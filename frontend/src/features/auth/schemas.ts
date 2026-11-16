import { z } from 'zod'

export const EmailSchema = z.email('Enter a valid email address.')

/** Mirrors the Supabase Auth password policy (supabase/config.toml), so users see errors before submitting. */
export const NewPasswordSchema = z
  .string()
  .min(8, 'Use at least 8 characters.')
  .regex(/[a-z]/, 'Include a lowercase letter.')
  .regex(/[A-Z]/, 'Include an uppercase letter.')
  .regex(/[0-9]/, 'Include a number.')

export const SignInSchema = z.object({
  email: EmailSchema,
  password: z.string().min(1, 'Enter your password.'),
})

export const SignUpSchema = z
  .object({
    email: EmailSchema,
    password: NewPasswordSchema,
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ['confirm'], message: 'Passwords do not match.' })

export type FieldErrors = Partial<Record<string, string>>

export function fieldErrors(error: z.ZodError): FieldErrors {
  const out: FieldErrors = {}
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? 'form')
    out[key] ??= issue.message
  }
  return out
}

/** Map the server's sign-in errors to plain language; never echo raw internals. */
export function authErrorMessage(err: unknown): string {
  const message = err instanceof Error ? err.message : ''
  if (/invalid login credentials/i.test(message)) return 'Email or password is incorrect.'
  if (/email not confirmed/i.test(message)) return 'Confirm your email address first, using the link we sent.'
  if (/already registered|already been registered/i.test(message)) return 'An account with this email already exists.'
  if (/rate limit|too many/i.test(message)) return 'Too many attempts. Wait a minute and try again.'
  if (/fetch|network/i.test(message)) return 'Cannot reach the sign-in service. Check your connection.'
  if (/password/i.test(message)) return message
  return 'Something went wrong. Please try again.'
}

/** Only allow in-app redirect targets after sign-in (no open redirects). */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard'
}
