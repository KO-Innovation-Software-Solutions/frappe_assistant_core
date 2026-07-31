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
  const [firstMessages, setFirstMessages] = useState({})
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [suggestions] = useState(() => pickRandom(SUGGESTIONS, 4))
  const [currentSessionName, setCurrentSessionName] = useState(null)

  const threadIdRef = useRef(frappe.utils.get_random(10))
  const currentRequestIdRef = useRef(null)
  const thinkingMsgIdRef = useRef(null)
  const sessionNameRef = useRef(null)
  const abortedRequestsRef = useRef(new Set())

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
              args: { session_name: s.name, limit: 1 },
              callback: (res) => {
                const msgs = res.message && res.message.messages
                const firstUser = msgs && msgs.find((m) => m.role === 'user')
                if (firstUser) setFirstMessages((prev) => ({ ...prev, [s.name]: firstUser.content }))
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
      setMessages((prev) => prev.filter((m) => m.id !== thinkingMsgIdRef.current).concat({
        id: uid(), role: 'ai', type: 'rich', text: data.success ? data.data : (data.error || 'An error occurred.'), time: Date.now()
      }))
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
    frappe.realtime.on('aiko_done', onDone)
    frappe.realtime.on('aiko_stage', onStage)
    return () => { frappe.realtime.off('aiko_done', onDone); frappe.realtime.off('aiko_stage', onStage) }
  }, [])

  const handleNewChat = () => {
    threadIdRef.current = frappe.utils.get_random(10)
    sessionNameRef.current = null
    setCurrentSessionName(null)
    setMessages([])
    setInput('')
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
    if (!trimmed) return
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
    setIsThinking(false)
  }

  const handleRetry = (id, retryText) => {
    setMessages((prev) => prev.filter((m) => m.id !== id))
    handleSend(retryText)
  }

  return (
    <div className="flex h-screen w-full bg-[linear-gradient(160deg,#f5f3ff,#ffffff_45%,#ede9fe)]">
      <aside className={`flex shrink-0 flex-col border-r border-brand-100/60 bg-white/70 backdrop-blur-xl transition-all duration-300 ${sidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}`}>
        <div className="flex items-center justify-between px-4 py-4">
          <span className="text-sm font-semibold text-slate-900">AIKO</span>
          <button onClick={handleNewChat} className="rounded-full bg-gradient-to-br from-brand-600 to-fuchsia-500 px-3 py-1.5 text-xs font-medium text-white">+ New</button>
        </div>
        <div className="scrollbar-thin flex-1 overflow-y-auto px-2">
          {sessions === null && <div className="px-3 py-4 text-xs text-slate-400">Loading…</div>}
          {sessions && sessions.map((s) => (
            <button
              key={s.name}
              onClick={() => handleLoadSession(s.name, s.thread_id)}
              className={`w-full rounded-xl px-3 py-2 text-left transition-colors hover:bg-brand-50 ${s.name === currentSessionName ? 'bg-brand-50' : ''}`}
            >
              <div className="truncate text-sm font-medium text-slate-900">{shortName(firstMessages[s.name] || s.preview)}</div>
              <div className="text-[11px] text-slate-400">{formatDayTime(s.preview_time || s.last_active)}</div>
            </button>
          ))}
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
        />
        <FloatingComposer input={input} setInput={setInput} onSend={handleSend} onStop={handleStop} isThinking={isThinking} />
      </div>
    </div>
  )
}