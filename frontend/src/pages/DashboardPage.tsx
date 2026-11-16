import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { FormAlert } from '@/components/ui/form'
import { Pill } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useDashboard, useFarmList, useRefreshWeather, useSeries, useWeather } from '@/features/dashboard/api'
import { TrendChart, WeatherCharts } from '@/features/dashboard/charts'
import { ActivityList, AlertsList, Card, DailyOutlook, EmptyFarms, KpiTile, LogIrrigationForm, ZoneCard } from '@/features/dashboard/panels'
import { RAIN_COLOR, TEMP_COLOR, ZONE_COLORS } from '@/features/dashboard/palette'
import type { FarmDetail } from '@/features/dashboard/schemas'
import { ConnectionBadge } from '@/features/live/components'
import { SENSOR_META, type SensorType } from '@/features/live/schemas'
import { useFarmStream } from '@/features/live/use-farm-stream'
import { useNow } from '@/lib/use-now'

const TREND_TYPES: SensorType[] = ['soil_moisture', 'temperature', 'humidity', 'light', 'soil_ph', 'nitrogen', 'leaf_wetness']
const RANGES = [
  { hours: 6, label: '6 h' },
  { hours: 24, label: '24 h' },
  { hours: 168, label: '7 d' },
] as const

export function DashboardPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>

  const wanted = Number(params.get('farm'))
  const farm = farms.data.items.find((f) => f.id === wanted) ?? farms.data.items[0]!
  return (
    <FarmDashboard
      key={farm.id}
      farm={farm}
      farms={farms.data.items}
      onSelect={(id) => setParams({ farm: String(id) })}
    />
  )
}

function FarmDashboard({ farm, farms, onSelect }: { farm: FarmDetail; farms: FarmDetail[]; onSelect: (id: number) => void }) {
  const summary = useDashboard(farm.id)
  const weather = useWeather(farm.latitude != null ? farm.id : null)
  const refreshWeather = useRefreshWeather(farm.id)
  const stream = useFarmStream(farm.id)
  const now = useNow(30_000)
  const [trendType, setTrendType] = useState<SensorType>('soil_moisture')
  const [hours, setHours] = useState<number>(24)
  const series = useSeries(farm.id, trendType, hours)
  const [logging, setLogging] = useState(false)

  const zoneOrder = useMemo(() => (summary.data?.zones ?? []).map((z) => z.id).sort((a, b) => a - b), [summary.data])
  const sensors = stream.sensors

  // Live zone values from the stream (good readings only), falling back to the summary.
  const liveByZone = useMemo(() => {
    const acc = new Map<number, Record<string, number[]>>()
    for (const s of sensors) {
      if (s.zone_id == null || !s.latest || s.latest.quality !== 'good') continue
      const z = acc.get(s.zone_id) ?? {}
      ;(z[s.sensor_type] ??= []).push(s.latest.value)
      acc.set(s.zone_id, z)
    }
    const out = new Map<number, Partial<Record<'soil_moisture' | 'temperature', number>>>()
    for (const [zoneId, types] of acc) {
      const avg = (v?: number[]) => (v?.length ? v.reduce((a, b) => a + b, 0) / v.length : undefined)
      out.set(zoneId, { soil_moisture: avg(types.soil_moisture), temperature: avg(types.temperature) })
    }
    return out
  }, [sensors])

  if (summary.isPending) return <FullPageSpinner />
  if (summary.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{summary.error.message}</FormAlert></div>
  const d = summary.data

  const moistureNow = d.zones
    .map((z) => liveByZone.get(z.id)?.soil_moisture ?? z.latest.soil_moisture?.value)
    .filter((v): v is number => v != null)
  const avgMoisture = moistureNow.length ? moistureNow.reduce((a, b) => a + b, 0) / moistureNow.length : null
  const today = weather.data?.daily[0]
  const current = weather.data?.current
  const localTime = new Intl.DateTimeFormat(undefined, { timeZone: farm.timezone, weekday: 'long', hour: '2-digit', minute: '2-digit' }).format(now)
  const zoneName = (id: number) => d.zones.find((z) => z.id === id)?.name ?? `Zone ${id}`
  const meta = SENSOR_META[trendType]

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      {/* Header */}
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="eyebrow">Farm dashboard · {localTime} local</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="font-display text-4xl font-light text-paper sm:text-5xl">{farm.name}</h1>
            {farms.length > 1 && (
              <select
                aria-label="Switch farm"
                value={farm.id}
                onChange={(e) => onSelect(Number(e.target.value))}
                className="rounded-full border border-white/10 bg-ink-950/60 px-3 py-1 text-sm text-sage-100"
              >
                {farms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            )}
          </div>
          <p className="mt-2 text-sm text-sage-400">
            {farm.latitude != null ? `${farm.latitude.toFixed(3)}°, ${farm.longitude?.toFixed(3)}°` : 'No location set'} · {d.zones.length} zone{d.zones.length === 1 ? '' : 's'} ·{' '}
            <Link to={`/farms/${farm.id}`} className="text-wheat-300 hover:underline">settings</Link>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ConnectionBadge status={stream.status} />
          <Link to="/live" className="rounded-full border border-white/15 px-4 py-1.5 text-sm text-sage-100 hover:border-white/30">All sensors</Link>
        </div>
      </header>

      {d.sensors.simulated > 0 && (
        <p className="mt-6 rounded-xl border border-wheat-400/20 bg-wheat-400/5 px-4 py-3 text-sm text-sage-200">
          <strong className="font-medium text-wheat-300">Simulated sensor data.</strong> {d.sensors.simulated} of {d.sensors.total} sensors are simulated; no physical
          hardware is connected. Weather comes from Open-Meteo and is real.
        </p>
      )}

      {/* KPIs */}
      <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiTile label="Soil moisture" accent={ZONE_COLORS[2]} value={avgMoisture != null ? avgMoisture.toFixed(1) : '—'} unit="%" sub={moistureNow.length > 1 ? `range ${Math.min(...moistureNow).toFixed(1)}–${Math.max(...moistureNow).toFixed(1)} % across zones` : 'average of zone sensors'} />
        <KpiTile label="Air now" accent={TEMP_COLOR} value={current?.temperature_c != null ? current.temperature_c.toFixed(1) : '—'} unit="°C" sub={current ? `${Math.round(current.relative_humidity_pct ?? 0)} % RH · wind ${current.wind_speed_ms?.toFixed(1) ?? '—'} m/s (Open-Meteo)` : farm.latitude == null ? 'set a location' : 'loading forecast…'} />
        <KpiTile label="Today" accent={RAIN_COLOR} value={today?.temp_max_c != null ? `${Math.round(today.temp_max_c)}°` : '—'} sub={today ? `low ${Math.round(today.temp_min_c ?? 0)}° · rain ${today.precipitation_mm} mm (${Math.round(today.precipitation_probability_max_pct ?? 0)}%) · ET₀ ${today.et0_mm.toFixed(1)} mm` : 'no forecast yet'} />
        <KpiTile label="Water, 7 days" value={(d.water_7d.liters / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} unit="m³" sub={`${d.water_7d.events} irrigation event${d.water_7d.events === 1 ? '' : 's'}`} />
        <KpiTile
          label="Open alerts"
          value={String(d.alerts.open)}
          sub={`${d.alerts.by_severity.critical ?? 0} critical · ${d.alerts.by_severity.warning ?? 0} warning · sensors reporting ${d.sensors.reporting}/${d.sensors.total}`}
        />
      </div>

      {/* Trend + weather */}
      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card
          title={`${meta.label} by zone`}
          className="xl:col-span-2"
          action={series.data?.includes_simulated ? <Pill tone="warn">Simulated</Pill> : undefined}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div role="radiogroup" aria-label="Measurement" className="flex flex-wrap gap-1">
              {TREND_TYPES.map((t) => (
                <button key={t} type="button" role="radio" aria-checked={trendType === t} onClick={() => setTrendType(t)}
                  className={`rounded-full px-3 py-1 text-xs transition-colors ${trendType === t ? 'bg-white/10 text-paper' : 'text-sage-400 hover:text-sage-100'}`}>
                  {SENSOR_META[t].label}
                </button>
              ))}
            </div>
            <div role="radiogroup" aria-label="Time range" className="flex gap-1 rounded-full border border-white/10 p-0.5">
              {RANGES.map((r) => (
                <button key={r.hours} type="button" role="radio" aria-checked={hours === r.hours} onClick={() => setHours(r.hours)}
                  className={`rounded-full px-3 py-0.5 text-xs ${hours === r.hours ? 'bg-white/10 text-paper' : 'text-sage-400'}`}>
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4">
            {series.isError ? (
              <FormAlert>{series.error.message}</FormAlert>
            ) : series.data ? (
              <TrendChart series={series.data} zoneOrder={zoneOrder} tz={farm.timezone} decimals={meta.decimals} />
            ) : (
              <div className="h-[260px] animate-pulse rounded-lg bg-white/[0.03]" />
            )}
            {series.data && <p className="mt-2 text-xs text-sage-400">{series.data.bucket_minutes}-minute averages of good-quality readings; suspect values excluded.</p>}
          </div>
        </Card>

        <Card
          title="Weather"
          action={farm.latitude != null && (
            <button type="button" onClick={() => refreshWeather.mutate()} disabled={refreshWeather.isPending} className="text-xs text-sage-400 hover:text-sage-100">
              {refreshWeather.isPending ? 'Refreshing…' : 'Refresh'}
            </button>
          )}
        >
          {farm.latitude == null ? (
            <p className="text-sm text-sage-300">Add the farm&apos;s location in <Link className="text-wheat-300" to={`/farms/${farm.id}`}>settings</Link> to get a forecast.</p>
          ) : weather.isError ? (
            <FormAlert>{weather.error.message}</FormAlert>
          ) : !weather.data ? (
            <div className="h-[260px] animate-pulse rounded-lg bg-white/[0.03]" />
          ) : (
            <>
              {weather.data.error && <div className="mb-3"><FormAlert>{weather.data.stale ? 'Showing the last stored forecast: ' : ''}{weather.data.error}</FormAlert></div>}
              <WeatherCharts hourly={weather.data.hourly} tz={farm.timezone} />
              <div className="mt-4"><DailyOutlook weather={weather.data} /></div>
              <p className="mt-3 text-[0.68rem] text-sage-400">
                <a href="https://open-meteo.com/" target="_blank" rel="noreferrer" className="hover:text-sage-200">{weather.data.attribution}</a>
                {weather.data.fetched_at && ` · updated ${new Date(weather.data.fetched_at).toLocaleTimeString()}`}
              </p>
            </>
          )}
        </Card>
      </div>

      {/* Zones */}
      <section className="mt-6" aria-label="Zones">
        <h2 className="eyebrow">Zones</h2>
        {d.zones.length === 0 ? (
          <p className="mt-3 text-sm text-sage-400">No zones yet. <Link to={`/farms/${farm.id}`} className="text-wheat-300">Add one</Link>.</p>
        ) : (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {d.zones.map((z) => (
              <ZoneCard key={z.id} zone={z} index={zoneOrder.indexOf(z.id)} live={liveByZone.get(z.id) ?? {}} />
            ))}
          </div>
        )}
      </section>

      {/* Alerts + activity */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Alerts"><AlertsList farmId={farm.id} alerts={d.alerts.recent} /></Card>
        <Card
          title="Field activity"
          action={d.zones.length > 0 && (
            <button type="button" onClick={() => setLogging((v) => !v)} className="text-xs text-wheat-300 hover:underline">
              {logging ? 'Close' : 'Log irrigation'}
            </button>
          )}
        >
          {logging && <div className="mb-5 rounded-xl border border-white/8 p-4"><LogIrrigationForm farmId={farm.id} zones={d.zones} onDone={() => setLogging(false)} /></div>}
          <ActivityList items={d.activity} zoneName={zoneName} tz={farm.timezone} />
        </Card>
      </div>

      <p className="mt-8 text-xs text-sage-400">
        {d.readings_24h.count.toLocaleString()} readings in the last 24 h ({d.readings_24h.not_good} flagged suspect) · updated {new Date(d.generated_at).toLocaleTimeString()}
      </p>
    </div>
  )
}
