import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { FormAlert } from '@/components/ui/form'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList } from '@/features/dashboard/api'
import { EmptyFarms } from '@/features/dashboard/panels'
import { ConnectionBadge } from '@/features/live/components'
import { useFarmStream } from '@/features/live/use-farm-stream'
import { useTwin } from '@/features/twin/api'
import { mergeLiveSensors, mergeLiveZones } from '@/features/twin/merge-live'
import { Legend, LayerToggles, ObjectList, SelectionPanel } from '@/features/twin/panels'
import { TwinCanvas } from '@/features/twin/Scene'
import { DEFAULT_LAYERS, type Layer, type Selection } from '@/features/twin/schemas'
import { useNow } from '@/lib/use-now'
import { usePrefersReducedMotion } from '@/lib/use-reduced-motion'

/** Loaded lazily (see router): three.js is only downloaded when this page is opened. */
export default function TwinPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>
  const farm = farms.data.items.find((f) => f.id === Number(params.get('farm'))) ?? farms.data.items[0]!
  return (
    <FarmTwinView
      key={farm.id}
      farmId={farm.id}
      farms={farms.data.items.map((f) => ({ id: f.id, name: f.name }))}
      onSelectFarm={(id) => setParams({ farm: String(id) })}
    />
  )
}

function FarmTwinView({ farmId, farms, onSelectFarm }: { farmId: number; farms: { id: number; name: string }[]; onSelectFarm: (id: number) => void }) {
  const twin = useTwin(farmId)
  const stream = useFarmStream(farmId)
  const reduced = usePrefersReducedMotion()
  const now = useNow(10_000)
  const [layers, setLayers] = useState(DEFAULT_LAYERS)
  const [selection, setSelection] = useState<Selection>(null)
  const [reset, setReset] = useState(0)

  const sensors = useMemo(() => (twin.data ? mergeLiveSensors(twin.data.sensors, stream.sensors) : []), [twin.data, stream.sensors])
  const view = useMemo(() => (twin.data ? { ...twin.data, zones: mergeLiveZones(twin.data.zones, sensors) } : null), [twin.data, sensors])

  if (twin.isPending) return <FullPageSpinner />
  if (twin.isError || !view) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{twin.error?.message ?? 'Could not load the twin.'}</FormAlert></div>

  const toggle = (l: Layer) => setLayers((prev) => ({ ...prev, [l]: !prev[l] }))
  const simulated = sensors.filter((s) => s.is_simulated).length

  return (
    <div className="relative h-[calc(100dvh-4rem)] w-full overflow-hidden bg-ink-950">
      {view.zones.length === 0 ? (
        <div className="grid h-full place-items-center px-4 text-center">
          <div>
            <p className="font-display text-2xl text-paper">This farm has no zones yet.</p>
            <Link to={`/farms/${farmId}`} className="mt-3 inline-block text-sm text-wheat-300 hover:underline">Add zones in farm settings →</Link>
          </div>
        </div>
      ) : (
        <TwinCanvas
          twin={view}
          sensors={sensors}
          layers={layers}
          selection={selection}
          onSelect={setSelection}
          reducedMotion={reduced}
          resetSignal={reset}
          now={now}
        />
      )}

      {/* Header overlay */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-wrap items-start justify-between gap-3 p-4">
        <div className="pointer-events-auto rounded-xl border border-white/10 bg-ink-950/70 px-4 py-3 backdrop-blur-md">
          <p className="eyebrow">Digital twin</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="font-display text-2xl font-light text-paper">{view.farm_name}</h1>
            {farms.length > 1 && (
              <select aria-label="Switch farm" value={farmId} onChange={(e) => onSelectFarm(Number(e.target.value))} className="rounded-full border border-white/10 bg-ink-950/60 px-2 py-0.5 text-xs text-sage-100">
                {farms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            )}
          </div>
          <p className="mt-1 text-[11px] text-sage-400">
            {view.sun ? `Sun ${view.sun.elevation_deg > 0 ? `${Math.round(view.sun.elevation_deg)}° high` : 'below horizon'} · ` : ''}
            {view.weather?.wind_speed_ms != null ? `wind ${view.weather.wind_speed_ms.toFixed(1)} m/s · ` : ''}
            {simulated > 0 ? `${simulated} simulated sensors` : `${sensors.length} sensors`}
          </p>
        </div>
        <div className="pointer-events-auto flex items-center gap-2">
          <ConnectionBadge status={stream.status} />
          <button type="button" onClick={() => (setSelection(null), setReset((r) => r + 1))} className="rounded-full border border-white/15 bg-ink-950/70 px-3 py-1 text-xs text-sage-100 backdrop-blur hover:border-white/30">
            Reset view
          </button>
        </div>
      </div>

      {/* Left: layers + objects */}
      <div className="pointer-events-auto absolute bottom-4 left-4 top-32 hidden w-56 flex-col gap-3 overflow-y-auto md:flex">
        <LayerToggles layers={layers} onToggle={toggle} />
        <ObjectList twin={view} sensors={sensors} selection={selection} onSelect={setSelection} />
      </div>

      {/* Right: selection + legend */}
      {/* Stays below the header overlay; scrolls instead of growing under it on short screens. */}
      <div className="pointer-events-none absolute bottom-4 right-4 top-28 w-72 max-w-[calc(100%-2rem)] overflow-y-auto">
        <div className="pointer-events-auto flex min-h-full flex-col justify-end gap-3">
          <SelectionPanel twin={view} sensors={sensors} selection={selection} now={now} onClose={() => setSelection(null)} />
          <Legend />
        </div>
      </div>

      {/* Mobile: layers below header */}
      <details className="pointer-events-auto absolute left-4 top-32 w-56 md:hidden">
        <summary className="cursor-pointer rounded-full border border-white/15 bg-ink-950/70 px-3 py-1 text-xs text-sage-100">Layers & objects</summary>
        <div className="mt-2 space-y-3">
          <LayerToggles layers={layers} onToggle={toggle} />
          <ObjectList twin={view} sensors={sensors} selection={selection} onSelect={setSelection} />
        </div>
      </details>

      <p className="pointer-events-none absolute bottom-1 left-1/2 -translate-x-1/2 text-[10px] text-sage-400/80">
        Drag to rotate · right-drag to pan · scroll to zoom · click a zone or sensor
      </p>
    </div>
  )
}
