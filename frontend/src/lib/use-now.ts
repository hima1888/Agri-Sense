import { useEffect, useState } from 'react'

/** Current time in ms, re-rendering every `intervalMs` (for "2 min ago" labels and staleness). */
export function useNow(intervalMs = 5_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}
