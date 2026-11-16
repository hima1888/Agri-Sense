import { useSearchParams } from 'react-router'
import { FormAlert } from '@/components/ui/form'
import { Pill } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList, useZoneList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { useEnrollment, useFarmFl, useForecast, type FlRun } from '@/features/federated/api'

const sel = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
const FEATURE: Record<string, string> = {
  moisture: 'Soil moisture now', air_temperature: 'Air temperature', humidity: 'Humidity', light: 'Light',
  rainfall: 'Rainfall sensor', hour_sin: 'Time of day (sin)', hour_cos: 'Time of day (cos)',
}

export function FederatedPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  const farmId = farms.data?.items.find((f) => f.id === Number(params.get('farm')))?.id ?? farms.data?.items[0]?.id ?? null
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length || farmId == null) return <div className="px-4 py-14"><EmptyFarms /></div>
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Federated learning</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Shared learning</h1>
        </div>
        <select aria-label="Farm" className={sel} value={farmId} onChange={(e) => setParams({ farm: e.target.value })}>
          {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      <FarmFederated key={farmId} farmId={farmId} />
    </div>
  )
}

function FarmFederated({ farmId }: { farmId: number }) {
  const fl = useFarmFl(farmId)
  const enrollment = useEnrollment(farmId)
  const zones = useZoneList(farmId)
  if (fl.isPending) return <div className="mt-10"><FullPageSpinner /></div>
  if (fl.isError) return <div className="mt-8"><FormAlert>{fl.error.message}</FormAlert></div>
  const v = fl.data
  const active = v.enrollment?.status === 'active'
  const latest = v.runs.find((r) => r.status === 'completed')
  return (
    <div className="mt-8 space-y-5">
      <Card
        title="Participation"
        action={
          <button type="button" disabled={enrollment.isPending} onClick={() => enrollment.mutate(active ? 'leave' : 'enroll')}
            className={`rounded-full px-3 py-1.5 text-xs disabled:opacity-50 ${active ? 'border border-white/10 text-sage-200' : 'bg-paper text-ink-900'}`}>
            {active ? 'Leave federation' : 'Join federation'}
          </button>
        }
      >
        <div className="space-y-2 text-sm">
          <p className="flex items-center gap-2">
            <Pill tone={active ? 'ok' : 'muted'}>{v.enrollment ? v.enrollment.status : 'not enrolled'}</Pill>
            <span className="text-sage-300">{v.local_samples} usable hourly samples on this farm (a run needs {v.min_samples}).</span>
          </p>
          <p className="text-sage-200">Shared with the federation: <span className="text-paper">{v.shared}</span>.</p>
          <p className="text-sage-200">Never shared: <span className="text-paper">{v.not_shared}</span>.</p>
          <p className="text-xs text-sage-400">The model learns how soil moisture changes over the next 6 hours from on-farm sensors. Each farm trains on its own data; only model weights are averaged (FedAvg).</p>
          {v.uses_simulated_data && <FormAlert>This farm's sensor data is <strong>SIMULATED</strong>. Training on it demonstrates the method only.</FormAlert>}
          {enrollment.error && <FormAlert>{enrollment.error.message}</FormAlert>}
        </div>
      </Card>

      {latest ? <LatestRun run={latest} /> : (
        <Card title="Latest model"><p className="text-sm text-sage-300">{v.runs[0]?.reason ?? 'No federated run has completed yet. An administrator starts runs once at least two farms have joined.'}</p></Card>
      )}

      {zones.data && zones.data.items.length > 0 && (
        <Card title="6-hour moisture forecast">
          <ul className="space-y-3">{zones.data.items.map((z) => <ZoneForecast key={z.id} zoneId={z.id} name={z.name} />)}</ul>
        </Card>
      )}

      <Card title="Runs">
        {v.runs.length ? (
          <ul className="space-y-1.5 text-sm">
            {v.runs.map((r) => (
              <li key={r.id} className="flex flex-wrap justify-between gap-2">
                <span className="text-sage-200">Run {r.id} · {r.rounds} rounds · {r.clients ?? 0} farm(s){r.participated ? ' · this farm took part' : ''}</span>
                <span className="text-xs text-sage-400">{r.status}{r.completed_at ? ` · ${new Date(r.completed_at).toLocaleString()}` : ''}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-sage-400">No runs yet.</p>}
      </Card>

      <Card title="Limitations">
        <ul className="list-disc space-y-1 pl-5 text-xs text-sage-400">{v.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Card>
    </div>
  )
}

function LatestRun({ run }: { run: FlRun }) {
  const o = run.overall
  const beats = o != null && o.mae_federated < o.mae_persistence
  return (
    <Card title={`Latest model · run ${run.id}`}>
      <div className="space-y-4 text-sm">
        {o && (
          <div>
            <p className="eyebrow">Error on held-out recent data, all farms ({o.test_samples} samples)</p>
            <table className="mt-2 w-full text-left">
              <tbody className="tabular-nums">
                <tr className="border-t border-white/5"><td className="py-1.5 pr-3 text-sage-200">Assume no change (baseline)</td><td className="text-paper">{o.mae_persistence} points</td></tr>
                <tr className="border-t border-white/5"><td className="py-1.5 pr-3 text-sage-200">Each farm's own model</td><td className="text-paper">{o.mae_local_only} points</td></tr>
                <tr className="border-t border-white/5"><td className="py-1.5 pr-3 text-sage-200">Federated model</td><td className="text-paper">{o.mae_federated} points</td></tr>
              </tbody>
            </table>
            <p className={`mt-2 text-xs ${beats ? 'text-moss-300' : 'text-signal-warn'}`}>
              {beats ? 'The federated model is more accurate than assuming no change.' : 'The federated model is NOT more accurate than assuming no change. It needs more (and real) data before it is useful.'}
            </p>
          </div>
        )}
        {run.your_metrics && (
          <p className="text-xs text-sage-300">On this farm's own held-out data: baseline {run.your_metrics.mae_persistence}, own model {run.your_metrics.mae_local_only}, federated {run.your_metrics.mae_federated} points ({run.your_metrics.test_samples} samples).</p>
        )}
        {run.explanation && (
          <div>
            <p className="eyebrow">What the model weighs most</p>
            <ul className="mt-1 text-xs text-sage-300">{run.explanation.slice(0, 4).map((f) => <li key={f.feature}>{FEATURE[f.feature] ?? f.feature}: {f.weight > 0 ? '+' : ''}{f.weight}</li>)}</ul>
          </div>
        )}
        {run.uses_simulated_data && <p className="text-xs text-signal-warn">Trained partly on SIMULATED data.</p>}
      </div>
    </Card>
  )
}

function ZoneForecast({ zoneId, name }: { zoneId: number; name: string }) {
  const fc = useForecast(zoneId)
  if (!fc.data) return <li className="text-sm text-sage-400">{name}: loading…</li>
  const f = fc.data
  if (f.status !== 'forecast') return <li className="text-sm text-sage-400">{name}: {f.message}</li>
  return (
    <li className="text-sm">
      <p className="text-paper">{name}: {f.moisture_now_pct} % now → {f.predicted_moisture_6h_pct} % in 6 h ({(f.predicted_change_6h_pct_points ?? 0) > 0 ? '+' : ''}{f.predicted_change_6h_pct_points} points)</p>
      <p className="text-xs text-sage-400">Typical error {f.expected_error_pct_points} points (no-change baseline: {f.persistence_error_pct_points}) · model {f.model_version}</p>
      {f.advice && <p className="text-xs text-signal-warn">{f.advice}</p>}
    </li>
  )
}
