import { useEffect } from 'react'

export default function useKeyboardShortcuts({ onClose, onFullscreen, onNewChat }) {
  useEffect(() => {
    const onKeyDown = (event) => {
      const mod = event.metaKey || event.ctrlKey

      if (mod && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        onNewChat?.()
      }

      if (event.key === 'Escape') {
        onClose?.()
      }

      if (mod && event.key.toLowerCase() === 'f') {
        event.preventDefault()
        onFullscreen?.()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, onFullscreen, onNewChat])
}