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

export default function FloatingComposer({ input, setInput, onSend, onStop, isThinking, onAttach, attachedFile, isUploading, onRemoveAttachment }) {  const [isRecording, setIsRecording] = useState(false)
  const recognitionRef = useRef(null)
  const fileInputRef = useRef(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (isThinking) return
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
      <form onSubmit={handleSubmit} className="flex items-center gap-2 rounded-full border border-white/70 bg-white/85 px-3 py-2 shadow-[0_10px_30px_rgba(88,56,255,0.10)] dark:border-white/10 dark:bg-white/10">
        <input type="file" ref={fileInputRef} style={{ display: 'none' }} onChange={handleFileChange} />
        <ToolButton label="Voice input" onClick={toggleMic} active={isRecording}><MicIcon /></ToolButton>
        <ToolButton label="Attachment" onClick={handleAttachClick}><AttachIcon /></ToolButton>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything or drop a file..."
          className="flex-1 bg-transparent px-2 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none dark:text-white dark:placeholder:text-slate-400"
        />
        {isThinking ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className="grid h-10 min-w-[40px] place-items-center rounded-full bg-slate-700 px-3 text-white shadow-lg transition-all hover:bg-slate-800 focus-ring"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
          </button>
        ) : (
          <button
            type="submit"
            aria-label="Send message"
            className="grid h-10 min-w-[40px] place-items-center rounded-full bg-gradient-to-r from-brand-600 to-fuchsia-500 px-3 text-white shadow-lg transition-all hover:scale-[1.03] focus-ring"
          >
            <SendIcon />
          </button>
        )}
      </form>
    </footer>
  )
}