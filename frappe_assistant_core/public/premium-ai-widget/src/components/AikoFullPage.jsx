import { useState, useEffect, useRef, useMemo } from 'react'
import ChatTranscript from './ChatTranscript'
import FloatingComposer from './FloatingComposer'

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
  { label: 'Open issues', prompt: 'Show all issues.' },
]
function pickRandom(arr, n) { return [...arr].sort(() => Math.random() - 0.5).slice(0, n) }

export default function AikoFullPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sessions, setSessions] = useState(null)
  const [visibleSessionCount, setVisibleSessionCount] = useState(10)
  const [firstMessages, setFirstMessages] = useState({})
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [suggestions] = useState(() => pickRandom(SUGGESTIONS, 4))
  const [currentSessionName, setCurrentSessionName] = useState(null)
  const [sidebarSearch, setSidebarSearch] = useState('')

  const threadIdRef = useRef(frappe.utils.get_random(10))
  const currentRequestIdRef = useRef(null)
  const thinkingMsgIdRef = useRef(null)
  // Mirrors `isThinking`, but as a ref: state updates only land in the DOM on
  // the next render, leaving a brief window where a second rapid click can
  // slip past a state-based check before the disabled prop actually paints.
  // This ref is set synchronously the instant a send starts, closing that gap.
  const isThinkingRef = useRef(false)
  const sessionNameRef = useRef(null)
  const abortedRequestsRef = useRef(new Set())

  const filteredSessions = useMemo(() => {
    if (!sessions) return []
    if (!sidebarSearch.trim()) return sessions
    const q = sidebarSearch.toLowerCase()
    return sessions.filter((s) => shortName(firstMessages[s.name] || s.preview).toLowerCase().includes(q))
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

  useEffect(() => { loadSessions() }, [])

  useEffect(() => {
    const onDone = (data) => {
      if (data.thread_id !== threadIdRef.current) return
      if (abortedRequestsRef.current.has(data.request_id)) { abortedRequestsRef.current.delete(data.request_id); return }
      if (currentRequestIdRef.current && data.request_id !== currentRequestIdRef.current) return
      const finalText = data.success ? data.data : (data.error || 'An error occurred.')
      setMessages((prev) => {
        const hasStreamed = prev.some((m) => m.id === thinkingMsgIdRef.current)
        if (hasStreamed) {
          return prev.map((m) => (
            m.id === thinkingMsgIdRef.current
              ? { ...m, type: 'rich', streaming: false, text: finalText, time: Date.now() }
              : m
          ))
        }
        return prev.concat({ id: uid(), role: 'ai', type: 'rich', text: finalText, time: Date.now() })
      })
      isThinkingRef.current = false
      setIsThinking(false)
      if (data.session_name && !sessionNameRef.current) {
        sessionNameRef.current = data.session_name
        setCurrentSessionName(data.session_name)
        loadSessions()
      }
    }
    const onStage = (data) => {
      if (data.thread_id !== threadIdRef.current || data.request_id !== currentRequestIdRef.current) return
      setMessages((prev) => prev.map((m) => (m.id === thinkingMsgIdRef.current ? { ...m, stage: data.stage } : m)))
    }
    const onChunk = (data) => {
      if (data.thread_id !== threadIdRef.current || data.request_id !== currentRequestIdRef.current) return
      setMessages((prev) => prev.map((m) => (
        m.id === thinkingMsgIdRef.current
          ? { ...m, type: 'rich', streaming: true, text: data.text }
          : m
      )))
    }
    frappe.realtime.on('aiko_done', onDone)
    frappe.realtime.on('aiko_stage', onStage)
    frappe.realtime.on('aiko_chunk', onChunk)
    return () => { frappe.realtime.off('aiko_done', onDone); frappe.realtime.off('aiko_stage', onStage); frappe.realtime.off('aiko_chunk', onChunk) }
  }, [])

  const handleNewChat = () => {
    threadIdRef.current = frappe.utils.get_random(10)
    sessionNameRef.current = null
    setCurrentSessionName(null)
    setMessages([])
    setInput('')
    isThinkingRef.current = false
    setIsThinking(false)
  }

  const handleLoadSession = (sessionName, threadId) => {
    sessionNameRef.current = sessionName
    threadIdRef.current = threadId
    setCurrentSessionName(sessionName)
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
        } else setMessages([])
      },
      error: () => setMessages([])
    })
  }

  const handleSend = (value) => {
    const trimmed = (value || '').trim()
    if (!trimmed || isThinkingRef.current) return
    isThinkingRef.current = true
    const userMessage = { id: uid(), role: 'user', text: trimmed, time: Date.now() }
    const thinkingMessage = { id: uid(), role: 'ai', type: 'thinking' }
    thinkingMsgIdRef.current = thinkingMessage.id
    setMessages((prev) => [...prev, userMessage, thinkingMessage])
    setInput('')
    setIsThinking(true)
    const requestId = frappe.utils.get_random(10)
    currentRequestIdRef.current = requestId
    frappe.call({
      method: 'frappe_assistant_core.aiko.api.chat',
      args: { message: trimmed, thread_id: threadIdRef.current, request_id: requestId },
      error: () => {
        isThinkingRef.current = false
        setMessages((prev) => prev.filter((m) => m.id !== thinkingMessage.id).concat({ id: uid(), role: 'ai', text: 'Network error.', failed: true, retryText: trimmed, time: Date.now() }))
        setIsThinking(false)
      }
    })
  }

  const handleStop = () => {
    if (!isThinking) return
    if (currentRequestIdRef.current) {
      abortedRequestsRef.current.add(currentRequestIdRef.current)
      frappe.call({ method: 'frappe_assistant_core.aiko.api.cancel_chat', args: { request_id: currentRequestIdRef.current } })
    }
    setMessages((prev) => prev.filter((m) => m.id !== thinkingMsgIdRef.current).concat({ id: uid(), role: 'ai', type: 'rich', text: '_Response stopped._', time: Date.now() }))
    isThinkingRef.current = false
    setIsThinking(false)
  }

  const handleRetry = (id, retryText) => {
    setMessages((prev) => prev.filter((m) => m.id !== id))
    handleSend(retryText)
  }

  return (
    <div className="flex h-screen w-full font-sans bg-[linear-gradient(160deg,#f5f3ff,#ffffff_45%,#ede9fe)]">
      <aside className={`flex shrink-0 flex-col border-r border-brand-100/60 bg-white/70 backdrop-blur-xl transition-all duration-300 ${sidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}`}>
        <div className="flex items-center px-4 py-4">
          <span className="text-sm font-semibold text-slate-900">AIKO</span>
        </div>

        <div className="px-3 pb-3">
          <button
            onClick={handleNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-brand-600 to-fuchsia-500 px-3 py-2 text-sm font-medium text-white transition hover:opacity-90"
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
              className={`w-full rounded-xl px-3 py-2 text-left transition-colors hover:bg-brand-50 ${s.name === currentSessionName ? 'bg-brand-50' : ''}`}
            >
              <div className="truncate text-sm font-medium text-slate-900">{shortName(firstMessages[s.name] || s.preview)}</div>
              <div className="text-[11px] text-slate-400">{formatDayTime(s.preview_time || s.last_active)}</div>
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
        <header className="flex shrink-0 items-center gap-3 border-b border-brand-100/60 bg-white/60 px-4 py-3 backdrop-blur-xl">
          <button onClick={() => setSidebarOpen((v) => !v)} aria-label="Toggle sidebar" className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-brand-50">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" /><line x1="9" y1="3" x2="9" y2="21" /></svg>
          </button>
          <span className="text-sm font-semibold text-slate-900">AIKO Assistant</span>
        </header>
        <ChatTranscript
          messages={messages}
          onPrompt={setInput}
          onRetry={handleRetry}
          emptySuggestions={messages.length === 0 ? suggestions : null}
          onSuggestionClick={handleSend}
          isThinking={isThinking}
        />
        <FloatingComposer input={input} setInput={setInput} onSend={handleSend} onStop={handleStop} isThinking={isThinking} />
      </div>
    </div>
  )
}