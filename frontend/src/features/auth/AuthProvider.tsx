import type { Session } from '@supabase/supabase-js'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { setAccessTokenProvider, setAccessTokenRefresher } from '@/lib/api-client'
import { supabase } from '@/lib/supabase'
import { AuthContext, type AuthContextValue, type AuthStatus } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState<AuthStatus>(supabase ? 'loading' : 'unconfigured')

  useEffect(() => {
    if (!supabase) return
    const auth = supabase.auth
    // Always ask Supabase for the current token: it refreshes expired tokens itself.
    setAccessTokenProvider(async () => (await auth.getSession()).data.session?.access_token ?? null)
    setAccessTokenRefresher(async () => (await auth.refreshSession()).data.session?.access_token ?? null)

    let active = true
    void auth.getSession().then(({ data }) => {
      if (!active) return
      setSession(data.session)
      setStatus(data.session ? 'signed_in' : 'signed_out')
    })
    const { data } = auth.onAuthStateChange((event, next) => {
      setSession(next)
      setStatus(next ? 'signed_in' : 'signed_out')
      // Never let one user's cached farm data be shown to the next user on this device.
      if (event === 'SIGNED_OUT' || event === 'SIGNED_IN') queryClient.removeQueries({ queryKey: ['me'] })
      if (event === 'SIGNED_OUT') queryClient.removeQueries({ queryKey: ['farms'] })
    })
    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [queryClient])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      user: session?.user ?? null,
      async signIn(email, password) {
        if (!supabase) throw new Error('Authentication is not configured.')
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      },
      async signUp(email, password) {
        if (!supabase) throw new Error('Authentication is not configured.')
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${window.location.origin}/account` },
        })
        if (error) throw error
        return { signedIn: Boolean(data.session) }
      },
      async signOut() {
        if (!supabase) return
        const { error } = await supabase.auth.signOut()
        if (error) throw error
      },
    }),
    [status, session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
