import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const COLORS = ['#7c3aed', '#a78bfa', '#c4b5fd', '#ddd6fe', '#f472b6', '#8b5cf6']

function ChartRenderer({ spec }) {
  return (
    <div className="scrollbar-thin aiko-scroll-x rounded-2xl border border-brand-100 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5">
      {spec.title && <div className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">{spec.title}</div>}
      <div className="min-w-[280px]">
        <ResponsiveContainer width="100%" height={200}>
          {spec.type === 'pie' ? (
            <PieChart>
              <Pie data={spec.data} dataKey={spec.yKey} nameKey={spec.xKey} outerRadius={70} label>
                {spec.data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          ) : spec.type === 'line' ? (
            <LineChart data={spec.data}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(139,92,246,0.15)" />
              <XAxis dataKey={spec.xKey} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line dataKey={spec.yKey} stroke="#7c3aed" strokeWidth={2} />
            </LineChart>
          ) : (
            <BarChart data={spec.data}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(139,92,246,0.15)" />
              <XAxis dataKey={spec.xKey} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey={spec.yKey} fill="#7c3aed" radius={[6, 6, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}
function useTypewriter(fullText, active) {
  const [shown, setShown] = useState(active ? '' : fullText)
  const doneRef = useRef(!active)

  useEffect(() => {
    if (!active || doneRef.current) {
      setShown(fullText)
      return
    }
    let i = 0
    const step = Math.max(1, Math.floor(fullText.length / 120))
    const interval = setInterval(() => {
      i += step
      setShown(fullText.slice(0, i))
      if (i >= fullText.length) {
        clearInterval(interval)
        doneRef.current = true
      }
    }, 12)
    return () => clearInterval(interval)
  }, [fullText, active])

  return shown
}

function splitContent(text) {
  if (!text) return [{ type: 'text', content: '' }]
  const parts = []
  const fenceRe = /```(?:\w+)?\s*([\s\S]*?)```/g
  let lastIndex = 0
  let match

  while ((match = fenceRe.exec(text)) !== null) {
    const before = text.slice(lastIndex, match.index)
    if (before.trim()) parts.push({ type: 'text', content: before })

    let isChart = false
    try {
      const parsed = JSON.parse(match[1])
      if (parsed && parsed.type && parsed.data && parsed.xKey && parsed.yKey) {
        parts.push({ type: 'chart', content: parsed })
        isChart = true
      }
    } catch {}
    if (!isChart) parts.push({ type: 'text', content: match[0] })

    lastIndex = fenceRe.lastIndex
  }

  const remaining = text.slice(lastIndex)
  if (remaining.trim()) parts.push({ type: 'text', content: remaining })

  return parts.length ? parts : [{ type: 'text', content: text }]
}

function stripForSpeech(text) {
  return (text || '').replace(/```[\s\S]*?```/g, '').replace(/[#*`_~>[\]]/g, '').trim()
}

export default function RichResponseCard({ text, animate }) {
  const revealed = useTypewriter(text || '', !!animate)
  const parts = splitContent(revealed)
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
    utterance.rate = 1
    utterance.pitch = 1
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    setSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }

  return (
    <div className="space-y-3 animate-fadeUp">
      {parts.map((part, i) =>
        part.type === 'chart' ? (
          <ChartRenderer key={i} spec={part.content} />
        ) : (
    <div key={i} className="scrollbar-thin aiko-scroll-x">
      <div className="prose prose-sm max-w-none dark:prose-invert prose-table:text-xs prose-th:bg-brand-50 prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1 prose-td:border prose-th:border prose-td:border-brand-100">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{part.content}</ReactMarkdown>
      </div>
    </div>
        )
      )}
    </div>
  )
}