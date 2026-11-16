import type { ReactNode } from 'react'

export type Tone = 'ok' | 'warn' | 'alert' | 'muted' | 'info'

const DOT: Record<Tone, string> = {
  ok: 'bg-signal-ok',
  warn: 'bg-signal-warn',
  alert: 'bg-signal-alert',
  muted: 'bg-sage-400/60',
  info: 'bg-sky-300',
}

const PILL: Record<Tone, string> = {
  ok: 'border-moss-400/30 text-moss-300 bg-moss-500/10',
  warn: 'border-wheat-400/30 text-wheat-300 bg-wheat-400/10',
  alert: 'border-signal-alert/30 text-signal-alert bg-signal-alert/10',
  muted: 'border-white/10 text-sage-300 bg-white/5',
  info: 'border-sky-300/30 text-sky-200 bg-sky-300/10',
}

export function StatusDot({ tone, pulse = false }: { tone: Tone; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2">
      {pulse && <span className={`absolute inset-0 rounded-full ${DOT[tone]} animate-pulse-soft`} />}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${DOT[tone]}`} />
    </span>
  )
}

export function Pill({ tone = 'muted', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[0.68rem] uppercase tracking-wider ${PILL[tone]}`}
    >
      {children}
    </span>
  )
}

export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#14221a" stroke="rgb(255 255 255 / 0.08)" />
        <path d="M16 25c0-7 3-12 9-14-1 7-4 11-9 14Z" fill="#8fbf7a" />
        <path d="M16 25c0-6-3-10-8-12 1 6 3 10 8 12Z" fill="#d8c48a" />
        <circle cx="16" cy="8" r="2" fill="#9cc7d8" />
      </svg>
      <span className="font-mono text-sm font-medium tracking-[0.24em] text-paper">AGRI·SENSE</span>
    </span>
  )
}

export function SectionHeading({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string
  title: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="max-w-2xl">
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="mt-3 font-display text-3xl font-light leading-tight text-paper sm:text-4xl">{title}</h2>
      {children && <p className="mt-4 text-base leading-relaxed text-sage-300">{children}</p>}
    </div>
  )
}
