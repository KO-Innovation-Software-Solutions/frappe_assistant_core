export default function AssistantGlassCard({ children }) {
  return (
    <div className="rounded-[18px] border border-white/60 bg-white/65 p-3 backdrop-blur-xl shadow-glass dark:border-white/10 dark:bg-white/10">
      {children}
    </div>
  )
}
