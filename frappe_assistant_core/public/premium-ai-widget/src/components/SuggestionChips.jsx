export default function SuggestionChips({ onPrompt }) {
  const chips = ['Show revenue dashboard', 'Summarize this week', 'Create a forecast']

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {chips.map((chip) => (
        <button
          key={chip}
          type="button"
          onClick={() => onPrompt(chip)}
          className="rounded-full border border-brand-200 bg-white/80 px-3 py-1.5 text-xs font-medium text-brand-700 transition hover:bg-brand-50 focus-ring dark:border-brand-400/20 dark:bg-white/10 dark:text-brand-200 dark:hover:bg-brand-500/20"
        >
          {chip}
        </button>
      ))}
    </div>
  )
}