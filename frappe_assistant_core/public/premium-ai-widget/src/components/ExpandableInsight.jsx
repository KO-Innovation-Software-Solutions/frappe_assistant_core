export default function ExpandableInsight() {
  const rows = [
    ['Chat Engine', 'Healthy', '84%', '↑ 8.2%'],
    ['Vision Upload', 'Active', '59%', '↑ 4.9%'],
    ['Voice Mode', 'Monitoring', '37%', '↓ 1.1%']
  ]

  return (
    <details open className="group rounded-2xl border border-brand-100 bg-white/70 p-3 transition-all open:shadow-sm dark:border-white/10 dark:bg-white/5">
      <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium text-brand-700 dark:text-brand-200">
        <span>Performance dashboard</span>
        <span className="transition-transform group-open:rotate-180">⌄</span>
      </summary>

      <div className="mt-3 overflow-hidden rounded-xl border border-brand-100 dark:border-white/10">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-brand-50/80 text-slate-600 dark:bg-white/5 dark:text-slate-300">
            <tr>
              <th className="px-3 py-2 font-medium">Module</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Usage</th>
              <th className="px-3 py-2 font-medium">Trend</th>
            </tr>
          </thead>
          <tbody className="bg-white/70 dark:bg-transparent">
            {rows.map((row) => (
              <tr key={row[0]} className="border-t border-brand-100/70 dark:border-white/10">
                <td className="px-3 py-2 text-slate-700 dark:text-slate-200">{row[0]}</td>
                <td className="px-3 py-2">
                  <span className="rounded-full bg-brand-100 px-2 py-1 text-xs font-medium text-brand-700 dark:bg-brand-500/20 dark:text-brand-200">{row[1]}</span>
                </td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-200">{row[2]}</td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-200">{row[3]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}