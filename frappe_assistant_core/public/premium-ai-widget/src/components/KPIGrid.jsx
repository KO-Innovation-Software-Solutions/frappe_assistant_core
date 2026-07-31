import { KPI } from './KPI'

export default function KPIGrid() {
  return (
    <div className="grid grid-cols-3 gap-3 max-sm:grid-cols-1">
      <KPI label="Tasks Completed" value="148" delta="+12.4%" tone="success" />
      <KPI label="Response Speed" value="1.3s" delta="Fast" tone="success" />
      <KPI label="Accuracy" value="98.1%" delta="Stable" tone="success" />
    </div>
  )
}