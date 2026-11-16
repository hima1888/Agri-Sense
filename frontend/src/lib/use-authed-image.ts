import { useEffect, useState } from 'react'
import { apiBlobUrl } from './api-client'

/** Authenticated image from the API as an object URL (revoked on change/unmount). */
export function useAuthedImage(path: string): string | null {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    const ctl = new AbortController()
    let made: string | null = null
    apiBlobUrl(path, ctl.signal)
      .then((u) => {
        made = u
        setUrl(u)
      })
      .catch(() => undefined)
    return () => {
      ctl.abort()
      if (made) URL.revokeObjectURL(made)
    }
  }, [path])
  return url
}
