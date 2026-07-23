export function KPI({ label, value, delta, tone }) {
  const toneColors = {
    success: 'text-emerald-600 dark:text-emerald-400',
    warning: 'text-amber-600 dark:text-amber-400',
    danger: 'text-red-600 dark:text-red-400',
  }

  return (
    <div className="rounded-2xl border border-brand-100 bg-white/80 p-3 backdrop-blur-sm dark:border-white/10 dark:bg-white/5">
      <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-1 text-xl font-bold text-slate-900 dark:text-white">{value}</div>
      <div className={`mt-0.5 text-xs font-medium ${toneColors[tone] || 'text-slate-500'}`}>{delta}</div>
    </div>
  )
}
