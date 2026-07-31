import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'
import AssistantGlassCard from './AssistantGlassCard'
import RichResponseCard from './RichResponseCard'
import ThinkingIndicator from './ThinkingIndicator'

function stripForSpeech(text) {
  return (text || '').replace(/```[\s\S]*?```/g, '').replace(/[#*`_~>[\]]/g, '').trim()
}

function formatTime(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function MessageActions({ text }) {
  const [copied, setCopied] = useState(false)
  const [speaking, setSpeaking] = useState(false)

  const handleCopy = () => {
    if (!navigator.clipboard) return
    navigator.clipboard.writeText(text || '').then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const handleSpeak = () => {
    if (speaking) {
      window.speechSynthesis.cancel()
      setSpeaking(false)
      return
    }
    const cleanText = stripForSpeech(text)
    if (!cleanText) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.lang = 'en-IN'
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    setSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }

  return (
    <div className="flex items-center gap-1 text-slate-400 dark:text-slate-500">
      <button onClick={handleCopy} aria-label="Copy" className="grid h-6 w-6 place-items-center rounded-full transition hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/20 dark:hover:text-brand-300">
        {copied ? (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
        ) : (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
      </button>
      <button onClick={handleSpeak} aria-label="Listen" className={`grid h-6 w-6 place-items-center rounded-full transition hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/20 dark:hover:text-brand-300 ${speaking ? 'text-brand-700 dark:text-brand-300' : ''}`}>
        {speaking ? (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2" /></svg>
        ) : (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
          </svg>
        )}
      </button>
    </div>
  )
}

export default function ChatTranscript({ messages, onPrompt, onRetry, emptySuggestions, onSuggestionClick }) {
  const ref = useRef(null)
  const [isScrolledUp, setIsScrolledUp] = useState(false)
  const prevCountRef = useRef(messages.length)

  const scrollToBottom = (smooth = true) => {
    const el = ref.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
    setIsScrolledUp(false)
  }

  useEffect(() => {
    const grew = messages.length > prevCountRef.current
    prevCountRef.current = messages.length
    if (grew && !isScrolledUp) {
      scrollToBottom()
    }
  }, [messages])

  const handleScroll = () => {
    const el = ref.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setIsScrolledUp(distFromBottom > 80)
  }

  if (emptySuggestions) {
    return (
      <main className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 bg-[linear-gradient(180deg,rgba(255,255,255,0.28),rgba(237,233,254,0.34))] px-6 py-4 text-center dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.18),rgba(76,29,149,0.12))]">
        <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-brand-600 to-fuchsia-500 text-white">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">How can I help?</h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Ask me anything about your fleet.</p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          {emptySuggestions.map((s) => (
            <button
              key={s.label}
              onClick={() => onSuggestionClick(s.prompt)}
              className="rounded-full border border-brand-200 bg-white/80 px-3 py-1.5 text-xs font-medium text-brand-700 transition hover:bg-brand-50 focus-ring dark:border-white/10 dark:bg-white/10 dark:text-brand-200"
            >
              {s.label}
            </button>
          ))}
        </div>
      </main>
    )
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <main
        ref={ref}
        onScroll={handleScroll}
        className="scrollbar-thin aiko-scroll-y min-h-0 flex-1 space-y-3 bg-[linear-gradient(180deg,rgba(255,255,255,0.28),rgba(237,233,254,0.34))] px-4 py-4 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.18),rgba(76,29,149,0.12))]"
      >
        {messages.map((message) => {
          if (message.role === 'user') {
            return (
              <div key={message.id} className="group animate-fadeUp">
                <MessageBubble text={message.text} attachment={message.attachment} />
                <div className="mt-0.5 text-right text-[10px] text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">
                  {formatTime(message.time)}
                </div>
              </div>
            )
          }

          return (
            <div key={message.id} className="group animate-fadeUp">
              {message.type === 'thinking' ? (
                <ThinkingIndicator stage={message.stage} />
              ) : (
                <>
                  <AssistantGlassCard>
                    <RichResponseCard
                      text={message.text}
                      onPrompt={onPrompt}
                      animate={message.id === messages[messages.length - 1]?.id}
                    />
                  </AssistantGlassCard>
                  <div className="mt-0.5 flex items-center justify-between px-1">
                    <MessageActions text={message.text} />
                    <span className="text-[10px] text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">
                      {formatTime(message.time)}
                    </span>
                  </div>
                  {message.failed && (
                    <button
                      onClick={() => onRetry(message.id, message.retryText)}
                      className="mt-1 flex items-center gap-1 px-1 text-[11px] font-medium text-brand-600 hover:text-brand-700 dark:text-brand-300"
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="1 4 1 10 7 10" />
                        <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                      </svg>
                      Retry
                    </button>
                  )}
                </>
              )}
            </div>
          )
        })}
      </main>
      {isScrolledUp && (
        <button
          onClick={() => scrollToBottom()}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-lg transition hover:bg-brand-700"
        >
          ↓ 
        </button>
      )}
    </div>
  )
}