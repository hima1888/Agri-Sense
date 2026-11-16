import { useMemo, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { usePrefersReducedMotion } from '@/lib/use-reduced-motion'
import { timeFormatter } from './format'
import { CHART, RAIN_COLOR, TEMP_COLOR, zoneColor } from './palette'
import type { Series, WeatherPoint } from './schemas'

interface TipEntry {
  dataKey?: unknown
  name?: unknown
  value?: unknown
  color?: string
}
interface TipProps {
  active?: boolean
  payload?: readonly TipEntry[]
  label?: unknown
  formatLabel: (t: number) => string
  unit: string
  decimals: number
}

function ChartTooltip({ active, payload, label, formatLabel, unit, decimals }: TipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border px-3 py-2 text-xs shadow-xl" style={{ background: CHART.tooltipBg, borderColor: CHART.tooltipBorder }}>
      <p className="font-mono text-sage-400">{formatLabel(Number(label))}</p>
      <ul className="mt-1.5 space-y-1">
        {payload.map((p) => (
          <li key={String(p.dataKey)} className="flex items-center gap-2">
            <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: p.color }} />
            <span className="text-sage-200">{String(p.name ?? '')}</span>
            <span className="ml-auto pl-4 font-mono tabular-nums text-paper">
              {typeof p.value === 'number' ? p.value.toFixed(decimals) : '—'} {unit}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function Legend({ items }: { items: { key: string; label: string; color: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-sage-300" aria-label="Legend">
      {items.map((i) => (
        <li key={i.key} className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-0.5 w-4 rounded-full" style={{ background: i.color }} />
          {i.label}
        </li>
      ))}
    </ul>
  )
}

/** Per-zone trend lines for one sensor type. Colour follows the zone (fixed order), never its rank. */
export function TrendChart({
  series,
  zoneOrder,
  tz,
  decimals,
  height = 260,
}: {
  series: Series
  zoneOrder: number[]
  tz: string
  decimals: number
  height?: number
}) {
  const reduced = usePrefersReducedMotion()
  const { rows, lines } = useMemo(() => {
    const byT = new Map<number, Record<string, number>>()
    const lines = series.zones.map((z) => {
      const key = `z${z.zone_id ?? 'none'}`
      const idx = z.zone_id == null ? -1 : zoneOrder.indexOf(z.zone_id)
      for (const p of z.points) {
        const t = Date.parse(p.t)
        byT.set(t, { ...(byT.get(t) ?? { t }), [key]: p.avg })
      }
      return { key, label: z.zone_name, color: zoneColor(idx < 0 ? 99 : idx) }
    })
    return { rows: [...byT.values()].sort((a, b) => a.t! - b.t!), lines }
  }, [series, zoneOrder])

  const hours = (Date.parse(series.end) - Date.parse(series.start)) / 3_600_000
  const fmt = timeFormatter(tz, hours > 30)
  const unit = series.unit ?? ''

  if (!rows.length) return <EmptyChart height={height}>No readings in this period.</EmptyChart>
  return (
    <figure>
      {lines.length > 1 && <Legend items={lines} />}
      <div style={{ height }} className="mt-3">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={fmt} stroke={CHART.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis width={48} stroke={CHART.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} domain={['auto', 'auto']} tickFormatter={(v: number) => `${Number(v.toFixed(decimals))}`} unit={unit.length <= 2 ? unit : ''} />
            <Tooltip
              cursor={{ stroke: 'rgb(255 255 255 / 0.25)', strokeWidth: 1 }}
              content={(props) => <ChartTooltip active={props.active} payload={props.payload as readonly TipEntry[] | undefined} label={props.label} formatLabel={timeFormatter(tz, true)} unit={unit} decimals={decimals} />}
            />
            {lines.map((l) => (
              <Line key={l.key} dataKey={l.key} name={l.label} stroke={l.color} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: CHART.tooltipBg }} connectNulls isAnimationActive={!reduced} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTable
        caption={`${series.sensor_type} by zone (${unit})`}
        headers={['Time', ...lines.map((l) => l.label)]}
        rows={rows.slice(-12).map((r) => [fmt(r.t!), ...lines.map((l) => (r[l.key] != null ? r[l.key]!.toFixed(decimals) : '—'))])}
      />
    </figure>
  )
}

/** Next 48 h: temperature and rain probability as two aligned charts (never a dual axis). */
export function WeatherCharts({ hourly, tz }: { hourly: WeatherPoint[]; tz: string }) {
  const reduced = usePrefersReducedMotion()
  const rows = useMemo(
    () =>
      hourly.map((h) => ({
        t: Date.parse(h.valid_at),
        temp: h.temperature_c,
        rain: h.precipitation_probability_pct,
      })),
    [hourly],
  )
  if (!rows.length) return <EmptyChart height={200}>No forecast available.</EmptyChart>
  const fmt = timeFormatter(tz, true)
  const axis = { stroke: CHART.axis, tick: { fontSize: 11 }, tickLine: false, axisLine: false } as const
  return (
    <figure className="space-y-2">
      <figcaption className="text-xs text-sage-400">Temperature (°C)</figcaption>
      <div style={{ height: 140 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} syncId="wx" margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} hide />
            <YAxis width={40} {...axis} domain={['auto', 'auto']} />
            <Tooltip content={(p) => <ChartTooltip active={p.active} payload={p.payload as readonly TipEntry[] | undefined} label={p.label} formatLabel={fmt} unit="°C" decimals={1} />} cursor={{ stroke: 'rgb(255 255 255 / 0.25)' }} />
            <Line dataKey="temp" name="Temperature" stroke={TEMP_COLOR} strokeWidth={2} dot={false} isAnimationActive={!reduced} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="text-xs text-sage-400">Chance of rain (%)</figcaption>
      <div style={{ height: 90 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} syncId="wx" margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barCategoryGap={2}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={timeFormatter(tz, true)} {...axis} minTickGap={60} />
            <YAxis width={40} {...axis} domain={[0, 100]} ticks={[0, 50, 100]} />
            <Tooltip content={(p) => <ChartTooltip active={p.active} payload={p.payload as readonly TipEntry[] | undefined} label={p.label} formatLabel={fmt} unit="%" decimals={0} />} cursor={{ fill: 'rgb(255 255 255 / 0.05)' }} />
            <Bar dataKey="rain" name="Chance of rain" fill={RAIN_COLOR} radius={[3, 3, 0, 0]} isAnimationActive={!reduced} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <DataTable
        caption="Hourly forecast: temperature and chance of rain"
        headers={['Time', 'Temperature (°C)', 'Chance of rain (%)']}
        rows={rows.map((r) => [fmt(r.t), r.temp == null ? '—' : r.temp.toFixed(1), r.rain == null ? '—' : r.rain.toFixed(0)])}
      />
    </figure>
  )
}

function EmptyChart({ height, children }: { height: number; children: ReactNode }) {
  return (
    <div style={{ height }} className="grid place-items-center rounded-lg border border-dashed border-white/10 text-sm text-sage-400">
      {children}
    </div>
  )
}

export function DataTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: string[][] }) {
  return (
    <details className="mt-3 text-xs text-sage-400">
      <summary className="cursor-pointer select-none hover:text-sage-200">View as table</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left font-mono tabular-nums">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>{headers.map((h) => <th key={h} className="py-1 pr-4 font-normal text-sage-300">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-white/5">{r.map((c, j) => <td key={j} className="py-1 pr-4 text-sage-200">{c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
