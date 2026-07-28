import { useEffect, useState } from 'react'

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
  const today = new Date()
  const isToday = date.toDateString() === today.toDateString()
  const timePart = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  if (isToday) return `Today, ${timePart}`
  const datePart = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return `${datePart}, ${timePart}`
}

export default function SessionsPanel({ onClose, onSelect, currentSessionName }) {
  const [sessions, setSessions] = useState(null)
  const [error, setError] = useState(false)
  const [firstMessages, setFirstMessages] = useState({})
  const [showAll, setShowAll] = useState(false)
  const visibleSessions = showAll ? sessions : (sessions || []).slice(0, 8)
  useEffect(() => {
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
        } else {
          setError(true)
        }
      },
      error: () => setError(true)
    })
  }, [])

  return (
    <div className="absolute inset-0 z-10 flex flex-col bg-white/95 backdrop-blur-xl dark:bg-slate-900/95">
      <div className="flex items-center justify-between border-b border-brand-100/80 px-4 py-3 dark:border-white/10">
        <span className="text-sm font-semibold text-slate-900 dark:text-white">Recent Chats</span>
        <button onClick={onClose} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-brand-50 focus-ring dark:text-slate-300 dark:hover:bg-brand-500/20">
          ✕
        </button>
      </div>
      <div className="scrollbar-thin flex-1 overflow-y-auto px-2 py-2">
        {sessions === null && !error && (
          <div className="px-3 py-6 text-center text-sm text-slate-400">Loading chats…</div>
        )}
        {error && (
          <div className="px-3 py-6 text-center text-sm text-slate-400">Could not load chats.</div>
        )}
        {sessions && sessions.length === 0 && (
          <div className="px-3 py-6 text-center text-sm text-slate-400">No previous chats found.</div>
        )}
        {sessions && visibleSessions.map((s) => (
          <button
          key={s.name}
          onClick={() => onSelect(s.name, s.thread_id)}
          className={`w-full rounded-2xl px-3 py-2 text-left transition-colors hover:bg-brand-50 dark:hover:bg-brand-500/10 ${
          s.name === currentSessionName ? 'bg-brand-50 dark:bg-brand-500/10' : ''
          }`}
          >
          <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-900 dark:text-white">{s.name}</div>
          <div className="truncate text-sm text-slate-600 dark:text-slate-300">{shortName(firstMessages[s.name] || s.preview)}</div>
          </div>
          <span className="shrink-0 whitespace-nowrap text-[11px] text-slate-400 pt-0.5">{formatDayTime(s.preview_time || s.last_active)}</span>
          </div>
          </button>
                  ))}
          {sessions && sessions.length > 8 && !showAll && (
          <button
          onClick={() => setShowAll(true)}
          className="w-full rounded-2xl px-3 py-2 text-center text-xs font-medium text-brand-600 hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-brand-500/10"
          >
          Show all ({sessions.length})
          </button>
                  )}
          </div>
          </div>
            )
          }