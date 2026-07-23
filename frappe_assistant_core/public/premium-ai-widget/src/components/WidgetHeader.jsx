import IconButton from './IconButton'
import NewChatIcon from './icons/NewChatIcon'
import HistoryIcon from './icons/HistoryIcon'
import FullscreenIcon from './icons/FullscreenIcon'
import CloseIcon from './icons/CloseIcon'

export default function WidgetHeader({ onNewChat, onHistory, onFullscreen, onClose }) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-brand-100/80 bg-gradient-to-r from-white/70 to-brand-50/60 px-4 py-3 dark:border-white/10 dark:from-white/5 dark:to-brand-500/10">
      <div>
        <div className="text-sm font-semibold text-slate-900 dark:text-white">AIKO</div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-300">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulseSoft"></span>
          <span>Online</span>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <IconButton label="New Chat" onClick={onNewChat}><NewChatIcon /></IconButton>
        <IconButton label="History" onClick={onHistory}><HistoryIcon /></IconButton>
        <IconButton label="Fullscreen" onClick={onFullscreen}><FullscreenIcon /></IconButton>
        <IconButton label="Close" onClick={onClose}><CloseIcon /></IconButton>
      </div>
    </header>
  )
}