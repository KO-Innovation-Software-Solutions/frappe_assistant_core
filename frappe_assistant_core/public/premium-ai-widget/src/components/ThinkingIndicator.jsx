import { useState, useEffect, useRef } from 'react'

const PHRASES = [
  'Searching the web',
  'Looking into this',
  'Checking records',
  'Digging through documents',
  'Pulling that up',
  'Scanning through everything',
  'Let me check on this',
  'Going through the details',
  'Fetching the latest info',
  'Almost there'
]

function shuffled(arr) {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

export default function ThinkingIndicator({ stage }) {
  const [text, setText] = useState(stage || PHRASES[0])
  const orderRef = useRef(shuffled(PHRASES))
  const idxRef = useRef(0)

  useEffect(() => {
    if (stage) {
      setText(stage)
      return
    }
    const interval = setInterval(() => {
      idxRef.current = (idxRef.current + 1) % orderRef.current.length
      setText(orderRef.current[idxRef.current])
    }, 2200)
    return () => clearInterval(interval)
  }, [stage])

  return (
    <div className="flex items-center gap-2 py-1">
      <span className="flex shrink-0 gap-0.5">
        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-dotBounce"></span>
        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-dotBounce [animation-delay:0.15s]"></span>
        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-dotBounce [animation-delay:0.3s]"></span>
      </span>
      <span className="aiko-shimmer-text text-sm font-medium">{text}</span>
    </div>
  )
}