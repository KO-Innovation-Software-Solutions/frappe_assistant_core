export default function MessageBubble({ text, attachment }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] overflow-hidden rounded-2xl rounded-br-md bg-gradient-to-br from-brand-600 to-fuchsia-500 shadow-md">
        {attachment && (
          attachment.is_image ? (
            <img src={attachment.file_url} alt={attachment.file_name} className="block max-h-48 w-full object-cover" />
          ) : (
            <div className="flex items-center gap-2 border-b border-white/20 bg-black/10 px-3 py-2 text-xs text-white">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
              <span className="truncate">{attachment.file_name}</span>
            </div>
          )
        )}
        {text && <div className="px-4 py-2.5 text-sm text-white">{text}</div>}
      </div>
    </div>
  )
}