import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { env } from './env'

/**
 * Browser Supabase client, used only for authentication. All farm data goes
 * through the FastAPI backend, never directly to the database.
 * `null` when Supabase is not configured, so the UI can say so instead of failing.
 */
export const supabase: SupabaseClient | null =
  env.supabaseUrl && env.supabaseKey
    ? createClient(env.supabaseUrl, env.supabaseKey, {
        auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
      })
    : null
