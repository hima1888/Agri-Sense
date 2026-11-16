import { DemoNote } from '@/components/ui/demo-note'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { FormAlert } from '@/components/ui/form'
import { Pill, type Tone } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { useGenerate, useRespond, useStored, type Recommendation, type StoredRec } from '@/features/recommendations/api'

const selectCls = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
const TONE: Record<Recommendation['priority'], Tone> = { critical: 'alert', high: 'warn', medium: 'info', low: 'muted' }

function show(v: unknown): string {
  if (typeof v === 'number') return v.toLocaleString()
  return String(v)
}

export function RecommendationsPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>
  const farm = farms.data.items.find((f) => f.id === Number(params.get('farm'))) ?? farms.data.items[0]!
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Recommendations</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Advice</h1>
        </div>
        <select aria-label="Farm" className={selectCls} value={farm.id} onChange={(e) => setParams({ farm: e.target.value })}>
          {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      <FarmAdvice key={farm.id} farmId={farm.id} />
    </div>
  )
}

function FarmAdvice({ farmId }: { farmId: number }) {
  const gen = useGenerate(farmId)
  const stored = useStored(farmId)
  const { mutate } = gen
  useEffect(() => mutate(), [mutate])
  const statusById = new Map((stored.data?.items ?? []).map((s) => [s.id, s]))
  const history = (stored.data?.items ?? []).filter((s) => s.status !== 'pending')

  return (
    <div className="mt-8 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-sage-400">
        <span>
          Rule-based advice from this farm's soil, weather, disease checks and sensors; not a trained model.
          {gen.data && ` Generated ${new Date(gen.data.generated_at).toLocaleString()} · ${gen.data.zones_assessed} zone(s) · ${gen.data.forecast_hours} forecast hours.`}
        </span>
        <button type="button" onClick={() => mutate()} disabled={gen.isPending} className="rounded-full border border-white/10 px-3 py-1.5 text-sage-200 hover:border-white/25 disabled:opacity-50">
          {gen.isPending ? 'Updating…' : 'Refresh advice'}
        </button>
      </div>
      {gen.error && <FormAlert>{gen.error.message}</FormAlert>}
      {gen.data?.uses_simulated_data && <DemoNote>Sensor readings on this farm come from the built-in <strong>simulated</strong> sensors, so this advice shows how the system responds to them.</DemoNote>}
      {gen.data && gen.data.forecast_hours === 0 && <FormAlert>No stored weather forecast: open the dashboard to fetch weather, then refresh. Irrigation timing is less certain without it.</FormAlert>}
      {gen.isPending && !gen.data && <FullPageSpinner />}
      {gen.data && (gen.data.recommendations.length ? (
        <ul className="space-y-4">
          {gen.data.recommendations.map((r) => <RecCard key={`${r.zone_id}-${r.rule}`} r={r} farmId={farmId} stored={r.id != null ? statusById.get(r.id) : undefined} />)}
        </ul>
      ) : <Card title="No advice right now"><p className="text-sm text-sage-300">None of the rules fired for this farm's current data.</p></Card>)}

      <Card title="Decisions">
        {history.length ? (
          <ul className="space-y-1.5 text-sm">
            {history.slice(0, 20).map((h) => (
              <li key={h.id} className="flex justify-between gap-3">
                <span className="text-sage-200">{h.title}</span>
                <span className="whitespace-nowrap text-xs text-sage-400">{h.status}{h.responded_at ? ` · ${new Date(h.responded_at).toLocaleDateString()}` : ''}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-sage-400">No accepted, rejected, applied or expired advice yet.</p>}
      </Card>
    </div>
  )
}

function RecCard({ r, farmId, stored }: { r: Recommendation; farmId: number; stored?: StoredRec }) {
  const respond = useRespond(farmId)
  const [open, setOpen] = useState(false)
  const status = stored?.status ?? 'pending'
  const act = (s: 'accepted' | 'rejected' | 'applied') => r.id != null && respond.mutate({ id: r.id, status: s })
  const steps = Array.isArray(r.action.steps) ? (r.action.steps as string[]) : null
  return (
    <li className="glass rounded-2xl p-5" aria-label={r.title}>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={TONE[r.priority]}>{r.priority}</Pill>
        <Pill>{r.category}</Pill>
        {r.zone_name && <span className="text-xs text-sage-400">{r.zone_name}</span>}
        {r.uses_simulated_data && <Pill tone="warn">simulated data</Pill>}
        {status !== 'pending' && <Pill tone="ok">{status}</Pill>}
      </div>
      <h2 className="mt-3 font-display text-xl text-paper">{r.title}</h2>
      <p className="mt-2 text-sm text-sage-200">{r.rationale}</p>
      {typeof r.action.next_step === 'string' && <p className="mt-2 text-sm text-paper">Next step: {r.action.next_step}</p>}
      {steps && <ul className="mt-2 list-disc pl-5 text-sm text-paper">{steps.map((s) => <li key={s}>{s}</li>)}</ul>}
      <p className="mt-2 text-xs text-sage-400">Confidence {Math.round(r.confidence * 100)} % ({r.confidence_basis})</p>

      <button type="button" className="mt-3 text-xs text-wheat-300 hover:text-paper" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide' : 'Why?'} evidence and limitations
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <table className="w-full text-left text-xs">
            <thead className="text-sage-400"><tr><th className="py-1 pr-3 font-normal">Factor</th><th className="pr-3 font-normal">Value</th><th className="font-normal">Source</th></tr></thead>
            <tbody>
              {r.factors.map((f) => (
                <tr key={f.name} className="border-t border-white/5">
                  <td className="py-1 pr-3 text-sage-200">{f.name}</td>
                  <td className="pr-3 tabular-nums text-paper">{show(f.value)} {f.unit}</td>
                  <td className="text-sage-300">{f.source}{f.simulated ? ' (simulated)' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="list-disc space-y-1 pl-5 text-xs text-sage-400">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      )}

      {r.id != null && (
        <div className="mt-4 flex flex-wrap gap-2">
          {status === 'pending' && (
            <>
              <button type="button" className="rounded-full bg-paper px-3 py-1.5 text-xs text-ink-900 disabled:opacity-50" disabled={respond.isPending} onClick={() => act('accepted')}>Accept</button>
              <button type="button" className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-sage-200 disabled:opacity-50" disabled={respond.isPending} onClick={() => act('rejected')}>Reject</button>
            </>
          )}
          {(status === 'pending' || status === 'accepted') && (
            <button type="button" className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-sage-200 disabled:opacity-50" disabled={respond.isPending} onClick={() => act('applied')}>Mark done</button>
          )}
        </div>
      )}
      {respond.error && <div className="mt-2"><FormAlert>{respond.error.message}</FormAlert></div>}
    </li>
  )
}
