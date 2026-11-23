import { motion } from 'framer-motion'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router'
import { FormAlert, SubmitButton, TextField } from '@/components/ui/form'
import { Pill } from '@/components/ui/primitives'
import { useAlertAction, useLogIrrigation } from './api'
import { useDemoFarm } from './demo'
import { zoneColor } from './palette'
import type { Alert, Dashboard, Weather, ZoneSummary } from './schemas'

export function Card({ title, action, children, className = '' }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`glass rounded-2xl p-5 sm:p-6 ${className}`} aria-label={title}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-lg text-paper">{title}</h2>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export function KpiTile({ label, value, unit, sub, accent }: { label: string; value: string; unit?: string; sub?: ReactNode; accent?: string }) {
  return (
    <div className="glass relative overflow-hidden rounded-2xl p-5">
      {accent && <span aria-hidden className="absolute inset-x-0 top-0 h-0.5" style={{ background: accent }} />}
      <p className="eyebrow">{label}</p>
      <p className="mt-3 flex items-baseline gap-1.5">
        <motion.span key={value} initial={{ opacity: 0.4 }} animate={{ opacity: 1 }} className="font-display text-4xl font-light tabular-nums text-paper">
          {value}
        </motion.span>
        {unit && <span className="text-sm text-sage-400">{unit}</span>}
      </p>
      {sub && <div className="mt-2 text-xs text-sage-400">{sub}</div>}
    </div>
  )
}

const STATUS = {
  critical: { icon: '▲', label: 'Critical', cls: 'text-signal-alert border-signal-alert/30 bg-signal-alert/10' },
  warning: { icon: '●', label: 'Warning', cls: 'text-signal-warn border-signal-warn/30 bg-signal-warn/10' },
  info: { icon: 'i', label: 'Info', cls: 'text-sky-200 border-sky-300/30 bg-sky-300/10' },
} as const

/** Severity is never colour alone: icon + text label + colour. */
export function SeverityBadge({ severity }: { severity: Alert['severity'] }) {
  const s = STATUS[severity]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[0.68rem] font-medium uppercase tracking-wider ${s.cls}`}>
      <span aria-hidden>{s.icon}</span>
      {s.label}
    </span>
  )
}

export function ZoneCard({
  zone,
  index,
  live,
}: {
  zone: ZoneSummary
  index: number
  live: Partial<Record<'soil_moisture' | 'temperature', number>>
}) {
  const moisture = live.soil_moisture ?? zone.latest.soil_moisture?.value
  const temp = live.temperature ?? zone.latest.temperature?.value
  return (
    <article className="glass rounded-xl p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: zoneColor(index) }} />
          <h3 className="font-medium text-paper">{zone.name}</h3>
        </div>
        <span className="text-xs text-sage-400">
          {zone.zone_type}
          {zone.area_hectares != null && ` · ${zone.area_hectares} ha`}
        </span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3">
        <Metric label="Soil moisture" value={moisture != null ? moisture.toFixed(1) : '—'} unit="%" />
        <Metric label="Air temp" value={temp != null ? temp.toFixed(1) : '—'} unit="°C" />
      </dl>
      <p className="mt-4 text-xs text-sage-400">
        {zone.active_cycle ? (
          <>
            <span className="text-sage-200">{zone.active_cycle.crop_name}</span>
            {zone.active_cycle.variety && ` (${zone.active_cycle.variety})`} · {zone.active_cycle.status}
            {zone.active_cycle.planted_on && ` since ${zone.active_cycle.planted_on}`}
          </>
        ) : (
          'No active crop cycle'
        )}
        {' · '}
        {zone.sensor_count} sensor{zone.sensor_count === 1 ? '' : 's'}
      </p>
    </article>
  )
}

function Metric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div>
      <dt className="text-[0.68rem] uppercase tracking-wider text-sage-400">{label}</dt>
      <dd className="mt-0.5 font-mono text-xl tabular-nums text-paper">
        {value}
        <span className="ml-1 text-xs text-sage-400">{unit}</span>
      </dd>
    </div>
  )
}

export function DailyOutlook({ weather }: { weather: Weather }) {
  const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', timeZone: 'UTC' })
  return (
    <ol className="grid grid-cols-4 gap-2 sm:grid-cols-7" aria-label="7-day outlook">
      {weather.daily.slice(0, 7).map((d) => (
        <li key={d.date} className="rounded-lg border border-white/6 px-2 py-2.5 text-center">
          <p className="text-xs text-sage-400">{dayFmt.format(new Date(`${d.date}T12:00:00Z`))}</p>
          <p className="mt-1 font-mono text-sm tabular-nums text-paper">
            {d.temp_max_c != null ? Math.round(d.temp_max_c) : '—'}°<span className="text-sage-400">/{d.temp_min_c != null ? Math.round(d.temp_min_c) : '—'}°</span>
          </p>
          <p className="mt-1 text-[0.68rem] text-sky-200">
            {d.precipitation_mm > 0 ? `${d.precipitation_mm} mm` : 'dry'}
            {d.precipitation_probability_max_pct != null && ` · ${Math.round(d.precipitation_probability_max_pct)}%`}
          </p>
          <p className="text-[0.68rem] text-sage-400" title="Reference evapotranspiration">ET₀ {d.et0_mm.toFixed(1)}</p>
        </li>
      ))}
    </ol>
  )
}

export function AlertsList({ farmId, alerts }: { farmId: number; alerts: Alert[] }) {
  const act = useAlertAction(farmId)
  if (!alerts.length) return <p className="text-sm text-sage-400">No open alerts.</p>
  return (
    <ul className="divide-y divide-white/5">
      {alerts.map((a) => (
        <li key={a.id} className="py-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={a.severity} />
                {a.status === 'acknowledged' && <Pill>acknowledged</Pill>}
              </div>
              <p className="mt-1.5 text-sm text-paper">{a.title}</p>
              <p className="text-xs text-sage-400">{a.message}</p>
            </div>
            <div className="flex shrink-0 flex-col gap-1.5">
              {a.status === 'open' && (
                <button type="button" disabled={act.isPending} onClick={() => act.mutate({ id: a.id, action: 'acknowledge' })} className="rounded-full border border-white/15 px-3 py-1 text-xs text-sage-100 hover:border-white/30">
                  Acknowledge
                </button>
              )}
              <button type="button" disabled={act.isPending} onClick={() => act.mutate({ id: a.id, action: 'resolve' })} className="rounded-full border border-white/15 px-3 py-1 text-xs text-sage-100 hover:border-white/30">
                Resolve
              </button>
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}

const KIND_LABEL = { irrigation: 'Irrigation', fertilizer: 'Fertilizer', pesticide: 'Pesticide' } as const

export function ActivityList({ items, zoneName, tz }: { items: Dashboard['activity']; zoneName: (id: number) => string; tz: string }) {
  if (!items.length) return <p className="text-sm text-sage-400">No field operations recorded yet.</p>
  const fmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: tz })
  return (
    <ul className="space-y-3">
      {items.map((a) => (
        <li key={`${a.kind}-${a.id}`} className="flex items-start justify-between gap-3 text-sm">
          <div>
            <p className="text-paper">
              {KIND_LABEL[a.kind]} · <span className="text-sage-200">{a.title}</span>
            </p>
            <p className="text-xs text-sage-400">
              {zoneName(a.zone_id)} · {a.at ? fmt.format(new Date(a.at)) : 'unscheduled'}
            </p>
          </div>
          <span className="shrink-0 font-mono text-xs tabular-nums text-sage-300">
            {a.amount != null ? `${a.amount.toLocaleString()} ${a.unit}` : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function LogIrrigationForm({ farmId, zones, onDone }: { farmId: number; zones: ZoneSummary[]; onDone: () => void }) {
  const log = useLogIrrigation(farmId)
  const [error, setError] = useState<string | null>(null)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const data = new FormData(e.currentTarget)
    const liters = Number(data.get('liters'))
    const minutesAgo = Number(data.get('minutesAgo') || 0)
    if (!Number.isFinite(liters) || liters <= 0 || liters > 10_000_000) return setError('Enter the volume in litres (greater than 0).')
    if (!Number.isFinite(minutesAgo) || minutesAgo < 0 || minutesAgo > 7 * 24 * 60) return setError('Start time must be within the last 7 days.')
    setError(null)
    log.mutate(
      { zoneId: Number(data.get('zoneId')), liters, method: String(data.get('method')), minutesAgo },
      { onSuccess: onDone },
    )
  }
  return (
    <form noValidate onSubmit={submit} className="space-y-3" aria-label="Log irrigation">
      {(error || log.isError) && <FormAlert>{error ?? log.error?.message}</FormAlert>}
      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm text-sage-200">
          Zone
          <select name="zoneId" className="mt-1.5 block w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2.5 text-sm text-paper">
            {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
          </select>
        </label>
        <label className="text-sm text-sage-200">
          Method
          <select name="method" defaultValue="drip" className="mt-1.5 block w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2.5 text-sm text-paper">
            {['drip', 'sprinkler', 'flood', 'pivot', 'furrow', 'manual'].map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <TextField label="Volume (L)" name="liters" inputMode="numeric" placeholder="5000" />
        <TextField label="Started (min ago)" name="minutesAgo" inputMode="numeric" defaultValue="0" />
      </div>
      <SubmitButton busy={log.isPending}>Log irrigation</SubmitButton>
      <p className="text-xs text-sage-400">Recorded as a completed event. Simulated soil-moisture sensors in that zone respond to it.</p>
    </form>
  )
}

export function EmptyFarms() {
  const demo = useDemoFarm()
  return (
    <div className="glass mx-auto mt-10 max-w-lg rounded-2xl p-8 text-center">
      <h2 className="font-display text-2xl text-paper">No farms yet</h2>
      <p className="mt-2 text-sm text-sage-300">
        Start with a ready-made demo farm: two zones with live sensor readings every 10 seconds and real local weather. Or create your own.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <button
          type="button"
          disabled={demo.isPending}
          onClick={() => demo.mutate()}
          className="rounded-full bg-paper px-5 py-2 text-sm font-medium text-ink-900 disabled:opacity-60"
        >
          {demo.isPending ? 'Setting up demo farm…' : 'Set up a demo farm'}
        </button>
        <Link to="/farms" className="rounded-full border border-white/15 px-5 py-2 text-sm text-sage-100 hover:border-white/30">
          Create my own farm
        </Link>
      </div>
      {demo.isError && <div className="mt-4"><FormAlert>Could not set up the demo farm: {demo.error.message}</FormAlert></div>}
    </div>
  )
}
