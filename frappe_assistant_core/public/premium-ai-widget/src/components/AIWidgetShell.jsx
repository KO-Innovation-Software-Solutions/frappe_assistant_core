import { useMemo, useState, useEffect, useRef } from 'react'
import WidgetHeader from './WidgetHeader'
import ChatTranscript from './ChatTranscript'
import FloatingComposer from './FloatingComposer'
import SessionsPanel from './SessionsPanel'

let nextId = 0
function uid() {
  return `msg-${Date.now()}-${++nextId}`
}

function stripFileNote(content) {
  content = content || ''
  const re = /\[System note: The user has attached a file named "([^"]*)" available at (.*?)\. Use the appropriate tool[^\]]*\]/s
  const match = content.match(re)
  if (!match) return { text: content, attachment: null }

  const fileName = match[1]
  const fileUrl = match[2]
  let text = content.replace(re, '').trim()
  text = text.replace(/^The user sent a file with no additional message\.\s*/i, '').trim()

  return {
    text,
    attachment: {
      file_url: fileUrl,
      file_name: fileName,
      is_image: /\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(fileName || '')
    }
  }
}
const SUGGESTIONS = [
  { label: 'Fleet overview', prompt: 'How many vehicles are in the fleet?' },
  { label: 'Active vehicles', prompt: 'List active vehicles.' },
  { label: 'Compliance alerts', prompt: 'Which vehicles have expired compliance documents?' },
  { label: 'Expiring soon', prompt: 'Which compliances are expiring soon?' },
  { label: 'Open inspections', prompt: 'Show all open inspections.' },
  { label: 'Overdue inspections', prompt: 'Which inspections are overdue?' },
  { label: 'Open issues', prompt: 'Show all issues.' },
  { label: 'High priority issues', prompt: 'Show all high priority issues.' },
  { label: 'Critical faults', prompt: 'Show all critical faults.' },
  { label: 'Work orders', prompt: 'Show all submitted work orders.' },
  { label: 'Overdue work orders', prompt: 'Which work orders are overdue?' },
  { label: 'Fuel entries today', prompt: 'Show fuel entries for today.' },
  { label: 'Service reminders', prompt: 'Show all upcoming service reminders.' },
  { label: 'Active trips', prompt: 'What trips are active right now?' },
  { label: "Today's bookings", prompt: "Show today's bookings." },
  { label: 'Pending bookings', prompt: 'Show pending bookings.' },
]

function pickRandom(arr, n) {
  return [...arr].sort(() => Math.random() - 0.5).slice(0, n)
}

export default function AIWidgetShell() {
  const [open, setOpen] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [sessionsOpen, setSessionsOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [suggestions, setSuggestions] = useState(() => pickRandom(SUGGESTIONS, 4))
  const [hasUnread, setHasUnread] = useState(false)
  const [attachedFile, setAttachedFile] = useState(null)
  const [isUploading, setIsUploading] = useState(false)

  const threadIdRef = useRef(frappe.utils.get_random(10))
  const currentRequestIdRef = useRef(null)
  const thinkingMsgIdRef = useRef(null)
  const sessionNameRef = useRef(null)
  const sessionTitleRef = useRef(null)
  const openRef = useRef(open)
  const abortedRequestsRef = useRef(new Set())

  useEffect(() => {
    openRef.current = open
  }, [open])

  const shellClass = useMemo(() => {
    const base = 'fixed z-[9999] flex flex-col overflow-hidden rounded-[28px] glass-panel shadow-widget transition-all duration-300 aiko-panel-enter'
    if (fullscreen) return `${base} inset-5`
    return `${base} bottom-6 right-6 h-[min(620px,calc(100vh-48px))] w-[380px] max-w-[calc(100vw-24px)] max-md:bottom-3 max-md:right-3 max-md:h-[calc(100vh-24px)] max-md:w-[calc(100vw-24px)]`
  }, [fullscreen])

  useEffect(() => {
    const onDone = (data) => {
      if (data.thread_id !== threadIdRef.current) return
      if (abortedRequestsRef.current.has(data.request_id)) {
        abortedRequestsRef.current.delete(data.request_id)
        return
      }
      if (currentRequestIdRef.current && data.request_id !== currentRequestIdRef.current) return

      setMessages((prev) => {
        const withoutThinking = prev.filter((m) => m.id !== thinkingMsgIdRef.current)
        return withoutThinking.concat({
          id: uid(),
          role: 'ai',
          type: 'rich',
          text: data.success ? data.data : (data.error || 'An error occurred.'),
          time: Date.now()
        })
      })
      setIsThinking(false)
      if (data.session_name && !sessionNameRef.current) {
        sessionNameRef.current = data.session_name
      }
      if (!openRef.current) setHasUnread(true)
    }

    const onStage = (data) => {
      if (data.thread_id !== threadIdRef.current) return
      if (data.request_id !== currentRequestIdRef.current) return
      setMessages((prev) =>
        prev.map((m) => (m.id === thinkingMsgIdRef.current ? { ...m, stage: data.stage } : m))
      )
    }

    frappe.realtime.on('aiko_done', onDone)
    frappe.realtime.on('aiko_stage', onStage)
    return () => {
      frappe.realtime.off('aiko_done', onDone)
      frappe.realtime.off('aiko_stage', onStage)
    }
  }, [])

  const handlePrompt = (text) => setInput(text)
  const handleAttach = (file) => {
  setIsUploading(true)
  const formData = new FormData()
  formData.append('file', file, file.name)
  formData.append('is_private', 0)

  fetch('/api/method/upload_file', {
    method: 'POST',
    body: formData,
    headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token }
  })
    .then((res) => res.json())
    .then((res) => {
      const msg = res.message || {}
      setAttachedFile({
        file_url: msg.file_url,
        file_name: msg.file_name || file.name,
        is_image: /\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(msg.file_name || file.name)
      })
      setIsUploading(false)
    })
    .catch(() => {
      setIsUploading(false)
      setAttachedFile(null)
      frappe.show_alert({ message: 'File upload failed.', indicator: 'red' })
    })
}

const removeAttachment = () => setAttachedFile(null)

const openWidget = () => {
    setOpen(true)
    setHasUnread(false)
}

  const handleNewChat = () => {
    threadIdRef.current = frappe.utils.get_random(10)
    sessionNameRef.current = null
    sessionTitleRef.current = null
    setMessages([])
    setInput('')
    setIsThinking(false)
    setSessionsOpen(false)
    setSuggestions(pickRandom(SUGGESTIONS, 4))
  }

const handleLoadSession = (sessionName, threadId) => {
  sessionNameRef.current = sessionName
  threadIdRef.current = threadId
  setSessionsOpen(false)
  setMessages([{ id: uid(), role: 'ai', type: 'rich', text: 'Loading messages…' }])

  frappe.call({
    method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
    args: { session_name: sessionName, limit: 20 },
    callback: (r) => {
      if (r.message && r.message.success) {
        const loaded = (r.message.messages || []).map((m) => {
          const parsed = stripFileNote(m.content)
          return {
            id: uid(),
            role: m.role === 'user' ? 'user' : 'ai',
            type: m.role === 'user' ? undefined : 'rich',
            text: parsed.text,
            attachment: parsed.attachment,
            time: m.creation ? new Date(m.creation.replace(' ', 'T')).getTime() : Date.now()
          }
        })
        setMessages(loaded)
      } else {
        setMessages([])
      }
    },
    error: () => setMessages([])
  })
}

const handleSend = (value) => {
  const trimmed = (value || '').trim()
  if (!trimmed && !attachedFile) return

  if (!sessionTitleRef.current) {
    sessionTitleRef.current = (trimmed || 'Sent a file').slice(0, 40) + (trimmed.length > 40 ? '…' : '')
  }

  const sentAttachment = attachedFile
  const userMessage = { id: uid(), role: 'user', text: trimmed, time: Date.now(), attachment: sentAttachment }
  const thinkingMessage = { id: uid(), role: 'ai', type: 'thinking' }
  thinkingMsgIdRef.current = thinkingMessage.id

  setMessages((prev) => [...prev, userMessage, thinkingMessage])
  setInput('')
  setAttachedFile(null)
  setIsThinking(true)

  let outgoingText = trimmed
  if (sentAttachment) {
    const fullUrl = sentAttachment.file_url.startsWith('/')
      ? (window.location.origin + sentAttachment.file_url)
      : sentAttachment.file_url
    const fileNote = `[System note: The user has attached a file named "${sentAttachment.file_name}" available at ${fullUrl}. Use the appropriate tool to read/extract its contents before answering, then respond based on what it contains.]`
    outgoingText = trimmed ? `${trimmed}\n\n${fileNote}` : `The user sent a file with no additional message.\n\n${fileNote}`
  }

  const requestId = frappe.utils.get_random(10)
  currentRequestIdRef.current = requestId

  frappe.call({
    method: 'frappe_assistant_core.aiko.api.chat',
    args: { message: outgoingText, thread_id: threadIdRef.current, request_id: requestId },
    callback: (r) => {
      if (!r.message || !r.message.success) {
        setMessages((prev) =>
          prev.filter((m) => m.id !== thinkingMessage.id)
            .concat({ id: uid(), role: 'ai', text: 'Could not start the request. Please try again.', failed: true, retryText: trimmed, time: Date.now() })
        )
        setIsThinking(false)
      }
    },
    error: () => {
      setMessages((prev) =>
        prev.filter((m) => m.id !== thinkingMessage.id)
          .concat({ id: uid(), role: 'ai', text: 'Network error or server unavailable.', failed: true, retryText: trimmed, time: Date.now() })
      )
      setIsThinking(false)
    }
  })
}

  const handleStop = () => {
    if (!isThinking) return
    const stoppedRequestId = currentRequestIdRef.current
    if (stoppedRequestId) {
      abortedRequestsRef.current.add(stoppedRequestId)
      frappe.call({
        method: 'frappe_assistant_core.aiko.api.cancel_chat',
        args: { request_id: stoppedRequestId }
      })
    }
    setMessages((prev) =>
      prev.filter((m) => m.id !== thinkingMsgIdRef.current)
        .concat({ id: uid(), role: 'ai', type: 'rich', text: '_Response stopped._', time: Date.now() })
    )
    setIsThinking(false)
    frappe.call({
      method: 'frappe_assistant_core.aiko.api.save_stopped_message',
      args: { thread_id: threadIdRef.current }
    })
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
        className="fixed bottom-6 right-6 z-[9999] grid h-16 w-16 place-items-center rounded-full bg-gradient-to-br from-brand-600 to-fuchsia-500 text-white shadow-widget transition hover:-translate-y-0.5 focus-ring"
      >
        ✦
        {hasUnread && (
          <span className="absolute -right-0.5 -top-0.5 h-3.5 w-3.5 rounded-full border-2 border-white bg-red-500" />
        )}
      </button>
    )
  }

  return (
    <section className={shellClass} aria-label="AI desktop assistant" role="dialog" aria-modal="false">
      <WidgetHeader
        onNewChat={handleNewChat}
        onHistory={() => setSessionsOpen((v) => !v)}
        onFullscreen={() => setFullscreen((v) => !v)}
        onClose={() => setOpen(false)}
      />
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        {sessionsOpen && (
          <SessionsPanel
            onClose={() => setSessionsOpen(false)}
            onSelect={handleLoadSession}
            currentSessionName={sessionNameRef.current}
          />
        )}
        <ChatTranscript
          messages={messages}
          onPrompt={handlePrompt}
          onRetry={handleRetry}
          emptySuggestions={messages.length === 0 ? suggestions : null}
          onSuggestionClick={handleSend}
        />
        <FloatingComposer
          input={input}
          setInput={setInput}
          onSend={handleSend}
          onStop={handleStop}
          isThinking={isThinking}
          onAttach={handleAttach}
          attachedFile={attachedFile}
          isUploading={isUploading}
          onRemoveAttachment={removeAttachment}
        />
      </div>
    </section>
  )
}