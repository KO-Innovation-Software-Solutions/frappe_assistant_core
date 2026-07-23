export default function IconButton({ label, children, onClick }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="grid h-9 w-9 place-items-center rounded-full text-slate-500 transition-all duration-200 hover:bg-brand-50 hover:text-brand-700 focus-ring dark:text-slate-300 dark:hover:bg-brand-500/20"
    >
      {children}
    </button>
  )
}
