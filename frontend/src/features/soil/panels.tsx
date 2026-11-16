import { useState, type FormEvent } from 'react'
import { localDate } from '@/lib/dates'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FormAlert, SubmitButton, TextField } from '@/components/ui/form'
import { Pill } from '@/components/ui/primitives'
import { CHART, RAIN_COLOR } from '@/features/dashboard/palette'
import { usePrefersReducedMotion } from '@/lib/use-reduced-motion'
import { useAddSoilProfile, useAddSoilTest } from './api'
import { LABELS, MEASUREMENT_SOURCES, SOIL_TEXTURES, type SoilAssessment, type SoilComponent, type WaterBalance } from './schemas'
import { statusTone } from './tone'

const pct = (v: number) => `${Math.round(v * 100)} %`
const human = (s: string) => s.replaceAll('_', ' ')

export function IndexSummary({ a }: { a: SoilAssessment }) {
  return (
    <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
      <div>
        <p className="eyebrow">Soil index</p>
        <p className="mt-2 flex items-baseline gap-2">
          <span className="font-display text-5xl font-light tabular-nums text-paper">{a.index == null ? '—' : Math.round(a.index)}</span>
          <span className="text-sm text-sage-400">/ 100</span>
          {a.rating && <Pill tone={statusTone(a.rating)}>{a.rating}</Pill>}
        </p>
      </div>
      <div className="min-w-48 flex-1">
        <p className="eyebrow">Confidence {pct(a.confidence)}</p>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10" role="meter" aria-label="Confidence" aria-valuemin={0} aria-valuemax={1} aria-valuenow={a.confidence}>
          <div className="h-full rounded-full bg-wheat-300" style={{ width: pct(a.confidence) }} />
        </div>
        <ul className="mt-2 space-y-0.5 text-xs text-sage-400">
          {a.confidence_reasons.map((r) => <li key={r}>· {r}</li>)}
        </ul>
      </div>
    </div>
  )
}

export function ComponentsTable({ a }: { a: SoilAssessment }) {
  const rows = Object.entries(a.components)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-sage-400">
          <tr><th className="py-2 pr-3 font-normal">Component</th><th className="pr-3 font-normal">Value</th><th className="pr-3 font-normal">Rating</th><th className="pr-3 font-normal">Target</th><th className="font-normal">Source</th></tr>
        </thead>
        <tbody>
          {rows.map(([k, c]) => <ComponentRow key={k} k={k} c={c} />)}
          {a.not_assessed.filter((k) => k !== 'water').map((k) => (
            <tr key={k} className="border-t border-white/5 text-sage-400">
              <td className="py-2 pr-3">{LABELS[k] ?? k}</td><td colSpan={4}>Not assessed — no data</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ComponentRow({ k, c }: { k: string; c: SoilComponent }) {
  const [lo, hi] = c.target
  return (
    <tr className="border-t border-white/5 align-top">
      <td className="py-2 pr-3 text-paper">{LABELS[k] ?? k}</td>
      <td className="pr-3 tabular-nums text-paper">
        {c.value} <span className="text-sage-400">{c.unit}</span>
        {c.value_mg_kg != null && <span className="block text-xs text-sage-400">{c.value_mg_kg} mg/kg</span>}
      </td>
      <td className="pr-3"><Pill tone={statusTone(c.status)}>{human(c.status)}</Pill></td>
      <td className="pr-3 text-xs text-sage-300">{lo}–{hi} <span className="block text-sage-400">{c.target_source}</span></td>
      <td className="text-xs text-sage-300">{c.source}</td>
    </tr>
  )
}

export function FactorList({ a }: { a: SoilAssessment }) {
  if (!a.factors.length) return <p className="text-sm text-sage-400">No factors — nothing could be assessed.</p>
  const max = Math.max(...a.factors.map((f) => f.impact), 1)
  return (
    <ul className="space-y-2.5">
      {a.factors.map((f) => (
        <li key={f.key}>
          <div className="flex justify-between text-sm"><span className="text-paper">{f.label}</span><span className="text-xs text-sage-400">score {Math.round(f.score)} · {human(f.status)}</span></div>
          <div className="mt-1 h-1 rounded-full bg-white/10"><div className="h-full rounded-full bg-signal-warn" style={{ width: `${(f.impact / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  )
}

export function WaterPanel({ w }: { w: WaterBalance }) {
  const reduced = usePrefersReducedMotion()
  const data = [{ date: 'now', depletion_mm: w.depletion_mm }, ...w.projection.map((p) => ({ date: p.date.slice(5), depletion_mm: p.depletion_mm }))]
  const fill = Math.min(1, Math.max(0, w.depletion_mm / w.taw_mm))
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Pill tone={statusTone(w.status)}>{human(w.status)}</Pill>
        <span className="text-sm text-sage-300">
          {w.days_to_stress == null ? `No stress within the ${w.forecast_days}-day forecast` : w.days_to_stress === 0 ? 'Already below the stress threshold' : `Stress expected in ~${w.days_to_stress} day${w.days_to_stress === 1 ? '' : 's'}`}
        </span>
      </div>
      {/* Depletion bar: 0 = field capacity, RAW = stress threshold, TAW = wilting point. */}
      <div className="mt-4" aria-label={`Root-zone depletion ${w.depletion_mm} of ${w.taw_mm} mm`}>
        <div className="relative h-3 rounded-full bg-white/10">
          <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${fill * 100}%`, background: RAIN_COLOR }} />
          <div className="absolute inset-y-[-3px] w-0.5 bg-signal-warn" style={{ left: `${(w.raw_mm / w.taw_mm) * 100}%` }} />
        </div>
        <div className="mt-1 flex justify-between text-[0.7rem] text-sage-400"><span>FC {w.field_capacity_pct} %</span><span>RAW {w.raw_mm} mm</span><span>WP {w.wilting_point_pct} %</span></div>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-3 text-xs">
        {[['Moisture', `${w.moisture_pct} %`], ['Depleted', `${w.depletion_mm} mm`], ['TAW', `${w.taw_mm} mm`], ['Kc', String(w.kc)], ['Root depth', `${w.root_depth_m} m`], ['p', String(w.depletion_fraction_p)]].map(([k, v]) => (
          <div key={k}><dt className="text-sage-400">{k}</dt><dd className="tabular-nums text-paper">{v}</dd></div>
        ))}
      </dl>
      {w.projection.length > 0 ? (
        <div className="mt-4 h-48" role="img" aria-label="Projected root-zone depletion by day, with the stress threshold">
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="date" stroke={CHART.axis} fontSize={11} tickLine={false} />
              <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} domain={[0, Math.ceil(w.taw_mm)]} unit=" mm" />
              <Tooltip contentStyle={{ background: CHART.tooltipBg, borderColor: CHART.tooltipBorder, fontSize: 12 }} formatter={(v) => [`${String(v)} mm`, 'Depletion']} />
              <ReferenceLine y={w.raw_mm} stroke="#c98500" strokeDasharray="4 4" label={{ value: 'stress', fill: '#c98500', fontSize: 11, position: 'insideTopRight' }} />
              <Line type="monotone" dataKey="depletion_mm" stroke={RAIN_COLOR} strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={!reduced} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-4 text-xs text-sage-400">No stored forecast for this farm — refresh weather on the dashboard to project ahead.</p>
      )}
      <ul className="mt-3 space-y-0.5 text-xs text-sage-400">
        {Object.entries(w.sources).map(([k, v]) => <li key={k}>{human(k)}: {v}</li>)}
      </ul>
    </div>
  )
}

export function TrendList({ trends }: { trends: Record<string, number> }) {
  const entries = Object.entries(trends)
  if (!entries.length) return <p className="text-sm text-sage-400">Not enough 7-day sensor history for trends.</p>
  return (
    <ul className="space-y-1.5 text-sm">
      {entries.map(([k, v]) => (
        <li key={k} className="flex justify-between"><span className="text-sage-300">{human(k)}</span><span className="tabular-nums text-paper">{v > 0 ? '+' : ''}{Number(v.toPrecision(2))} / day</span></li>
      ))}
    </ul>
  )
}

const selectCls = 'mt-1.5 block w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2.5 text-sm text-paper'
const numberOrNull = (fd: FormData, k: string) => {
  const raw = String(fd.get(k) ?? '').trim()
  return raw === '' ? null : Number(raw)
}

export function SoilTestForm({ zoneId, onDone }: { zoneId: number; onDone: () => void }) {
  const add = useAddSoilTest(zoneId)
  const [error, setError] = useState<string | null>(null)
  const fields = [['ph', 'pH', '0.1'], ['nitrogen_mg_kg', 'N (mg/kg)', '0.1'], ['phosphorus_mg_kg', 'P (mg/kg)', '0.1'], ['potassium_mg_kg', 'K (mg/kg)', '0.1'], ['organic_carbon_pct', 'Organic carbon (%)', '0.01'], ['electrical_conductivity_ds_m', 'EC (dS/m)', '0.01'], ['moisture_pct', 'Moisture (vol %)', '0.1']] as const
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const body: Record<string, unknown> = { source: fd.get('source'), measured_at: new Date(String(fd.get('measured_at'))).toISOString() }
    let any = false
    for (const [k] of fields) {
      const v = numberOrNull(fd, k)
      if (v != null) { body[k] = v; any = true }
    }
    if (!any) return setError('Enter at least one measured value.')
    setError(null)
    add.mutate(body, { onSuccess: onDone })
  }
  return (
    <form onSubmit={submit} className="space-y-3" aria-label="Add soil test">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm text-sage-200">Source<select name="source" className={selectCls}>{MEASUREMENT_SOURCES.map((s) => <option key={s} value={s}>{human(s)}</option>)}</select></label>
        <TextField label="Sampled on" name="measured_at" type="date" required defaultValue={localDate()} />
        {fields.map(([k, label, step]) => <TextField key={k} label={label} name={k} type="number" step={step} min={0} />)}
      </div>
      {(error ?? add.error) && <FormAlert>{error ?? add.error?.message}</FormAlert>}
      <SubmitButton busy={add.isPending}>Save soil test</SubmitButton>
    </form>
  )
}

export function SoilProfileForm({ zoneId, onDone }: { zoneId: number; onDone: () => void }) {
  const add = useAddSoilProfile(zoneId)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const body: Record<string, unknown> = { texture: fd.get('texture') || null }
    for (const k of ['field_capacity_pct', 'wilting_point_pct'] as const) {
      const v = numberOrNull(fd, k)
      if (v != null) body[k] = v
    }
    add.mutate(body, { onSuccess: onDone })
  }
  return (
    <form onSubmit={submit} className="space-y-3" aria-label="Add soil profile">
      <label className="block text-sm text-sage-200">Texture<select name="texture" defaultValue="loam" className={selectCls}>{SOIL_TEXTURES.map((t) => <option key={t} value={t}>{human(t)}</option>)}</select></label>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label="Field capacity (vol %)" name="field_capacity_pct" type="number" step="0.1" min={0} max={100} hint="Optional — estimated from texture if blank" />
        <TextField label="Wilting point (vol %)" name="wilting_point_pct" type="number" step="0.1" min={0} max={100} />
      </div>
      {add.error && <FormAlert>{add.error.message}</FormAlert>}
      <SubmitButton busy={add.isPending}>Save soil profile</SubmitButton>
    </form>
  )
}
