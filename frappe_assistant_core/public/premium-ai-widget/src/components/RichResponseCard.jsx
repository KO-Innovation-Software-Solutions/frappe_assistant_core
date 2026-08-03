import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const COLORS = ['#7c3aed', '#a78bfa', '#c4b5fd', '#ddd6fe', '#f472b6', '#8b5cf6']

function ChartBody({ spec }) {
  return (
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
  )
}

// Single chart: same as before, no tab chrome needed.
function ChartRenderer({ spec }) {
  return (
    <div className="scrollbar-thin aiko-scroll-x rounded-2xl border border-brand-100 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5">
      {spec.title && <div className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">{spec.title}</div>}
      <ChartBody spec={spec} />
    </div>
  )
}

// Multiple charts in one response: group into tabs so they don't stack and
// eat vertical space.
function ChartTabs({ specs }) {
  const [active, setActive] = useState(0)
  const current = specs[active]
  return (
    <div className="scrollbar-thin aiko-scroll-x rounded-2xl border border-brand-100 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {specs.map((spec, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setActive(i)}
            className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
              i === active
                ? 'bg-brand-600 text-white'
                : 'bg-brand-50 text-brand-700 hover:bg-brand-100 dark:bg-white/10 dark:text-brand-200'
            }`}
          >
            {spec.title || `Chart ${i + 1}`}
          </button>
        ))}
      </div>
      <ChartBody spec={current} />
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
  if (!text) return { parts: [{ type: 'text', content: '' }], followups: [] }
  const parts = []
  let followups = []
  const fenceRe = /(`{3,})(\w+)?\s*([\s\S]*?)\1/g
  let lastIndex = 0
  let match

  while ((match = fenceRe.exec(text)) !== null) {
    const before = text.slice(lastIndex, match.index)
    if (before.trim()) parts.push({ type: 'text', content: before })

    const lang = (match[2] || '').toLowerCase()
    let handled = false

    if (lang === 'followups') {
      try {
        const parsed = JSON.parse(match[3])
        if (Array.isArray(parsed)) {
          followups = parsed.filter((q) => typeof q === 'string' && q.trim()).slice(0, 3)
          handled = true
        }
      } catch {}
    } else {
      try {
        const parsed = JSON.parse(match[3])
        if (parsed && parsed.type && parsed.data && parsed.xKey && parsed.yKey) {
          parts.push({ type: 'chart', content: parsed })
          handled = true
        } else if (Array.isArray(parsed) && parsed.length && parsed.every((q) => typeof q === 'string' && q.trim())) {
          followups = parsed.filter((q) => typeof q === 'string' && q.trim()).slice(0, 3)
          handled = true
        }
      } catch {}
    }

    if (!handled) parts.push({ type: 'text', content: match[0] })
    lastIndex = fenceRe.lastIndex
  }

  const remaining = text.slice(lastIndex)
  if (remaining.trim()) parts.push({ type: 'text', content: remaining })

  return { parts: parts.length ? parts : [{ type: 'text', content: text }], followups }
}

function stripForSpeech(text) {
  return (text || '').replace(/```[\s\S]*?```/g, '').replace(/[#*`_~>[\]]/g, '').trim()
}

const CHART_HEADING_RE = /^\s{0,3}(#{1,6}\s*)?(\*\*)?chart\s*\d+\s*[:.\-]?\s*.*$/im

// Strips a lone "Chart N: ..." heading line from a text block (the tab label
// already shows this, so keeping it in prose is just duplication).
function stripChartHeadingLine(content) {
  return content
    .split('\n')
    .filter((line) => !CHART_HEADING_RE.test(line.trim()))
    .join('\n')
}

// Pulls every chart part out of the message — wherever it sits — and groups
// them into ONE tabbed unit inserted at the position of the first chart.
// Any inline "Chart N: ..." headings are stripped from the surrounding text
// since the tab labels (from spec.title, or a fallback) cover that already.
function groupChartParts(parts) {
  const charts = parts.filter((p) => p.type === 'chart').map((p) => p.content)
  if (charts.length === 0) return parts
  if (charts.length === 1) {
    // Single chart: leave it exactly where it is, just clean up any heading.
    return parts.map((p) => (p.type === 'text' ? { ...p, content: stripChartHeadingLine(p.content) } : p))
  }

  const result = []
  let inserted = false
  for (const part of parts) {
    if (part.type === 'chart') {
      if (!inserted) {
        result.push({ type: 'chart-tabs', content: charts })
        inserted = true
      }
      continue
    }
    const cleaned = stripChartHeadingLine(part.content)
    if (cleaned.trim()) result.push({ ...part, content: cleaned })
  }
  return result
}

export default function RichResponseCard({ text, animate, streaming, onPrompt }) {
  // While the answer is actively streaming in from the backend, the text
  // itself is already arriving progressively — skip the typewriter so the
  // two effects don't fight each other, and just render it live.
  const revealed = useTypewriter(text || '', !!animate && !streaming)
  const { parts: rawParts, followups } = splitContent(streaming ? (text || '') : revealed)
  const parts = groupChartParts(rawParts)
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
      {parts.map((part, i) => {
        if (part.type === 'chart') return <ChartRenderer key={i} spec={part.content} />
        if (part.type === 'chart-tabs') return <ChartTabs key={i} specs={part.content} />
        return (
          <div key={i} className="scrollbar-thin aiko-scroll-x">
            <div className="prose prose-sm max-w-none dark:prose-invert prose-table:text-xs prose-th:bg-brand-50 prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1 prose-td:border prose-th:border prose-td:border-brand-100">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{part.content}</ReactMarkdown>
            </div>
          </div>
        )
      })}
      {!streaming && followups.length > 0 && onPrompt && (
        <div className="pt-2">
          <div className="border-t border-brand-100 pt-2 text-[11px] font-medium uppercase tracking-wide text-slate-400 dark:border-white/10 dark:text-slate-500">
            Related Queries
          </div>
          <div className="mt-1">
            {followups.map((q, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onPrompt(q)}
                className="block w-full border-b border-brand-100/70 py-2 text-left text-sm text-slate-700 transition hover:text-brand-700 hover:underline focus-ring last:border-b-0 dark:border-white/10 dark:text-slate-200 dark:hover:text-brand-300"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}