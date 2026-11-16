import { useState, type FormEvent } from 'react'
import { localDate } from '@/lib/dates'
import { useSearchParams } from 'react-router'
import { FormAlert, SubmitButton, TextField } from '@/components/ui/form'
import { Pill, type Tone } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList, useZoneList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import {
  useChemicalUse,
  useLogFertilizer,
  useLogPesticide,
  useNutrientPlan,
  useSetTarget,
  useSprayCheck,
  type ChemicalUse,
  type NutrientPlan,
} from '@/features/nutrients/api'

const selectCls = 'mt-1.5 block w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
const LABEL: Record<string, string> = { n: 'N', p2o5: 'P₂O₅', k2o: 'K₂O' }
const TYPES = ['fungicide', 'insecticide', 'herbicide', 'bactericide', 'nematicide', 'biological', 'other']
const CHECK_TONE: Record<string, Tone> = { ok: 'ok', warning: 'warn', unknown: 'muted' }
const num = (fd: FormData, k: string) => {
  const v = String(fd.get(k) ?? '').trim()
  return v === '' ? null : Number(v)
}

export function NutrientsPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  const farmId = farms.data?.items.find((f) => f.id === Number(params.get('farm')))?.id ?? farms.data?.items[0]?.id ?? null
  const zones = useZoneList(farmId)
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>
  const list = zones.data?.items ?? []
  const zoneId = list.find((z) => z.id === Number(params.get('zone')))?.id ?? list[0]?.id ?? null
  const sel = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Fertilizer &amp; chemical reduction</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Nutrients & chemicals</h1>
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
      {zones.isSuccess && !list.length && <p className="mt-10 text-sage-300">This farm has no zones yet.</p>}
      {zoneId != null && (
        <div key={zoneId} className="mt-8 space-y-5">
          <FertilizerSection zoneId={zoneId} />
          <ChemicalSection zoneId={zoneId} />
        </div>
      )}
    </div>
  )
}

function FertilizerSection({ zoneId }: { zoneId: number }) {
  const plan = useNutrientPlan(zoneId)
  const [editing, setEditing] = useState(false)
  const [logging, setLogging] = useState(false)
  if (plan.isPending) return <FullPageSpinner />
  if (plan.isError) return <FormAlert>{plan.error.message}</FormAlert>
  const p = plan.data
  const btn = 'rounded-full border border-white/10 px-3 py-1.5 text-xs text-sage-200 hover:border-white/25'
  return (
    <Card
      title={`Fertilizer plan${p.crop ? ` · ${p.crop}` : ''}`}
      action={p.cycle_id != null && (
        <div className="flex gap-2">
          <button type="button" className={btn} onClick={() => setEditing((o) => !o)}>Set recommended dose</button>
          <button type="button" className={btn} onClick={() => setLogging((o) => !o)}>Log fertilizer</button>
        </div>
      )}
    >
      {p.status === 'no_crop' && <p className="text-sm text-sage-300">{p.message}</p>}
      {p.status === 'no_target' && <FormAlert tone="ok">{p.message}</FormAlert>}
      {editing && p.cycle_id != null && <TargetForm zoneId={zoneId} cycleId={p.cycle_id} plan={p} onDone={() => setEditing(false)} />}
      {logging && <FertilizerForm zoneId={zoneId} onDone={() => setLogging(false)} />}
      {p.factors && p.target_kg_ha && (
        <div className="space-y-5">
          <p className="text-xs text-sage-400">
            Recommended dose: {p.target_kg_ha.n}-{p.target_kg_ha.p2o5}-{p.target_kg_ha.k2o} kg/ha ({p.target_source}). Confidence {Math.round((p.confidence ?? 0) * 100)} %.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-sage-400">
                <tr><th className="py-2 pr-3 font-normal">Nutrient</th><th className="pr-3 font-normal">Recommended</th><th className="pr-3 font-normal">Soil test</th><th className="pr-3 font-normal">Adjusted</th><th className="pr-3 font-normal">Applied</th><th className="font-normal">Still needed</th></tr>
              </thead>
              <tbody>
                {p.factors.map((f) => (
                  <tr key={f.nutrient} className="border-t border-white/5 tabular-nums">
                    <td className="py-2 pr-3 text-paper">{LABEL[f.nutrient]}</td>
                    <td className="pr-3">{f.recommended_kg_ha}</td>
                    <td className="pr-3 text-xs">{f.soil_rating ?? '—'} ×{f.factor}<span className="block text-sage-400">{f.note ?? f.soil_source}</span></td>
                    <td className="pr-3">{f.adjusted_kg_ha}</td>
                    <td className="pr-3">{f.applied_kg_ha}{f.surplus_kg_ha > 0 && <span className="block text-xs text-signal-warn">+{f.surplus_kg_ha} over</span>}</td>
                    <td className="text-paper">{f.remaining_kg_ha} kg/ha</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {p.products && p.products.length > 0 ? (
            <div>
              <p className="eyebrow">To apply</p>
              <ul className="mt-2 grid gap-2 sm:grid-cols-3">
                {p.products.map((x) => (
                  <li key={x.product} className="rounded-xl border border-white/5 p-3 text-sm">
                    <p className="text-paper">{x.product} <span className="text-xs text-sage-400">({x.grade})</span></p>
                    <p className="tabular-nums">{x.kg_per_ha} kg/ha{x.kg_for_zone != null && ` · ${x.kg_for_zone} kg here (${x.bags_50kg} × 50 kg bags)`}</p>
                    <p className="text-xs text-sage-400">{x.supplies}</p>
                  </li>
                ))}
              </ul>
            </div>
          ) : <FormAlert tone="ok">The recommended dose is already covered by logged applications.</FormAlert>}
          {p.soil_test_saving_kg_ha && Object.keys(p.soil_test_saving_kg_ha).length > 0 && (
            <p className="text-sm text-moss-300">The soil test lowers the dose by {Object.entries(p.soil_test_saving_kg_ha).map(([k, v]) => `${v} kg/ha ${LABEL[k]}`).join(', ')} compared with the unadjusted recommendation.</p>
          )}
          {p.surplus_kg_ha && Object.keys(p.surplus_kg_ha).length > 0 && (
            <FormAlert>Applied above the adjusted dose: {Object.entries(p.surplus_kg_ha).map(([k, v]) => `${v} kg/ha ${LABEL[k]}`).join(', ')}. Avoid further applications of these this season.</FormAlert>
          )}
          <ul className="list-disc space-y-1 pl-5 text-xs text-sage-300">{p.notes?.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      )}
      {p.limitations && <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-sage-400">{p.limitations.map((l) => <li key={l}>{l}</li>)}</ul>}
    </Card>
  )
}

function TargetForm({ zoneId, cycleId, plan, onDone }: { zoneId: number; cycleId: number; plan: NutrientPlan; onDone: () => void }) {
  const set = useSetTarget(zoneId)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    set.mutate({ cycleId, body: { n: Number(fd.get('n')), p2o5: Number(fd.get('p2o5')), k2o: Number(fd.get('k2o')), source: String(fd.get('source')) } }, { onSuccess: onDone })
  }
  const t = plan.target_kg_ha
  return (
    <form onSubmit={submit} className="mb-5 grid gap-3 border-b border-white/5 pb-5 sm:grid-cols-4" aria-label="Recommended dose">
      <TextField label="N (kg/ha)" name="n" type="number" min={0} required defaultValue={t?.n} />
      <TextField label="P₂O₅ (kg/ha)" name="p2o5" type="number" min={0} required defaultValue={t?.p2o5} />
      <TextField label="K₂O (kg/ha)" name="k2o" type="number" min={0} required defaultValue={t?.k2o} />
      <TextField label="Source" name="source" required minLength={3} placeholder="e.g. State PoP 2024" />
      {set.error && <div className="sm:col-span-4"><FormAlert>{set.error.message}</FormAlert></div>}
      <div className="sm:col-span-4"><SubmitButton busy={set.isPending}>Save dose for this crop cycle</SubmitButton></div>
    </form>
  )
}

function FertilizerForm({ zoneId, onDone }: { zoneId: number; onDone: () => void }) {
  const log = useLogFertilizer(zoneId)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    log.mutate({
      applied_at: new Date(String(fd.get('date'))).toISOString(),
      product_name: String(fd.get('product')),
      method: String(fd.get('method')),
      quantity_kg: Number(fd.get('qty')),
      n_pct: num(fd, 'n'), p_pct: num(fd, 'p'), k_pct: num(fd, 'k'),
    }, { onSuccess: onDone })
  }
  return (
    <form onSubmit={submit} className="mb-5 grid gap-3 border-b border-white/5 pb-5 sm:grid-cols-4" aria-label="Log fertilizer">
      <TextField label="Product" name="product" required placeholder="Urea" />
      <TextField label="Quantity (kg, whole zone)" name="qty" type="number" min={0} step="0.1" required />
      <TextField label="Applied on" name="date" type="date" required defaultValue={localDate()} />
      <label className="block text-sm text-sage-200">Method<select name="method" className={selectCls}>{['broadcast', 'banding', 'fertigation', 'foliar', 'top_dressing', 'other'].map((m) => <option key={m}>{m}</option>)}</select></label>
      <TextField label="N %" name="n" type="number" min={0} max={100} step="0.1" />
      <TextField label="P₂O₅ %" name="p" type="number" min={0} max={100} step="0.1" />
      <TextField label="K₂O %" name="k" type="number" min={0} max={100} step="0.1" />
      {log.error && <div className="sm:col-span-4"><FormAlert>{log.error.message}</FormAlert></div>}
      <div className="sm:col-span-4"><SubmitButton busy={log.isPending}>Save application</SubmitButton></div>
    </form>
  )
}

function ChemicalSection({ zoneId }: { zoneId: number }) {
  const use = useChemicalUse(zoneId)
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="Spray check & log" className="min-w-0"><SprayForm zoneId={zoneId} /></Card>
      <Card title="Chemical use this crop cycle" className="min-w-0">
        {use.isPending ? <p className="text-sm text-sage-400">Loading…</p> : use.isError ? <FormAlert>{use.error.message}</FormAlert> : <UseSummary u={use.data} />}
      </Card>
    </div>
  )
}

function UseSummary({ u }: { u: ChemicalUse }) {
  if (!u.current) return <p className="text-sm text-sage-300">{u.message}</p>
  const c = u.current
  return (
    <div className="space-y-3 text-sm">
      <p className="text-paper">{c.applications} application(s){Object.keys(c.by_type).length > 0 && `: ${Object.entries(c.by_type).map(([t, n]) => `${n} ${t}`).join(', ')}`}</p>
      {c.quantity_per_ha_by_unit && Object.keys(c.quantity_per_ha_by_unit).length > 0 && (
        <p className="text-sage-300">Product used: {Object.entries(c.quantity_per_ha_by_unit).map(([unit, v]) => `${v} ${unit}/ha`).join(', ')}</p>
      )}
      {c.evidence_share != null && <p className="text-sage-300">Linked to a disease check: {c.with_evidence} of {c.applications} ({Math.round(c.evidence_share * 100)} %)</p>}
      {c.phi_conflicts > 0 && <FormAlert>{c.phi_conflicts} spray(s) would still be within the pre-harvest interval on the expected harvest date.</FormAlert>}
      {c.harvest_blocked_until && <p className="text-xs text-sage-400">Safe to harvest from {new Date(`${c.harvest_blocked_until}T12:00:00`).toLocaleDateString()} (latest PHI).</p>}
      {u.comparison ? (
        <p className={u.comparison.change_pct != null && u.comparison.change_pct <= 0 ? 'text-moss-300' : 'text-signal-warn'}>
          Sprays per hectare vs previous cycle: {u.comparison.applications_per_ha.current} vs {u.comparison.applications_per_ha.previous}
          {u.comparison.change_pct != null && ` (${u.comparison.change_pct > 0 ? '+' : ''}${u.comparison.change_pct} %)`}
        </p>
      ) : <p className="text-xs text-sage-400">No previous crop cycle in this zone to compare with.</p>}
      {u.recent && u.recent.length > 0 && (
        <ul className="space-y-1 border-t border-white/5 pt-3 text-xs text-sage-300">
          {u.recent.map((r) => <li key={r.id}>{new Date(r.applied_at).toLocaleDateString()} · {r.product_name} ({r.pesticide_type}) · {String(r.quantity)} {r.quantity_unit}{r.disease_detection_id ? ' · evidence linked' : ''}</li>)}
        </ul>
      )}
      <p className="text-xs text-sage-400">{u.basis}</p>
    </div>
  )
}

function SprayForm({ zoneId }: { zoneId: number }) {
  const check = useSprayCheck(zoneId)
  const log = useLogPesticide(zoneId)
  const [type, setType] = useState('fungicide')
  const [phi, setPhi] = useState('')
  const [saved, setSaved] = useState(false)
  const evidenceId = check.data?.evidence[0]?.id
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setSaved(false)
    log.mutate({
      applied_at: new Date().toISOString(), product_name: String(fd.get('product')), pesticide_type: type,
      quantity: Number(fd.get('qty')), quantity_unit: String(fd.get('unit')),
      pre_harvest_interval_days: phi === '' ? null : Number(phi), target: String(fd.get('target') || '') || null,
      ...(fd.get('link') && evidenceId ? { disease_detection_id: evidenceId } : {}),
    }, { onSuccess: () => setSaved(true) })
  }
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-sm text-sage-200">Type<select className={selectCls} value={type} onChange={(e) => { setType(e.target.value); check.reset() }}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
        <TextField label="PHI (days, from label)" type="number" min={0} value={phi} onChange={(e) => setPhi(e.target.value)} />
        <div className="flex items-end"><button type="button" className="w-full rounded-full border border-white/15 px-3 py-2.5 text-sm text-paper disabled:opacity-50" disabled={check.isPending} onClick={() => check.mutate({ type, phi: phi === '' ? null : Number(phi) })}>Check before spraying</button></div>
      </div>
      {check.data && (
        <div aria-label="Spray check result">
          <Pill tone={check.data.verdict === 'hold' ? 'warn' : 'ok'}>{check.data.verdict === 'hold' ? `Hold: ${check.data.warnings} warning(s)` : 'OK to proceed'}</Pill>
          <ul className="mt-2 space-y-1 text-xs">{check.data.checks.map((c) => <li key={c.check} className="flex gap-2"><Pill tone={CHECK_TONE[c.status]}>{c.status}</Pill><span className="text-sage-300">{c.detail}</span></li>)}</ul>
          <p className="mt-2 text-xs text-sage-400">{check.data.limitations.join(' ')}</p>
        </div>
      )}
      <form onSubmit={submit} className="grid gap-3 border-t border-white/5 pt-4 sm:grid-cols-2" aria-label="Log spray">
        <TextField label="Product" name="product" required />
        <TextField label="Target pest / disease" name="target" />
        <TextField label="Quantity (whole zone)" name="qty" type="number" min={0} step="0.001" required />
        <label className="block text-sm text-sage-200">Unit<select name="unit" className={selectCls}><option value="l">litres</option><option value="kg">kg</option></select></label>
        {evidenceId != null && <label className="flex items-center gap-2 text-sm text-sage-200 sm:col-span-2"><input type="checkbox" name="link" defaultChecked /> Link to disease check #{evidenceId}</label>}
        {log.error && <div className="sm:col-span-2"><FormAlert>{log.error.message}</FormAlert></div>}
        {saved && <p className="text-xs text-moss-300 sm:col-span-2" role="status">Spray logged.</p>}
        <div className="sm:col-span-2"><SubmitButton busy={log.isPending}>Log spray</SubmitButton></div>
      </form>
    </div>
  )
}
