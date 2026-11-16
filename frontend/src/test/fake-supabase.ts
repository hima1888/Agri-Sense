import type { AuthChangeEvent, Session } from '@supabase/supabase-js'
import { vi } from 'vitest'

type Listener = (event: AuthChangeEvent, session: Session | null) => void

export const VALID_PASSWORD = 'Correct-horse1'

export function makeSession(email: string): Session {
  return {
    access_token: `token-for-${email}`,
    refresh_token: 'refresh',
    expires_in: 3600,
    token_type: 'bearer',
    user: { id: '6f1c7a52-6a8e-4d55-9a49-0c1b2d3e4f50', email, aud: 'authenticated', app_metadata: {}, user_metadata: {}, created_at: '' },
  } as Session
}

/** In-memory stand-in for supabase.auth with the same call shapes the app uses. */
export function createFakeSupabase() {
  let session: Session | null = null
  const listeners = new Set<Listener>()
  const emit = (event: AuthChangeEvent) => listeners.forEach((l) => l(event, session))

  const auth = {
    getSession: vi.fn(async () => ({ data: { session }, error: null })),
    onAuthStateChange: vi.fn((cb: Listener) => {
      listeners.add(cb)
      return { data: { subscription: { unsubscribe: () => listeners.delete(cb) } } }
    }),
    signInWithPassword: vi.fn(async ({ email, password }: { email: string; password: string }) => {
      if (password !== VALID_PASSWORD) return { data: { session: null }, error: new Error('Invalid login credentials') }
      session = makeSession(email)
      emit('SIGNED_IN')
      return { data: { session }, error: null }
    }),
    signUp: vi.fn(async ({ email }: { email: string; password: string }) => {
      if (email.startsWith('taken')) return { data: { session: null }, error: new Error('User already registered') }
      if (email.startsWith('confirm')) return { data: { session: null, user: {} }, error: null }
      session = makeSession(email)
      emit('SIGNED_IN')
      return { data: { session }, error: null }
    }),
    refreshSession: vi.fn(async () => {
      if (session) session = { ...session, access_token: `${session.access_token}-refreshed` }
      return { data: { session }, error: null }
    }),
    signOut: vi.fn(async () => {
      session = null
      emit('SIGNED_OUT')
      return { error: null }
    }),
  }

  return {
    supabase: { auth },
    auth,
    signInAs(email: string) {
      session = makeSession(email)
    },
    reset() {
      session = null
      listeners.clear()
      Object.values(auth).forEach((fn) => fn.mockClear())
    },
  }
}
