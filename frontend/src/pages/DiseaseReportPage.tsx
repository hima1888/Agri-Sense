import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { z } from 'zod'
import { FormAlert } from '@/components/ui/form'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useDiseaseKnowledge } from '@/features/disease/api'
import { apiGet } from '@/lib/api-client'
import { pct } from '@/lib/percent'
import { useAuthedImage } from '@/lib/use-authed-image'

const Check = z.object({ rule: z.string(), passed: z.boolean(), detail: z.string() })
const RecordSchema = z.object({
  id: z.number(),
  zone_id: z.number().nullable(),
  disease_label: z.string(),
  is_healthy: z.boolean(),
  confidence: z.number(),
  severity: z.string(),
  affected_area_pct: z.number().nullable(),
  top_k: z.array(z.object({ label: z.string(), confidence: z.number() }).passthrough()).nullable(),
  detected_at: z.string(),
  knowledge_key: z.string().nullable().optional(),
  explanation: z
    .object({
      outcome: z.string().optional(),
      part: z.string().optional(),
      crop: z.string().nullable().optional(),
      crop_source: z.string().nullable().optional(),
      model: z.object({ name: z.string(), version: z.string() }).passthrough().nullable().optional(),
      margin: z.number().nullable().optional(),
      checks: z.array(Check).optional(),
      reason: z.string().optional(),
      limitations: z.array(z.string()).optional(),
    })
    .passthrough()
    .nullable(),
})

const OUTCOME: Record<string, string> = {
  possible_disease: 'Possible disease',
  possible_healthy: 'Possibly healthy',
  uncertain: 'Uncertain result',
}

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8 break-inside-avoid">
      <h2 className="font-display text-xl text-paper">
        <span className="mr-2 font-mono text-sm text-sage-400">{n}.</span>
        {title}
      </h2>
      <div className="mt-3 text-sm leading-relaxed text-sage-200">{children}</div>
    </section>
  )
}

const Bullets = ({ items }: { items: string[] }) => (
  <ul className="list-disc space-y-1 pl-5">{items.map((i) => <li key={i}>{i}</li>)}</ul>
)

/** A complete, printable report for one saved disease check: built only from the stored record and the knowledge base. */
export function DiseaseReportPage() {
  const { checkId } = useParams()
  const rec = useQuery({
    queryKey: ['disease-check', checkId],
    queryFn: ({ signal }) => apiGet(`/vision/disease-checks/${checkId}`, RecordSchema, { signal }),
  })
  const img = useAuthedImage(`/vision/disease-checks/${checkId}/image`)
  const k = useDiseaseKnowledge(rec.data?.knowledge_key)

  if (rec.isPending) return <FullPageSpinner />
  if (rec.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>Could not load this disease check: {rec.error.message}</FormAlert></div>

  const r = rec.data
  const e = r.explanation ?? {}
  const outcome = e.outcome ?? (r.is_healthy ? 'possible_healthy' : 'possible_disease')
  const kn = k.data
  let n = 0

  return (
    <div className="print-sheet mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <div className="no-print mb-6 flex flex-wrap items-center gap-2">
        <Link to="/vision?tab=disease" className="text-sm text-sage-400 hover:text-paper">← Back to disease checks</Link>
        <button type="button" className="ml-auto rounded-full bg-paper px-4 py-2 text-sm font-medium text-ink-900" onClick={() => window.print()}>
          Download PDF
        </button>
      </div>
      <p className="no-print mb-6 text-xs text-sage-400">In the print dialog, choose “Save as PDF” as the destination.</p>

      <header className="border-b border-white/10 pb-5">
        <p className="eyebrow">AGRI-SENSE · Plant disease screening report</p>
        <h1 className="mt-2 font-display text-3xl text-paper">{r.disease_label}</h1>
        <p className="mt-1 text-sm text-sage-300">
          {OUTCOME[outcome] ?? outcome} · report #{r.id} · {new Date(r.detected_at).toLocaleString()}
        </p>
      </header>

      <Section n={++n} title="Result summary">
        <div className="grid gap-6 sm:grid-cols-[14rem_1fr]">
          {img && <img src={img} alt={`Photo checked: ${r.disease_label}`} className="w-56 rounded-lg border border-white/10 object-cover" />}
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-sage-400">Prediction</dt><dd className="text-paper">{r.disease_label}</dd>
            <dt className="text-sage-400">Result</dt><dd>{OUTCOME[outcome] ?? outcome}</dd>
            <dt className="text-sage-400">Model confidence</dt><dd>{pct(r.confidence)}{e.margin != null && ` (lead over 2nd choice: ${(e.margin * 100).toFixed(1)} points)`}</dd>
            <dt className="text-sage-400">Crop</dt><dd>{e.crop ?? '—'}{e.crop_source ? ` (from ${e.crop_source})` : ''}</dd>
            <dt className="text-sage-400">Photo of</dt><dd>{e.part === 'fruit' ? 'Fruit' : 'Leaf'}</dd>
            {!r.is_healthy && <><dt className="text-sage-400">Severity</dt><dd>{e.part === 'fruit' ? 'not estimated for fruit photos' : <>{r.severity}{r.affected_area_pct != null && ` · about ${r.affected_area_pct} % of the leaf discoloured (colour estimate)`}</>}</dd></>}
            <dt className="text-sage-400">Conclusion</dt><dd>{e.reason ?? '—'}</dd>
          </dl>
        </div>
      </Section>

      <Section n={++n} title="How the prediction was made">
        <p>
          The photo was analysed by <strong>{e.model?.name ?? 'the disease model'}</strong>{e.model?.version ? ` (${e.model.version})` : ''}, an image
          classifier run on the AGRI-SENSE server with ONNX Runtime. The model gives a probability for each disease it knows; the app accepts an
          answer only if every check below passes.
        </p>
        {e.checks && e.checks.length > 0 && (
          <table className="mt-3 w-full text-left text-xs">
            <thead className="text-sage-400"><tr><th className="py-1 pr-3">Check</th><th className="py-1 pr-3">Result</th><th className="py-1">Detail</th></tr></thead>
            <tbody>
              {e.checks.map((c) => (
                <tr key={c.rule} className="border-t border-white/5">
                  <td className="py-1 pr-3">{c.rule.replaceAll('_', ' ')}</td>
                  <td className="py-1 pr-3">{c.passed ? 'passed' : 'failed'}</td>
                  <td className="py-1">{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {r.top_k && r.top_k.length > 0 && (
          <>
            <p className="mt-4 text-sage-400">Most likely classes according to the model:</p>
            <ol className="mt-1 list-decimal space-y-0.5 pl-5">{r.top_k.map((c) => <li key={c.label}>{c.label}: {pct(c.confidence)}</li>)}</ol>
          </>
        )}
      </Section>

      {kn && (
        <>
          <Section n={++n} title={`About ${kn.name}`}>
            <p>{kn.what}</p>
            <p className="mt-2 text-sage-400">Cause: <i>{kn.pathogen}</i> ({kn.pathogen_type}). Crops affected: {kn.crops.join(', ')}.</p>
          </Section>
          <Section n={++n} title="Symptoms to look for"><Bullets items={kn.symptoms} /></Section>
          <Section n={++n} title="Why it occurs and how it spreads">
            <p><strong>Why it occurs:</strong> {kn.causes}</p>
            <p className="mt-2"><strong>Favourable conditions:</strong> {kn.conditions}</p>
            <p className="mt-2"><strong>How it spreads:</strong> {kn.spread}</p>
          </Section>
          <Section n={++n} title="How to overcome it: action plan">
            <p className="font-medium text-paper">Step 1. Confirm</p>
            <p>Check more leaves for the symptoms above and confirm with an agronomist or extension officer before any treatment.</p>
            <p className="mt-3 font-medium text-paper">Step 2. Manage now</p>
            <Bullets items={kn.management} />
            <p className="mt-3 font-medium text-paper">Step 3. Prevent it coming back</p>
            <Bullets items={kn.prevention} />
            <p className="mt-3 font-medium text-paper">Step 4. Sustainable practices</p>
            <Bullets items={kn.sustainable} />
            <p className="mt-3 font-medium text-paper">Step 5. Keep monitoring</p>
            <Bullets items={kn.monitor} />
          </Section>
          <Section n={++n} title="When to seek expert advice"><p>{kn.seek_advice}</p></Section>
        </>
      )}
      {r.knowledge_key && k.isPending && <p className="mt-8 text-sm text-sage-400">Loading disease information…</p>}
      {!r.knowledge_key && outcome === 'possible_healthy' && (
        <Section n={++n} title="What to do next">
          <Bullets items={['Re-check every 1–2 weeks and after long wet or humid spells', 'Look at leaf undersides and the lower canopy, where many diseases start', 'Keep rotating crops, remove infected residue and water at the base of plants']} />
        </Section>
      )}
      {outcome === 'uncertain' && (
        <Section n={++n} title="What to do next">
          <p>The model was not confident enough to name a disease. Take a new photo of one leaf in good light against a plain background, or ask an agronomist.</p>
        </Section>
      )}

      <Section n={n + 1} title="Limitations">
        <Bullets items={e.limitations ?? []} />
        {kn && <p className="mt-2 text-xs text-sage-400">Disease information: {kn.source}</p>}
      </Section>

      <footer className="mt-10 border-t border-white/10 pt-4 text-xs text-sage-400">
        Generated by AGRI-SENSE from saved check #{r.id}. A screening aid, not a diagnosis.
      </footer>
    </div>
  )
}
