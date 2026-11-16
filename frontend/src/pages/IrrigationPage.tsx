import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FormAlert } from '@/components/ui/form'
import { Pill, type Tone } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList, useZoneList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { CHART, RAIN_COLOR } from '@/features/dashboard/palette'
import { useCompleteEvent, useSchedule, useWaterUse, useZonePlan, type PlanEvent, type ZonePlan } from '@/features/irrigation/api'
import { usePrefersReducedMotion } from '@/lib/use-reduced-motion'

const selectCls = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
const STATUS: Record<ZonePlan['status'], { label: string; tone: Tone }> = {
  irrigate_today: { label: 'Irrigate today', tone: 'warn' },
  planned: { label: 'Irrigation planned', tone: 'info' },
  no_irrigation_needed: { label: 'No irrigation needed this week', tone: 'ok' },
  no_moisture_data: { label: 'No moisture data', tone: 'muted' },
}
const litres = (v: number | null) => (v == null ? '—' : `${v.toLocaleString()} L`)
const dayLabel = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

export function IrrigationPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  const farmId = farms.data?.items.find((f) => f.id === Number(params.get('farm')))?.id ?? farms.data?.items[0]?.id ?? null
  const zones = useZoneList(farmId)
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>
  const list = zones.data?.items ?? []
  const zoneId = list.find((z) => z.id === Number(params.get('zone')))?.id ?? list[0]?.id ?? null
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Smart irrigation</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Irrigation</h1>
        </div>
        <div className="flex gap-2">
          <select aria-label="Farm" className={selectCls} value={farmId ?? ''} onChange={(e) => setParams({ farm: e.target.value })}>
            {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <select aria-label="Zone" className={selectCls} value={zoneId ?? ''} onChange={(e) => setParams({ farm: String(farmId), zone: e.target.value })}>
            {list.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
          </select>
        </div>
      </div>
      {zones.isSuccess && !list.length && <p className="mt-10 text-sage-300">This farm has no zones yet.</p>}
      {zoneId != null && <ZoneIrrigation key={zoneId} zoneId={zoneId} />}
    </div>
  )
}

function ZoneIrrigation({ zoneId }: { zoneId: number }) {
  const plan = useZonePlan(zoneId)
  const [days, setDays] = useState(7)
  const use = useWaterUse(zoneId, days)
  if (plan.isPending) return <div className="mt-10"><FullPageSpinner /></div>
  if (plan.isError) return <div className="mt-8"><FormAlert>{plan.error.message}</FormAlert></div>
  const p = plan.data
  const s = STATUS[p.status]

  return (
    <div className="mt-8 space-y-5">
      {p.uses_simulated_data && <FormAlert>Soil moisture here comes from <strong>SIMULATED</strong> sensors. The plan demonstrates the method; do not irrigate a real field from it.</FormAlert>}
      <Card title={`${p.zone_name}${p.crop ? ` · ${p.crop}` : ''}`} action={<Pill tone={s.tone}>{s.label}</Pill>}>
        {p.water ? (
          <div className="grid gap-4 sm:grid-cols-4 text-sm">
            <Stat label="Depleted now" value={`${p.water.depletion_mm} mm`} sub={`stress at ${p.water.raw_mm} mm · empty at ${p.water.taw_mm} mm`} />
            <Stat label="Soil moisture" value={`${p.water.moisture_pct} %`} sub={p.water.sources.moisture ?? ''} />
            <Stat label="This week" value={p.plan ? `${p.plan.total_gross_mm} mm` : '—'} sub={p.plan ? litres(p.plan.total_volume_liters) : ''} />
            <Stat label="Confidence" value={`${Math.round(p.confidence * 100)} %`} sub={`${p.irrigation_method ?? 'method unknown'} · efficiency ${p.plan?.application_efficiency ?? '—'}`} />
          </div>
        ) : <p className="text-sm text-sage-300">{p.message}</p>}
      </Card>

      {p.plan && (
        <div className="grid gap-5 lg:grid-cols-5">
          <Card title="Planned irrigations" className="min-w-0 lg:col-span-2">
            {p.plan.events.length ? (
              <ul className="space-y-3">{p.plan.events.map((e) => <EventRow key={e.date} e={e} zoneId={zoneId} />)}</ul>
            ) : <p className="text-sm text-sage-300">No irrigation needed within the {p.plan.days.length}-day forecast.</p>}
            {p.rain_aware_saving && p.rain_aware_saving.gross_mm > 0 && (
              <p className="mt-4 text-xs text-moss-300">Rain-aware planning avoids an estimated {p.rain_aware_saving.gross_mm} mm{p.rain_aware_saving.volume_liters ? ` (${litres(p.rain_aware_saving.volume_liters)})` : ''} this week ({p.rain_aware_saving.basis}).</p>
            )}
          </Card>
          <Card title="Root-zone depletion, end of each day" className="min-w-0 lg:col-span-3">
            <DepletionChart plan={p} />
            <DayTable plan={p} />
          </Card>
        </div>
      )}

      <ScheduledList p={p} zoneId={zoneId} />

      <Card title="Water use" action={
        <select aria-label="Period" className={selectCls} value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option>
        </select>
      }>
        {use.data ? (
          <div className="space-y-2 text-sm">
            <p className="text-paper">{litres(use.data.applied_liters)} applied in {use.data.events} completed event(s){use.data.applied_net_mm != null ? ` · ${use.data.applied_net_mm} mm reached the roots` : ''}.</p>
            {use.data.events_without_volume > 0 && <p className="text-xs text-signal-warn">{use.data.events_without_volume} event(s) have no volume and are not counted.</p>}
            {use.data.applied_to_need_ratio != null
              ? <p className="text-sage-300">Estimated crop need {use.data.estimated_need_mm} mm · applied/need ratio {use.data.applied_to_need_ratio}</p>
              : <p className="text-xs text-sage-400">Crop need not compared: stored weather covers {use.data.weather_days_covered} of {use.data.days} days.</p>}
            <p className="text-xs text-sage-400">{use.data.basis}</p>
          </div>
        ) : <p className="text-sm text-sage-400">Loading…</p>}
      </Card>

      <Card title="Method and limitations">
        <p className="text-sm text-sage-300">{p.method}</p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-sage-400">{p.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Card>
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="mt-1 font-display text-2xl tabular-nums text-paper">{value}</p>
      <p className="text-xs text-sage-400">{sub}</p>
    </div>
  )
}

function EventRow({ e, zoneId }: { e: PlanEvent; zoneId: number }) {
  const schedule = useSchedule(zoneId)
  return (
    <li className="rounded-xl border border-white/5 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-paper">{dayLabel(e.date)} · from {String(e.window.start_local_hour).padStart(2, '0')}:00</p>
        {e.urgent && <Pill tone="warn">now</Pill>}
      </div>
      <p className="mt-1 text-sm text-sage-200">{e.gross_mm} mm gross ({e.net_mm} mm net){e.volume_liters != null ? ` · ${litres(e.volume_liters)}` : ''}</p>
      <p className="mt-1 text-xs text-sage-400">Why: {e.reason}. Timing: {e.window.basis}.</p>
      <div className="mt-2">
        {e.already_scheduled ? <Pill tone="ok">scheduled</Pill> : (
          <button type="button" className="rounded-full bg-paper px-3 py-1.5 text-xs text-ink-900 disabled:opacity-50" disabled={schedule.isPending} onClick={() => schedule.mutate(e.date)}>
            Schedule
          </button>
        )}
        {schedule.error && <div className="mt-2"><FormAlert>{schedule.error.message}</FormAlert></div>}
      </div>
    </li>
  )
}

function DepletionChart({ plan }: { plan: ZonePlan }) {
  const reduced = usePrefersReducedMotion()
  if (!plan.plan || !plan.water) return null
  const data = plan.plan.days.map((d) => ({ day: dayLabel(d.date), depletion: d.depletion_end_mm }))
  return (
    <div className="h-48" role="img" aria-label="Projected end-of-day root-zone depletion with the stress threshold">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={CHART.grid} vertical={false} />
          <XAxis dataKey="day" stroke={CHART.axis} fontSize={11} tickLine={false} />
          <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} unit=" mm" domain={[0, Math.ceil(plan.water.taw_mm)]} />
          <Tooltip cursor={{ fill: 'rgb(255 255 255 / 0.04)' }} contentStyle={{ background: CHART.tooltipBg, borderColor: CHART.tooltipBorder, fontSize: 12 }} formatter={(v) => [`${String(v)} mm`, 'Depletion']} />
          <ReferenceLine y={plan.water.raw_mm} stroke="#c98500" strokeDasharray="4 4" label={{ value: 'stress', fill: '#c98500', fontSize: 11, position: 'insideTopRight' }} />
          <Bar dataKey="depletion" fill={RAIN_COLOR} radius={[3, 3, 0, 0]} isAnimationActive={!reduced} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function DayTable({ plan }: { plan: ZonePlan }) {
  if (!plan.plan) return null
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-sage-400">
          <tr><th className="py-1 pr-2 font-normal">Day</th><th className="pr-2 font-normal">Crop use</th><th className="pr-2 font-normal">Rain (eff.)</th><th className="pr-2 font-normal">Irrigation</th><th className="font-normal">Depleted</th></tr>
        </thead>
        <tbody>
          {plan.plan.days.map((d) => (
            <tr key={d.date} className="border-t border-white/5 tabular-nums">
              <td className="py-1 pr-2 text-sage-200">{dayLabel(d.date)}</td>
              <td className="pr-2">{d.etc_mm} mm</td>
              <td className="pr-2">{d.rain_mm} ({d.effective_rain_mm}) mm</td>
              <td className="pr-2">{d.irrigation_net_mm != null ? `${d.irrigation_net_mm} mm` : d.note ? 'deferred' : '—'}</td>
              <td>{d.depletion_start_mm} → {d.depletion_end_mm} mm</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ScheduledList({ p, zoneId }: { p: ZonePlan; zoneId: number }) {
  const complete = useCompleteEvent(zoneId)
  if (!p.scheduled.length) return null
  return (
    <Card title="Scheduled">
      <ul className="space-y-2 text-sm">
        {p.scheduled.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sage-200">{new Date(s.scheduled_for).toLocaleString()} · {litres(s.volume_liters)}</span>
            <button type="button" className="rounded-full border border-white/10 px-3 py-1 text-xs text-sage-200 disabled:opacity-50" disabled={complete.isPending} onClick={() => complete.mutate({ id: s.id, volume: s.volume_liters })}>
              Mark done
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-sage-400">Marking done records the planned volume; the water balance then counts it until the next moisture reading.</p>
      {complete.error && <div className="mt-2"><FormAlert>{complete.error.message}</FormAlert></div>}
    </Card>
  )
}
