import { useEffect } from 'react'

export default function useAutoScroll(ref, deps = []) {
  useEffect(() => {
    if (!ref?.current) return
    ref.current.scrollTo({
      top: ref.current.scrollHeight,
      behavior: 'smooth'
    })
  }, deps)
}