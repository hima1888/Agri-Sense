import { motion } from 'framer-motion'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { SkyBackground } from '@/components/ambient/SkyBackground'
import { FormAlert, SubmitButton, TextField } from '@/components/ui/form'
import { useAuth } from '@/features/auth/auth-context'
import { AuthUnavailable, FullPageSpinner } from '@/features/auth/RequireAuth'
import { useStillCurrent } from '@/lib/use-still-current'
import {
  authErrorMessage,
  fieldErrors,
  safeNext,
  SignInSchema,
  SignUpSchema,
  type FieldErrors,
} from '@/features/auth/schemas'

function AuthShell({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section className="relative isolate -mt-16 flex min-h-dvh items-center justify-center overflow-hidden px-4 pb-16 pt-28">
      <SkyBackground className="opacity-70" />
      <motion.div
        className="glass relative w-full max-w-sm rounded-2xl p-7 sm:p-8"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="mt-3 font-display text-3xl font-light text-paper">{title}</h1>
        <div className="mt-7">{children}</div>
      </motion.div>
    </section>
  )
}

function formValues(e: FormEvent<HTMLFormElement>): Record<string, string> {
  return Object.fromEntries(
    [...new FormData(e.currentTarget).entries()].map(([k, v]) => [k, typeof v === 'string' ? v.trim() : '']),
  )
}

export function LoginPage() {
  const { status, signIn } = useAuth()
  const { current } = useStillCurrent()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const next = safeNext(params.get('next'))
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (status === 'unconfigured') return <AuthUnavailable />
  if (status === 'loading') return <FullPageSpinner />
  if (status === 'signed_in' && !busy && current) return <Navigate to={next} replace />

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setFormError(null)
    const values = formValues(e)
    // Passwords are never trimmed.
    values.password = String(new FormData(e.currentTarget).get('password') ?? '')
    const parsed = SignInSchema.safeParse(values)
    if (!parsed.success) return setErrors(fieldErrors(parsed.error))
    setErrors({})
    setBusy(true)
    try {
      await signIn(parsed.data.email, parsed.data.password)
      navigate(next, { replace: true })
    } catch (err) {
      setFormError(authErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell eyebrow="Welcome back" title="Sign in">
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {formError && <FormAlert>{formError}</FormAlert>}
        <TextField label="Email" name="email" type="email" autoComplete="email" error={errors.email} />
        <TextField
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          error={errors.password}
        />
        <SubmitButton busy={busy}>Sign in</SubmitButton>
      </form>
      <p className="mt-6 text-center text-sm text-sage-300">
        New to AGRI-SENSE?{' '}
        <Link to={`/signup${params.get('next') ? `?next=${encodeURIComponent(next)}` : ''}`} className="text-wheat-300 hover:underline">
          Create an account
        </Link>
      </p>
    </AuthShell>
  )
}

export function SignupPage() {
  const { status, signUp } = useAuth()
  const { current } = useStillCurrent()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const next = safeNext(params.get('next'))
  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [pendingEmail, setPendingEmail] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (status === 'unconfigured') return <AuthUnavailable />
  if (status === 'loading') return <FullPageSpinner />
  if (status === 'signed_in' && !busy && current) return <Navigate to={next} replace />

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setFormError(null)
    const data = new FormData(e.currentTarget)
    const parsed = SignUpSchema.safeParse({
      email: String(data.get('email') ?? '').trim(),
      password: String(data.get('password') ?? ''),
      confirm: String(data.get('confirm') ?? ''),
    })
    if (!parsed.success) return setErrors(fieldErrors(parsed.error))
    setErrors({})
    setBusy(true)
    try {
      const result = await signUp(parsed.data.email, parsed.data.password)
      if (result.signedIn) navigate(next, { replace: true })
      else setPendingEmail(parsed.data.email)
    } catch (err) {
      setFormError(authErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (pendingEmail) {
    return (
      <AuthShell eyebrow="Almost there" title="Check your email">
        <FormAlert tone="ok">
          We sent a confirmation link to <strong>{pendingEmail}</strong>. Open it to activate your account.
        </FormAlert>
        <Link to="/login" className="mt-6 block text-center text-sm text-wheat-300 hover:underline">
          Back to sign in
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell eyebrow="Get started" title="Create your account">
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {formError && <FormAlert>{formError}</FormAlert>}
        <TextField label="Email" name="email" type="email" autoComplete="email" error={errors.email} />
        <TextField
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          error={errors.password}
          hint="At least 8 characters, with upper- and lowercase letters and a number."
        />
        <TextField
          label="Confirm password"
          name="confirm"
          type="password"
          autoComplete="new-password"
          error={errors.confirm}
        />
        <SubmitButton busy={busy}>Create account</SubmitButton>
      </form>
      <p className="mt-6 text-center text-sm text-sage-300">
        Already have an account?{' '}
        <Link to="/login" className="text-wheat-300 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}
