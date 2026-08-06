import { useMemo, useState, useEffect, useRef } from 'react'
import WidgetHeader from './WidgetHeader'
import ChatTranscript from './ChatTranscript'
import FloatingComposer from './FloatingComposer'
import SessionsPanel from './SessionsPanel'
import aikoIcon from './aiko-icon.svg'

let nextId = 0
function uid() { return `msg-${Date.now()}-${++nextId}` }

function stripFileNote(content) {
  content = content || ''
  const re = /\[System note: The user has attached a file named "([^"]*)" available at (.*?)\. Use the appropriate tool[^\]]*\]/s
  const match = content.match(re)
  if (!match) return { text: content, attachment: null }
  const fileName = match[1]
  const fileUrl = match[2]
  let text = content.replace(re, '').trim()
  text = text.replace(/^The user sent a file with no additional message\.\s*/i, '').trim()
  return { text, attachment: { file_url: fileUrl, file_name: fileName, is_image: /\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(fileName || '') } }
}

function shortName(text) {
  if (!text) return 'New chat'
  const clean = text.replace(/\[System note:[\s\S]*?\]/g, '').replace(/[#*`_~>[\]]/g, '').replace(/\s+/g, ' ').trim()
  if (!clean) return 'Sent a file'
  const words = clean.split(' ').slice(0, 6).join(' ')
  return words.length < clean.length ? words + '…' : words
}

function formatDayTime(datetimeStr) {
  if (!datetimeStr) return ''
  const date = new Date(datetimeStr.replace(' ', 'T'))
  const isToday = date.toDateString() === new Date().toDateString()
  const timePart = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  if (isToday) return `Today, ${timePart}`
  return `${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}, ${timePart}`
}

const SUGGESTIONS = [
  { label: 'Fleet overview', prompt: 'How many vehicles are in the fleet?' },
  { label: 'Active vehicles', prompt: 'List active vehicles.' },
  { label: 'Compliance alerts', prompt: 'Which vehicles have expired compliance documents?' },
  { label: 'Expiring soon', prompt: 'Which compliances are expiring soon?' },
  { label: 'Open issues', prompt: 'Show all issues.' },
  { label: 'Overdue work orders', prompt: 'Which work orders are overdue?' },
]
function pickRandom(arr, n) { return [...arr].sort(() => Math.random() - 0.5).slice(0, n) }

export default function AIWidgetShell() {
  const [open, setOpen] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [sessionsOpen, setSessionsOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sessions, setSessions] = useState(null)
  const [visibleSessionCount, setVisibleSessionCount] = useState(10)
  const [firstMessages, setFirstMessages] = useState({})
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [suggestions, setSuggestions] = useState(() => pickRandom(SUGGESTIONS, 4))
  const [hasUnread, setHasUnread] = useState(false)
  const [messageCount, setMessageCount] = useState(0)
  const [closing, setClosing] = useState(false)
  const [reasoningEffort, setReasoningEffort] = useState('auto')
  const [frozen, setFrozen] = useState(false)
  const [frozenReason, setFrozenReason] = useState('')
  const [connectionError, setConnectionError] = useState(false)
  const [tokenUsage, setTokenUsage] = useState(null)

  const [sidebarSearch, setSidebarSearch] = useState('')
  const threadIdRef = useRef(frappe.utils.get_random(10))
  const currentRequestIdRef = useRef(null)
  const thinkingMsgIdRef = useRef(null)
  const sessionNameRef = useRef(null)
  const sessionTitleRef = useRef(null)
  const openRef = useRef(open)
  const abortedRequestsRef = useRef(new Set())
  // Mirrors `isThinking`, but as a ref: state updates only land in the DOM on
  // the next render, leaving a brief window where a second click (e.g. a
  // related-query button on an earlier message) can slip past a state-based
  // check before the disabled prop actually paints. This ref is set
  // synchronously the instant a send starts, closing that gap.
  const isThinkingRef = useRef(false)
  useEffect(() => { openRef.current = open }, [open])

  const shellClass = useMemo(() => {
      const exitClass = closing ? 'aiko-panel-exit' : 'aiko-panel-enter'
      if (fullscreen) {
        return `fixed inset-0 z-[9999] flex flex-col overflow-hidden bg-white transition-all duration-300 ${exitClass}`
      }
      const base = `fixed z-[9999] flex flex-col overflow-hidden rounded-[28px] glass-panel shadow-widget transition-all duration-300 ${exitClass}`
      return `${base} bottom-6 right-6 h-[min(620px,calc(100vh-48px))] w-[380px] max-w-[calc(100vw-24px)] max-md:bottom-3 max-md:right-3 max-md:h-[calc(100vh-24px)] max-md:w-[calc(100vw-24px)]`
    }, [fullscreen, closing])

  const filteredSessions = useMemo(() => {
    if (!sessions) return []
    if (!sidebarSearch.trim()) return sessions
    const q = sidebarSearch.toLowerCase()
    return sessions.filter((s) => {
      const preview = shortName(firstMessages[s.name] || s.preview).toLowerCase()
      const sessionId = (s.name || '').toLowerCase()
      return preview.includes(q) || sessionId.includes(q)
    })
  }, [sessions, sidebarSearch, firstMessages])

  const loadSessions = () => {
    frappe.call({
      method: 'frappe_assistant_core.api.assistant_api.get_chat_sessions',
      callback: (r) => {
        if (r.message && r.message.success) {
          const list = r.message.sessions || []
          setSessions(list)
          list.forEach((s) => {
            frappe.call({
              method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
              args: { session_name: s.name, limit: 10 },
              callback: (res) => {
                const msgs = res.message && res.message.messages
                if (!msgs || !msgs.length) return
                const userMsgs = msgs.filter((m) => m.role === 'user')
                if (!userMsgs.length) return
                const earliest = userMsgs.reduce((a, b) => {
                  const aTime = a.creation ? new Date(a.creation.replace(' ', 'T')).getTime() : 0
                  const bTime = b.creation ? new Date(b.creation.replace(' ', 'T')).getTime() : 0
                  return aTime <= bTime ? a : b
                })
                setFirstMessages((prev) => ({ ...prev, [s.name]: earliest.content }))
              }
            })
          })
        }
      }
    })
  }

  const fetchTokenUsage = () => {
    frappe.call({
      method: 'frappe_assistant_core.aiko.api.get_token_usage',
      callback: (r) => {
        if (r.message) {
          setTokenUsage(r.message)
          setFrozen(!!r.message.frozen)
          setFrozenReason(r.message.frozen ? 'Token limit exceeded. Please contact your administrator.' : '')
        }
      },
    })
  }

  useEffect(() => { loadSessions() }, [])

  useEffect(() => { fetchTokenUsage() }, [])

  useEffect(() => {
    const onDone = (data) => {
      if (data.thread_id !== threadIdRef.current) return
      if (abortedRequestsRef.current.has(data.request_id)) { abortedRequestsRef.current.delete(data.request_id); return }
      if (currentRequestIdRef.current && data.request_id !== currentRequestIdRef.current) return

      if (data.token_usage) setTokenUsage(data.token_usage)

      setMessages((prev) => {
        const withoutThinking = prev.filter((m) => m.id !== thinkingMsgIdRef.current)
        return withoutThinking.concat({
          id: uid(), role: 'ai', type: 'rich',
          text: data.success ? data.data : (data.error || 'An error occurred.'),
          time: Date.now()
        })
      })
      isThinkingRef.current = false
      setIsThinking(false)
      if (data.session_name && !sessionNameRef.current) {
        sessionNameRef.current = data.session_name
        loadSessions()
      }
      if (!openRef.current) setHasUnread(true)
    }

    const onStage = (data) => {
      if (data.thread_id !== threadIdRef.current) return
      if (data.request_id !== currentRequestIdRef.current) return
      setMessages((prev) => prev.map((m) => (m.id === thinkingMsgIdRef.current ? { ...m, stage: data.stage } : m)))
    }

    frappe.realtime.on('aiko_done', onDone)
    frappe.realtime.on('aiko_stage', onStage)
    return () => {
      frappe.realtime.off('aiko_done', onDone)
      frappe.realtime.off('aiko_stage', onStage)
    }
  }, [])

  const handlePrompt = (text) => setInput(text)
  const handleClose = () => {
    setClosing(true)
    setTimeout(() => {
      setOpen(false)
      setClosing(false)
      setFullscreen(false)
    }, 220)
  }
  const openWidget = () => {
    setOpen(true)
    setHasUnread(false)
  }

  // Lets external UI (e.g. a nav bar button) open the widget without needing
  // direct access to this component's state. Two hooks are exposed:
  // a global function and a custom DOM event — use whichever fits the caller.
  useEffect(() => {
    window.openAikoWidget = openWidget
    const onExternalOpen = () => openWidget()
    window.addEventListener('aiko:open', onExternalOpen)
    return () => {
      delete window.openAikoWidget
      window.removeEventListener('aiko:open', onExternalOpen)
    }
  }, [])

  const handleNewChat = () => {
    threadIdRef.current = frappe.utils.get_random(10)
    sessionNameRef.current = null
    sessionTitleRef.current = null
    setMessages([])
    setInput('')
    isThinkingRef.current = false
    setIsThinking(false)
    setSessionsOpen(false)
    setSuggestions(pickRandom(SUGGESTIONS, 4))
    setMessageCount(0)
    setConnectionError(false)
    fetchTokenUsage() // re-check the real frozen status instead of assuming it's cleared
  }

  const handleLoadSession = (sessionName, threadId) => {
    sessionNameRef.current = sessionName
    threadIdRef.current = threadId
    isThinkingRef.current = false
    setIsThinking(false)
    setSessionsOpen(false)
    setMessages([{ id: uid(), role: 'ai', type: 'rich', text: 'Loading messages…' }])
    frappe.call({
      method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
      args: { session_name: sessionName, limit: 20 },
      callback: (r) => {
        if (r.message && r.message.success) {
          const loaded = (r.message.messages || []).map((m) => {
            const parsed = stripFileNote(m.content)
            return { id: uid(), role: m.role === 'user' ? 'user' : 'ai', type: m.role === 'user' ? undefined : 'rich', text: parsed.text, attachment: parsed.attachment, time: m.creation ? new Date(m.creation.replace(' ', 'T')).getTime() : Date.now() }
          })
          setMessages(loaded)
          setMessageCount(loaded.filter((m) => m.role === 'user').length)
        } else { setMessages([]); setMessageCount(0) }
      },
      error: () => { setMessages([]); setMessageCount(0) }
    })
  }

  const handleSend = (value) => {
    const trimmed = (value || '').trim()
    if (!trimmed) return
    if (messageCount >= 10) return
    if (isThinkingRef.current) return
    isThinkingRef.current = true
    if (!sessionTitleRef.current) {
      sessionTitleRef.current = trimmed.slice(0, 40) + (trimmed.length > 40 ? '…' : '')
    }
    const userMessage = { id: uid(), role: 'user', text: trimmed, time: Date.now() }
    const thinkingMessage = { id: uid(), role: 'ai', type: 'thinking' }
    thinkingMsgIdRef.current = thinkingMessage.id

    setMessages((prev) => [...prev, userMessage, thinkingMessage])
    setInput('')
    setIsThinking(true)
    setMessageCount((c) => c + 1)

    const requestId = frappe.utils.get_random(10)
    currentRequestIdRef.current = requestId

    frappe.call({
      method: 'frappe_assistant_core.aiko.api.chat',
      args: { message: trimmed, thread_id: threadIdRef.current, request_id: requestId, reasoning_effort: reasoningEffort },
      callback: (r) => {
        if (!r.message || !r.message.success) {
          setMessages((prev) => prev.filter((m) => m.id !== thinkingMessage.id).concat({ id: uid(), role: 'ai', text: 'Could not start the request. Please try again.', failed: true, retryText: trimmed, time: Date.now() }))
          isThinkingRef.current = false
          if (r.message && r.message.frozen) {
            setMessages((prev) => prev.filter((m) => m.id !== thinkingMessage.id))
            setFrozen(true)
            setFrozenReason(r.message.reason || 'Token limit exceeded. Please contact your administrator.')
          } else {
            setMessages((prev) => prev.filter((m) => m.id !== thinkingMessage.id).concat({ id: uid(), role: 'ai', text: 'Could not start the request. Please try again.', failed: true, retryText: trimmed, time: Date.now() }))
          }
          setIsThinking(false)
        }
      },
      error: () => {
        setMessages((prev) => prev.filter((m) => m.id !== thinkingMessage.id).concat({ id: uid(), role: 'ai', text: 'Network error or server unavailable.', failed: true, retryText: trimmed, time: Date.now() }))
        isThinkingRef.current = false
        setConnectionError(true)
        setIsThinking(false)
      }
    })
  }

  const handleStop = () => {
    if (!isThinking) return
    const stoppedRequestId = currentRequestIdRef.current
    if (stoppedRequestId) {
      abortedRequestsRef.current.add(stoppedRequestId)
      frappe.call({ method: 'frappe_assistant_core.aiko.api.cancel_chat', args: { request_id: stoppedRequestId } })
    }
    setMessages((prev) => prev.filter((m) => m.id !== thinkingMsgIdRef.current).concat({ id: uid(), role: 'ai', type: 'rich', text: '_Response stopped._', time: Date.now() }))
    isThinkingRef.current = false
    setIsThinking(false)
    frappe.call({ method: 'frappe_assistant_core.aiko.api.save_stopped_message', args: { thread_id: threadIdRef.current } })
  }

  const handleRetry = (failedMessageId, originalText) => {
    setMessages((prev) => prev.filter((m) => m.id !== failedMessageId))
    handleSend(originalText)
  }

  if (!open) {
    return (
      <button
        onClick={openWidget}
        aria-label="Open AI assistant"
        className="group fixed bottom-6 right-6 z-[9999] grid h-16 w-16 place-items-center rounded-full bg-gradient-to-br from-brand-600 to-fuchsia-500 text-white shadow-widget transition hover:-translate-y-0.5 focus-ring"
      >
        <span className="pointer-events-none absolute right-full mr-3 whitespace-nowrap rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
          Hi, I'm AIKO — your AI assistant
          <span className="absolute left-full top-1/2 -translate-y-1/2 border-4 border-transparent border-l-slate-900" />
        </span>
        <img src={aikoIcon} alt="AIKO" className="h-9 w-9 object-contain" />
        {hasUnread && <span className="absolute -right-0.5 -top-0.5 h-3.5 w-3.5 rounded-full border-2 border-white bg-red-500" />}
      </button>
    )
  }

  // ── FULLSCREEN: sidebar layout ──
  if (fullscreen) {
    return (
      <section className={`${shellClass} font-sans`} aria-label="AI assistant fullscreen" role="dialog" aria-modal="false">
        <div className="flex h-full w-full">
          <aside className={`flex shrink-0 flex-col border-r border-brand-100/60 bg-white transition-all duration-300 ${sidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}`}>
            <div className="flex items-center justify-between px-4 py-4">
              <span className="text-sm font-semibold text-slate-900">AIKO</span>
            </div>

            <div className="px-3 pb-2">
              <button
                onClick={handleNewChat}
                className="flex w-full items-center gap-2 rounded-xl border border-brand-100 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-brand-50"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
                New chat
              </button>
            </div>

            <div className="px-3 pb-2">
              <div className="flex items-center gap-2 rounded-xl border border-brand-100 bg-white px-3 py-1.5">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-slate-400"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
                <input
                  value={sidebarSearch}
                  onChange={(e) => setSidebarSearch(e.target.value)}
                  placeholder="Search chats..."
                  className="w-full bg-transparent text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none"
                />
              </div>
            </div>

            <div className="px-4 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Recents</div>

            <div className="scrollbar-thin flex-1 overflow-y-auto px-2">
              {sessions === null && <div className="px-3 py-4 text-xs text-slate-400">Loading…</div>}
              {sessions && filteredSessions.length === 0 && (
                <div className="px-3 py-4 text-xs text-slate-400">No chats found.</div>
              )}
              {sessions && filteredSessions.slice(0, visibleSessionCount).map((s) => (
                  <button
                    key={s.name}
                    onClick={() => handleLoadSession(s.name, s.thread_id)}
                    className={`w-full rounded-xl px-3 py-2 text-left transition-colors hover:bg-brand-50 ${s.name === sessionNameRef.current ? 'bg-brand-50' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold text-slate-900">{shortName(firstMessages[s.name] || s.preview)}</div>
                      </div>
                      <span className="shrink-0 whitespace-nowrap pt-0.5 text-[11px] text-slate-400">{formatDayTime(s.preview_time || s.last_active)}</span>
                    </div>
                  </button>
                ))}
              {sessions && filteredSessions.length > visibleSessionCount && (
                <button
                  onClick={() => setVisibleSessionCount((n) => n + 10)}
                  className="w-full rounded-xl px-3 py-2 text-center text-xs font-medium text-brand-600 hover:bg-brand-50"
                >
                  Load more
                </button>
              )}
            </div>
          </aside>

          <div className="flex min-h-0 flex-1 flex-col">
            <header className="flex shrink-0 items-center justify-between gap-3 border-b border-brand-100/60 bg-white/60 px-4 py-3">
              <div className="flex items-center gap-3">
                <button onClick={() => setSidebarOpen((v) => !v)} aria-label="Toggle sidebar" className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-brand-50">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" /><line x1="9" y1="3" x2="9" y2="21" /></svg>
                </button>
                <span className="text-sm font-semibold text-slate-900">AIKO Assistant</span>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => setFullscreen(false)} aria-label="Exit fullscreen" className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-brand-50">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" /></svg>
                </button>
                <button onClick={handleClose} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-brand-50">✕</button>              </div>
            </header>
            <ChatTranscript
              messages={messages}
              onPrompt={handlePrompt}
              onRetry={handleRetry}
              emptySuggestions={messages.length === 0 ? suggestions : null}
              onSuggestionClick={handleSend}
            />
            <FloatingComposer
              input={input} setInput={setInput} onSend={handleSend} onStop={handleStop} isThinking={isThinking}
              limitReached={messageCount >= 10} onNewChat={handleNewChat}
              reasoningEffort={reasoningEffort} onReasoningEffortChange={setReasoningEffort}
              frozen={frozen} frozenReason={frozenReason} connectionError={connectionError}
              tokenUsage={tokenUsage}
            />
          </div>
        </div>
      </section>
    )
  }

  // ── COMPACT WIDGET PANEL ──
  return (
    <section className={`${shellClass} font-sans`} aria-label="AI desktop assistant" role="dialog" aria-modal="false">
      <WidgetHeader
        onNewChat={handleNewChat}
        onHistory={() => setSessionsOpen((v) => !v)}
        onFullscreen={() => setFullscreen(true)}
        onClose={handleClose}
      />
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        {sessionsOpen && (
          <SessionsPanel onClose={() => setSessionsOpen(false)} onSelect={handleLoadSession} currentSessionName={sessionNameRef.current} />
        )}
        <ChatTranscript
          messages={messages}
          onPrompt={handlePrompt}
          onRetry={handleRetry}
          emptySuggestions={messages.length === 0 ? suggestions : null}
          onSuggestionClick={handleSend}
        />
        <FloatingComposer
              input={input} setInput={setInput} onSend={handleSend} onStop={handleStop} isThinking={isThinking}
              limitReached={messageCount >= 10} onNewChat={handleNewChat}
              reasoningEffort={reasoningEffort} onReasoningEffortChange={setReasoningEffort}
              frozen={frozen} frozenReason={frozenReason} connectionError={connectionError}
              tokenUsage={tokenUsage}
        />
      </div>
    </section>
  )
}