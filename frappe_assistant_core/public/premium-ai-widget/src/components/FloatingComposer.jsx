import { useState, useRef } from 'react'
import MicIcon from './icons/MicIcon'
import AttachIcon from './icons/AttachIcon'
import SendIcon from './icons/SendIcon'

function ToolButton({ label, children, onClick, active }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={`grid h-9 w-9 place-items-center rounded-full transition-all duration-200 hover:bg-brand-50 hover:text-brand-700 focus-ring dark:hover:bg-brand-500/20 ${
        active ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/30' : 'text-slate-500 dark:text-slate-300'
      }`}
    >
      {children}
    </button>
  )
}

const REASONING_OPTIONS = [
  { value: 'auto', label: 'Auto' },
  { value: 'none', label: 'Fast' },
  { value: 'high', label: 'Deep' },
  { value: 'xhigh', label: 'Max' },
]

export default function FloatingComposer({ input, setInput, onSend, onStop, isThinking, onAttach, attachedFile, isUploading, onRemoveAttachment, limitReached, onNewChat, reasoningEffort, onReasoningEffortChange, frozen, frozenReason, connectionError, tokenUsage }) {
  const [isRecording, setIsRecording] = useState(false)
  const recognitionRef = useRef(null)
  const fileInputRef = useRef(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (isThinking || limitReached || frozen || connectionError) return
    onSend(input)
  }

  const handleAttachClick = () => fileInputRef.current?.click()

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (file && onAttach) onAttach(file)
    e.target.value = ''
  }

  const toggleMic = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      frappe.show_alert({ message: 'Voice input not supported in this browser', indicator: 'orange' })
      return
    }

    if (isRecording) {
      recognitionRef.current?.stop()
      return
    }

    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-IN'

    let baseText = input

    recognition.onresult = (event) => {
      let finalText = ''
      let interimText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) finalText += transcript
        else interimText += transcript
      }
      if (finalText) baseText += finalText
      setInput((baseText + interimText).trim())
    }

    recognition.onerror = (e) => {
      console.warn('Speech recognition error:', e.error)
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        frappe.show_alert({ message: 'Microphone access denied', indicator: 'red' })
      }
    }

    recognition.onend = () => setIsRecording(false)

    try {
      recognition.start()
      recognitionRef.current = recognition
      setIsRecording(true)
    } catch (e) {
      console.warn('Could not start speech recognition:', e)
    }
  }

  return (
    <footer className="shrink-0 border-t border-brand-100/80 bg-white/72 px-4 py-4 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/70">
      {(attachedFile || isUploading) && (
        <div className="mb-2 flex items-center gap-2 rounded-full border border-brand-100 bg-white/80 px-3 py-1.5 text-xs dark:border-white/10 dark:bg-white/10">
          {isUploading ? (
            <span className="text-slate-500 dark:text-slate-300">Uploading…</span>
          ) : (
            <>
              <span className="truncate text-slate-700 dark:text-slate-200">{attachedFile.file_name}</span>
              <button type="button" onClick={onRemoveAttachment} aria-label="Remove attachment" className="ml-auto text-slate-400 hover:text-red-500">✕</button>
            </>
          )}
        </div>
      )}
      {frozen && (
        <div className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <span>{frozenReason || 'Token limit exceeded. Please contact your administrator.'}</span>
        </div>
      )}
      {connectionError && (
        <div className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-orange-200 bg-orange-50 px-3 py-2 text-xs text-orange-700">
          <span>Connection lost. Please check your network and try again.</span>
        </div>
      )}
      {limitReached && (
        <div className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-brand-100 bg-brand-50 px-3 py-2 text-xs text-brand-700">
          <span>This chat has reached 10 messages. Start a new session to continue.</span>
          <button onClick={onNewChat} className="shrink-0 rounded-full bg-gradient-to-br from-brand-600 to-fuchsia-500 px-3 py-1 font-medium text-white">+ New Chat</button>
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex items-center gap-2 rounded-full border border-white/70 bg-white/85 px-3 py-2 shadow-[0_10px_30px_rgba(88,56,255,0.10)] dark:border-white/10 dark:bg-white/10">
        <input type="file" ref={fileInputRef} style={{ display: 'none' }} onChange={handleFileChange} />
        <ToolButton label="Voice input" onClick={toggleMic} active={isRecording}><MicIcon /></ToolButton>
        <ToolButton label="Attachment" onClick={handleAttachClick}><AttachIcon /></ToolButton>
        {!frozen && !connectionError && (
          <select
            value={reasoningEffort}
            onChange={(e) => onReasoningEffortChange(e.target.value)}
            className="h-7 rounded-md border border-slate-200 bg-white px-1.5 text-[10px] font-medium text-slate-600 focus:outline-none focus:ring-2 focus:ring-brand-400"
          >
            {REASONING_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        )}
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={limitReached || frozen || connectionError}
          placeholder={
            frozen ? 'Token limit exceeded.'
            : connectionError ? 'Connection lost.'
            : limitReached ? 'Message limit reached.'
            : 'Ask anything or drop a file...'
          }
          onKeyDown={(e) => {
            if (e.key === 'Enter' && isThinking) {
              e.preventDefault()
              return
            }
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (!isThinking && !limitReached && !frozen && !connectionError) onSend(input)
            }
          }}
          rows={1}
          className="max-h-24 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none dark:text-white dark:placeholder:text-slate-400"
          style={{ overflowY: input.split('\n').length > 3 ? 'auto' : 'hidden' }}
          onInput={(e) => {
            e.target.style.height = 'auto'
            e.target.style.height = Math.min(e.target.scrollHeight, 96) + 'px'
          }}
        />
        {isThinking ? (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onStop()
            }}
            aria-label="Stop generating"
            className="grid h-10 min-w-[40px] place-items-center rounded-full bg-slate-700 px-3 text-white shadow-lg transition-all hover:bg-slate-800 focus-ring"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
          </button>
        ) : (
          <button
            type="submit"
            disabled={limitReached || frozen || connectionError}
            aria-label="Send message"
            className="grid h-10 min-w-[40px] place-items-center rounded-full bg-gradient-to-r from-brand-600 to-fuchsia-500 px-3 text-white shadow-lg transition-all hover:scale-[1.03] focus-ring disabled:opacity-50"
          >
            <SendIcon />
          </button>
        )}
      </form>
      {tokenUsage && tokenUsage.enabled && (
        <div className="mt-2 flex items-center gap-2 px-1">
          <div className="flex-1 overflow-hidden rounded-full bg-slate-200 h-1.5">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                tokenUsage.frozen ? 'bg-red-500' : tokenUsage.tokens_used / tokenUsage.tokens_limit > 0.8 ? 'bg-orange-500' : 'bg-brand-500'
              }`}
              style={{ width: `${Math.min((tokenUsage.tokens_used / tokenUsage.tokens_limit) * 100, 100)}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-400 whitespace-nowrap">
            {(() => {
              const pct = Math.min((tokenUsage.tokens_used / tokenUsage.tokens_limit) * 100, 100)
              return pct > 0 && pct < 1 ? '<1' : pct.toFixed(pct < 10 ? 1 : 0)
            })()}% used
          </span>
        </div>
      )}
    </footer>
  )
}