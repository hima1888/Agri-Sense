import { motion } from 'framer-motion'
import { useMemo } from 'react'
import { Pill, StatusDot } from '@/components/ui/primitives'
import { formatValue, relativeTime } from './format'
import { SENSOR_META, type StreamSensor } from './schemas'
import type { Point, StreamStatus } from './use-farm-stream'

const GROUP_STROKE = { air: 'var(--color-sky-300)', soil: 'var(--color-moss-400)', water: 'var(--color-water-400)' }

export function Sparkline({ points, stroke, label }: { points: Point[]; stroke: string; label: string }) {
  const { path, area, suspects } = useMemo(() => {
    if (points.length < 2) return { path: '', area: '', suspects: [] as { x: number; y: number }[] }
    const good = points.filter((p) => p.q === 'good')
    const ref = good.length >= 2 ? good : points
    const t0 = points[0]!.t
    const t1 = points[points.length - 1]!.t
    let lo = Math.min(...ref.map((p) => p.v))
    let hi = Math.max(...ref.map((p) => p.v))
    if (hi - lo < 1e-9) {
      lo -= 1
      hi += 1
    }
    const x = (t: number) => ((t - t0) / Math.max(1, t1 - t0)) * 100
    const y = (v: number) => 30 - ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * 26 - 2
    const line = ref.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(2)},${y(p.v).toFixed(2)}`).join(' ')
    return {
      path: line,
      area: `${line} L${x(ref[ref.length - 1]!.t).toFixed(2)},32 L${x(ref[0]!.t).toFixed(2)},32 Z`,
      suspects: points.filter((p) => p.q !== 'good').map((p) => ({ x: x(p.t), y: y(p.v) })),
    }
  }, [points])

  if (!path) return <div className="h-10 text-[0.65rem] text-sage-400/70">Collecting data…</div>
  return (
    <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="h-10 w-full overflow-visible" role="img" aria-label={label}>
      <path d={area} fill={stroke} opacity={0.12} />
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      {suspects.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={1.6} fill="var(--color-signal-warn)" />
      ))}
    </svg>
  )
}

export function SensorCard({
  sensor,
  points,
  staleAfterMs,
  now,
}: {
  sensor: StreamSensor
  points: Point[]
  staleAfterMs: number
  now: number
}) {
  const meta = SENSOR_META[sensor.sensor_type]
  const latest = sensor.latest
  const ageMs = latest ? Math.max(0, now - Date.parse(latest.recorded_at)) : Infinity
  const stale = ageMs > staleAfterMs
  return (
    <article className="glass flex flex-col rounded-xl p-4" aria-label={`${meta.label}, ${sensor.name}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-sage-300">{meta.label}</p>
        {sensor.is_simulated ? <Pill tone="warn">Simulated</Pill> : <Pill tone="info">Hardware</Pill>}
      </div>
      <div className="mt-3 flex items-baseline gap-1.5">
        {latest ? (
          <motion.span
            key={latest.recorded_at}
            initial={{ opacity: 0.4 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6 }}
            className={`font-mono text-2xl tabular-nums ${stale ? 'text-sage-400' : 'text-paper'}`}
            data-testid={`value-${sensor.id}`}
          >
            {formatValue(sensor, latest.value)}
          </motion.span>
        ) : (
          <span className="font-mono text-2xl text-sage-400">—</span>
        )}
        <span className="text-xs text-sage-400">{sensor.unit}</span>
      </div>
      <div className="mt-3">
        <Sparkline points={points} stroke={GROUP_STROKE[meta.group]} label={`${meta.label} trend`} />
      </div>
      <div className="mt-2 flex items-center justify-between text-[0.65rem] text-sage-400">
        <span>{latest ? relativeTime(ageMs) : 'No readings yet'}</span>
        {latest?.quality === 'suspect' && <span className="text-signal-warn">Suspect value</span>}
        {stale && latest && <span>Stale</span>}
      </div>
    </article>
  )
}

const STATUS_UI: Record<StreamStatus, { label: string; tone: 'ok' | 'warn' | 'alert' | 'muted' }> = {
  connecting: { label: 'Connecting', tone: 'muted' },
  live: { label: 'Live', tone: 'ok' },
  reconnecting: { label: 'Reconnecting', tone: 'warn' },
  unauthorized: { label: 'Disconnected', tone: 'alert' },
  closed: { label: 'Idle', tone: 'muted' },
}

export function ConnectionBadge({ status }: { status: StreamStatus }) {
  const ui = STATUS_UI[status]
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1 font-mono text-[0.7rem] uppercase tracking-wider text-sage-200" role="status">
      <StatusDot tone={ui.tone} pulse={status === 'live'} />
      {ui.label}
    </span>
  )
}
