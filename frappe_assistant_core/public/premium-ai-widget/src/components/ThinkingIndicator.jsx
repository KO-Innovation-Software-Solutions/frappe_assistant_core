export default function ThinkingIndicator({ stage }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <svg width="40" height="24" viewBox="0 0 54 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="shrink-0 animate-truckMove">
        <rect x="1" y="6" width="30" height="20" rx="2" stroke="#7c3aed" strokeWidth="1.5" fill="none" />
        <path d="M31 14 L31 26 L52 26 L52 14 L46 6 L31 6 Z" stroke="#7c3aed" strokeWidth="1.5" fill="none" strokeLinejoin="round" />
        <path d="M33 13 L33 8 L45 8 L50 13 Z" stroke="#7c3aed" strokeWidth="1.2" fill="none" strokeLinejoin="round" />
        <circle cx="11" cy="27" r="4.5" stroke="#7c3aed" strokeWidth="1.5" fill="none" />
        <circle cx="41" cy="27" r="4.5" stroke="#7c3aed" strokeWidth="1.5" fill="none" />
      </svg>
      <span className="flex-1 truncate text-xs text-slate-500 dark:text-slate-300">{stage || 'Thinking…'}</span>
      <span className="flex shrink-0 gap-0.5">
        <span className="h-1 w-1 rounded-full bg-brand-400 animate-dotBounce"></span>
        <span className="h-1 w-1 rounded-full bg-brand-400 animate-dotBounce [animation-delay:0.15s]"></span>
        <span className="h-1 w-1 rounded-full bg-brand-400 animate-dotBounce [animation-delay:0.3s]"></span>
      </span>
    </div>
  )
}