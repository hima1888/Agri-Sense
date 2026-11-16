import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { FormAlert, SubmitButton, TextField } from '@/components/ui/form'
import { Pill } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList, useZoneList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { useBacktest, useSaveYield, useSavedYields, useSetReference, useYield, type YieldEstimate } from '@/features/yield/api'

const sel = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
const kg = (v: number) => `${Math.round(v).toLocaleString()} kg`
const t = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(2)} t` : kg(v))

export function YieldPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  const farmId = farms.data?.items.find((f) => f.id === Number(params.get('farm')))?.id ?? farms.data?.items[0]?.id ?? null
  const zones = useZoneList(farmId)
  const backtest = useBacktest(farmId)
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>
  const list = zones.data?.items ?? []
  const zoneId = list.find((z) => z.id === Number(params.get('zone')))?.id ?? list[0]?.id ?? null
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Yield prediction</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Yield</h1>
        </div>
        <div className="flex gap-2">
          <select aria-label="Farm" className={sel} value={farmId ?? ''} onChange={(e) => setParams({ farm: e.target.value })}>
            {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <select aria-label="Zone" className={sel} value={zoneId ?? ''} onChange={(e) => setParams({ farm: String(farmId), zone: e.target.value })}>
            {list.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
          </select>
        </div>
      </div>
      {zoneId != null && <ZoneYield key={zoneId} zoneId={zoneId} />}
      <Card title="Accuracy on this farm" className="mt-5">
        {backtest.data ? (
          backtest.data.n === 0 ? <p className="text-sm text-sage-300">{backtest.data.message}</p> : (
            <div className="space-y-2 text-sm">
              <p className="text-paper">Mean absolute error {backtest.data.mean_absolute_error_pct} % over {backtest.data.n} harvest(s); {Math.round((backtest.data.share_within_range ?? 0) * 100)} % fell inside the predicted range.</p>
              <ul className="space-y-1 text-xs text-sage-300">
                {backtest.data.cycles.map((c) => <li key={c.cycle_id}>{c.zone_name} · {c.crop}: predicted {kg(c.predicted_central_kg_ha)}/ha, actual {kg(c.actual_kg_ha)}/ha ({c.error_pct != null && c.error_pct > 0 ? '+' : ''}{c.error_pct} %)</li>)}
              </ul>
            </div>
          )
        ) : <p className="text-sm text-sage-400">Loading…</p>}
      </Card>
    </div>
  )
}

function ZoneYield({ zoneId }: { zoneId: number }) {
  const est = useYield(zoneId)
  const saved = useSavedYields(zoneId)
  const save = useSaveYield(zoneId)
  const [editing, setEditing] = useState(false)
  if (est.isPending) return <div className="mt-10"><FullPageSpinner /></div>
  if (est.isError) return <div className="mt-8"><FormAlert>{est.error.message}</FormAlert></div>
  const e = est.data
  const btn = 'rounded-full border border-white/10 px-3 py-1.5 text-xs text-sage-200 hover:border-white/25 disabled:opacity-50'
  return (
    <div className="mt-8 space-y-5">
      {e.uses_simulated_data && <FormAlert>The moisture history here is <strong>SIMULATED</strong>. The estimate demonstrates the method; it says nothing about a real harvest.</FormAlert>}
      <Card
        title={`${e.zone_name}${e.crop ? ` · ${e.crop}` : ''}`}
        action={e.cycle_id != null && (
          <div className="flex gap-2">
            <button type="button" className={btn} onClick={() => setEditing((o) => !o)}>Set attainable yield</button>
            {e.status === 'estimate' && <button type="button" className={btn} disabled={save.isPending} onClick={() => save.mutate()}>Save estimate</button>}
          </div>
        )}
      >
        {editing && e.cycle_id != null && <ReferenceForm zoneId={zoneId} cycleId={e.cycle_id} current={e.ym_kg_ha} onDone={() => setEditing(false)} />}
        {save.isSuccess && <p className="mb-3 text-xs text-moss-300" role="status">Estimate saved; it will be compared with the actual harvest.</p>}
        {e.status === 'estimate' && e.yield_kg_ha ? <Estimate e={e} /> : <p className="text-sm text-sage-300">{e.message}</p>}
      </Card>

      {saved.data && saved.data.total > 0 && (
        <Card title="Saved estimates">
          <ul className="space-y-1 text-sm">
            {saved.data.items.map((s) => (
              <li key={s.id} className="flex justify-between gap-3"><span className="text-sage-300">{new Date(s.created_at).toLocaleString()}</span><span className="tabular-nums text-paper">{kg(s.predicted_value.low)} – {kg(s.predicted_value.high)} /ha</span></li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Method and limitations">
        <p className="text-sm text-sage-300">{e.method}</p>
        {e.limitations && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-sage-400">{e.limitations.map((l) => <li key={l}>{l}</li>)}</ul>}
      </Card>
    </div>
  )
}

function Estimate({ e }: { e: YieldEstimate }) {
  const y = e.yield_kg_ha!
  const ymax = e.ym_kg_ha ?? y.high
  const pos = (v: number) => `${Math.min(100, (v / ymax) * 100)}%`
  return (
    <div className="space-y-5">
      <div>
        <p className="eyebrow">Estimated yield (water-limited)</p>
        <p className="mt-2 font-display text-4xl font-light tabular-nums text-paper">{kg(y.central)}<span className="text-lg text-sage-400"> /ha</span></p>
        <p className="text-sm text-sage-300">Range {kg(y.low)} – {kg(y.high)} /ha{e.total_kg && ` · ${t(e.total_kg.central)} for ${e.area_hectares} ha (${t(e.total_kg.low)} – ${t(e.total_kg.high)})`}</p>
        <div className="relative mt-3 h-2 rounded-full bg-white/10" role="img" aria-label={`Range ${y.low} to ${y.high} kg per hectare, central ${y.central}, attainable ${ymax}`}>
          <div className="absolute inset-y-0 rounded-full bg-moss-400/40" style={{ left: pos(y.low), width: `calc(${pos(y.high)} - ${pos(y.low)})` }} />
          <div className="absolute inset-y-[-3px] w-0.5 bg-paper" style={{ left: pos(y.central) }} />
        </div>
        <p className="mt-1 flex justify-between text-[0.7rem] text-sage-400"><span>0</span><span>attainable {kg(ymax)} /ha</span></p>
        {(e.season?.coverage_season ?? 0) < 0.5 && (
          <p className="mt-2 text-xs text-signal-warn">
            Based on very little moisture data: a narrow range here means no water stress was seen on the few measured days, not that the yield is known precisely.
          </p>
        )}
        <p className="mt-2 text-xs text-sage-400">Confidence {Math.round((e.confidence ?? 0) * 100)} % · moisture measured on {e.season?.days_measured} of {e.season?.days_elapsed} days so far ({Math.round((e.season?.coverage_season ?? 0) * 100)} % of the season, ETc-weighted)</p>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-sage-400"><tr><th className="py-1 pr-3 font-normal">Factor</th><th className="pr-3 font-normal">Value</th><th className="font-normal">Source</th></tr></thead>
        <tbody>
          {e.factors?.map((f) => (
            <tr key={f.name} className="border-t border-white/5">
              <td className="py-1.5 pr-3 text-sage-200">{f.name}</td>
              <td className="pr-3 tabular-nums text-paper">{f.value == null ? '—' : String(f.value)} {f.unit}</td>
              <td className="text-xs text-sage-400">{f.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {e.water_loss_pct_central != null && e.water_loss_pct_central > 0 && <Pill tone="warn">{e.water_loss_pct_central} % below attainable from water stress (central)</Pill>}
    </div>
  )
}

function ReferenceForm({ zoneId, cycleId, current, onDone }: { zoneId: number; cycleId: number; current?: number; onDone: () => void }) {
  const set = useSetReference(zoneId)
  function submit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    const fd = new FormData(ev.currentTarget)
    set.mutate({ cycleId, kg_ha: Number(fd.get('kg_ha')), source: String(fd.get('source')) }, { onSuccess: onDone })
  }
  return (
    <form onSubmit={submit} className="mb-5 grid gap-3 border-b border-white/5 pb-5 sm:grid-cols-3" aria-label="Attainable yield">
      <TextField label="Attainable yield (kg/ha)" name="kg_ha" type="number" min={1} required defaultValue={current} hint="Well-watered yield for this variety and field" />
      <TextField label="Source" name="source" required minLength={3} placeholder="e.g. KVK variety trial 2024" />
      <div className="flex items-end"><SubmitButton busy={set.isPending}>Save</SubmitButton></div>
      {set.error && <div className="sm:col-span-3"><FormAlert>{set.error.message}</FormAlert></div>}
    </form>
  )
}
