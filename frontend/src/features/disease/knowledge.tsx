import { useState } from 'react'
import { Pill } from '@/components/ui/primitives'
import { useDiseaseKnowledge, type HealthyGuidance, type Knowledge } from './api'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="eyebrow">{title}</p>
      <div className="mt-1.5 text-sm text-sage-200">{children}</div>
    </div>
  )
}

function List({ items }: { items: string[] }) {
  return <ul className="list-disc space-y-1 pl-5">{items.map((i) => <li key={i}>{i}</li>)}</ul>
}

/** Guidance for a disease, rendered from the backend's structured knowledge entry (never written in the UI). */
export function KnowledgePanel({ k }: { k: Knowledge }) {
  return (
    <section aria-label={`About ${k.name}`} className="space-y-4 rounded-xl border border-white/10 bg-ink-950/40 p-4">
      <div>
        <p className="font-display text-xl text-paper">{k.name}</p>
        <p className="mt-0.5 text-xs text-sage-400">
          <i>{k.pathogen}</i> · {k.pathogen_type} · crops: {k.crops.join(', ')}
        </p>
      </div>
      <Section title="What is this?">{k.what}</Section>
      <Section title="Symptoms"><List items={k.symptoms} /></Section>
      <div className="grid gap-4 sm:grid-cols-2">
        <Section title="Why it occurs">{k.causes}</Section>
        <Section title="Environmental conditions">{k.conditions}</Section>
      </div>
      <Section title="How it spreads">{k.spread}</Section>
      <Section title="How to manage it"><List items={k.management} /></Section>
      <div className="grid gap-4 sm:grid-cols-2">
        <Section title="Prevention"><List items={k.prevention} /></Section>
        <Section title="Sustainable practices"><List items={k.sustainable} /></Section>
      </div>
      <Section title="What to monitor"><List items={k.monitor} /></Section>
      <Section title="When to seek expert advice">{k.seek_advice}</Section>
      <p className="text-xs text-sage-400">
        {!k.reviewed && <Pill tone="muted">not agronomist-reviewed</Pill>} {k.source}
      </p>
    </section>
  )
}

export function HealthyPanel({ g }: { g: HealthyGuidance }) {
  return (
    <section aria-label="Healthy result guidance" className="space-y-4 rounded-xl border border-white/10 bg-ink-950/40 p-4">
      <Section title="What this means">{g.what}</Section>
      <Section title="What to monitor"><List items={g.monitor} /></Section>
      <Section title="Prevention"><List items={g.prevention} /></Section>
      <Section title="When to seek expert advice">{g.seek_advice}</Section>
      <p className="text-xs text-sage-400">{g.source}</p>
    </section>
  )
}

/** Loads an entry by key (saved history, the twin) with loading, error and empty states. */
export function KnowledgeByKey({ k }: { k: string }) {
  const q = useDiseaseKnowledge(k)
  if (q.isLoading) return <p className="text-sm text-sage-400" role="status">Loading disease information…</p>
  if (q.error) return <p className="text-sm text-signal-alert" role="alert">Could not load disease information: {q.error.message}</p>
  return q.data ? <KnowledgePanel k={q.data} /> : null
}

export function KnowledgeToggle({ k, label = 'About this disease' }: { k: string; label?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button type="button" className="text-wheat-300 hover:underline" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? 'Hide' : label}
      </button>
      {open && <div className="mt-2"><KnowledgeByKey k={k} /></div>}
    </div>
  )
}
