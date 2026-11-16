import { useEffect, useMemo } from 'react'

/** Object URL for a local File (revoked when the file changes or on unmount). */
export function useFilePreview(file: File | null): string | null {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url)
    },
    [url],
  )
  return url
}
