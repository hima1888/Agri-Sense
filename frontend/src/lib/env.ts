import { z } from 'zod'

const trimmed = z
  .string()
  .optional()
  .transform((v) => (v ?? '').trim())

const EnvSchema = z.object({
  VITE_API_BASE_URL: trimmed.transform((v) => v.replace(/\/+$/, '')),
  VITE_SUPABASE_URL: trimmed.transform((v) => v.replace(/\/+$/, '')),
  VITE_SUPABASE_PUBLISHABLE_KEY: trimmed,
})

const parsed = EnvSchema.safeParse(import.meta.env)

if (!parsed.success) {
  // Fail loudly; a misconfigured env should never be silent.
  throw new Error(`Invalid frontend environment: ${parsed.error.message}`)
}

export const env = {
  /** Empty string means "same origin" (the Vite dev proxy forwards /api to FastAPI). */
  apiBaseUrl: parsed.data.VITE_API_BASE_URL,
  supabaseUrl: parsed.data.VITE_SUPABASE_URL,
  supabaseKey: parsed.data.VITE_SUPABASE_PUBLISHABLE_KEY,
}
