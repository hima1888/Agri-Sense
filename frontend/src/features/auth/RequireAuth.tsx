import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useStillCurrent } from '@/lib/use-still-current'
import { useAuth } from './auth-context'

export function AuthUnavailable() {
  return (
    <div className="mx-auto max-w-md px-4 py-24 text-center sm:px-6">
      <p className="eyebrow">Sign-in unavailable</p>
      <h1 className="mt-3 font-display text-3xl font-light text-paper">Authentication is not configured.</h1>
      <p className="mt-4 text-sm text-sage-300">
        Set <code className="font-mono">VITE_SUPABASE_URL</code> and{' '}
        <code className="font-mono">VITE_SUPABASE_PUBLISHABLE_KEY</code> for the frontend.
      </p>
    </div>
  )
}

export function FullPageSpinner() {
  return (
    <div className="flex min-h-[50dvh] items-center justify-center" role="status" aria-label="Loading">
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-white/15 border-t-wheat-300" />
    </div>
  )
}

/** Routes inside this guard require a signed-in user; others are sent to /login and returned afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()
  const { current, ownPath } = useStillCurrent()
  if (!current) return null // outgoing page during a transition: never redirect from here
  if (status === 'unconfigured') return <AuthUnavailable />
  if (status === 'loading') return <FullPageSpinner />
  if (status === 'signed_out') {
    const next = encodeURIComponent(ownPath + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return <>{children}</>
}
