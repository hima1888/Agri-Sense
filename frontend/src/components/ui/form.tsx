import { useId, type InputHTMLAttributes, type ReactNode } from 'react'

export function TextField({
  label,
  error,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: string }) {
  const id = useId()
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  return (
    <div>
      <label htmlFor={id} className="block text-sm text-sage-200">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className={`mt-1.5 block w-full rounded-lg border bg-ink-950/60 px-3.5 py-2.5 text-sm text-paper placeholder:text-sage-400/60 transition-colors focus:outline-none focus:ring-2 focus:ring-wheat-300/40 ${
          error ? 'border-signal-alert/60' : 'border-white/10 focus:border-wheat-300/50'
        }`}
        {...props}
      />
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-xs text-signal-alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-sage-400">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export function SubmitButton({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-paper px-5 py-2.5 text-sm font-medium text-ink-900 transition-opacity disabled:opacity-60"
    >
      {busy && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-900/30 border-t-ink-900" />}
      {children}
    </button>
  )
}

export function FormAlert({ tone = 'alert', children }: { tone?: 'alert' | 'ok'; children: ReactNode }) {
  const cls =
    tone === 'ok'
      ? 'border-moss-400/30 bg-moss-500/10 text-moss-300'
      : 'border-signal-alert/30 bg-signal-alert/10 text-paper'
  return (
    <div role={tone === 'alert' ? 'alert' : 'status'} className={`rounded-lg border px-3.5 py-2.5 text-sm ${cls}`}>
      {children}
    </div>
  )
}
