import type { ReactNode } from 'react'

/** Neutral "demo mode" note for simulated data: clearly labelled, not styled as an error. */
export function DemoNote({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="flex items-start gap-2.5 rounded-lg border border-sky-300/20 bg-sky-400/5 px-3.5 py-2.5 text-sm text-sage-200">
      <span className="mt-0.5 shrink-0 rounded-full border border-sky-300/30 px-2 py-px font-mono text-[0.65rem] uppercase tracking-wider text-sky-200">Demo mode</span>
      <span>{children}</span>
    </div>
  )
}
