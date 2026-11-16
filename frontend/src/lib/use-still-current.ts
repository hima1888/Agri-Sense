import { useState } from 'react'
import { useLocation } from 'react-router'

/**
 * True while the page that called this hook is still the current route.
 *
 * During a page transition the outgoing page stays mounted (AnimatePresence) but
 * already sees the NEW location. A page that redirects based on auth state must not
 * act in that window, or it would redirect away from the page being navigated to
 * (and could loop forever). Gate every <Navigate> in such pages with this hook.
 */
export function useStillCurrent(): { current: boolean; ownPath: string } {
  const location = useLocation()
  const [ownPath] = useState(location.pathname)
  return { current: location.pathname === ownPath, ownPath }
}
