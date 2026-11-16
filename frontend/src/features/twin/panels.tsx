import { KnowledgeToggle } from '@/features/disease/knowledge'
import type { ReactNode } from 'react'
import { Pill } from '@/components/ui/primitives'
import { formatValue } from '@/features/live/format'
import { SENSOR_META } from '@/features/live/schemas'
import { MOISTURE_DOMAIN, MOISTURE_LEGEND_STOPS, sensorStatus } from './layout'
import { LAYER_LABELS, LAYERS, type FarmTwin, type Infra, type Layer, type Layers, type Selection, type TwinSensor } from './schemas'

const INFRA_LABEL: Record<Infra['kind'], string> = {
  farmhouse: 'Farmhouse',
  shed: 'Equipment shed',
  road: 'Farm road',
  channel: 'Water channel',
  tank: 'Water tank',
  pump: 'Irrigation pump',
  pipe: 'Irrigation main',
  weather_station: 'Weather station',
  gateway: 'IoT gateway',
  solar: 'Solar array',
}

function Panel({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section aria-label={title} className={`rounded-xl border border-white/10 bg-ink-950/75 p-4 text-sm shadow-xl backdrop-blur-md ${className}`}>
      <h2 className="eyebrow">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  )
}

export function LayerToggles({ layers, onToggle }: { layers: Layers; onToggle: (l: Layer) => void }) {
  return (
    <Panel title="Layers">
      <ul className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-1">
        {LAYERS.map((l) => (
          <li key={l}>
            <label className="flex cursor-pointer items-center gap-2 text-xs text-sage-200">
              <input type="checkbox" checked={layers[l]} onChange={() => onToggle(l)} className="h-3.5 w-3.5 accent-[#8fbf7a]" />
              {LAYER_LABELS[l]}
            </label>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1">
      <dt className="text-sage-400">{label}</dt>
      <dd className="text-right text-paper">{children}</dd>
    </div>
  )
}

export function SelectionPanel({ twin, sensors, selection, now, onClose }: { twin: FarmTwin; sensors: TwinSensor[]; selection: Selection; now: number; onClose: () => void }) {
  if (!selection) return null
  const close = (
    <button type="button" onClick={onClose} className="text-xs text-sage-400 hover:text-paper" aria-label="Close details">
      ✕
    </button>
  )

  if (selection.kind === 'zone') {
    const z = twin.zones.find((zz) => zz.id === selection.id)
    if (!z) return null
    const zoneSensors = sensors.filter((s) => s.zone_id === z.id)
    return (
      <Panel title="Zone">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-display text-xl text-paper">{z.name}</h3>
          {close}
        </div>
        <dl className="mt-2 divide-y divide-white/5 text-xs">
          <Row label="Type">{z.zone_type}</Row>
          <Row label="Area">{z.area_hectares != null ? `${z.area_hectares} ha` : '—'}</Row>
          <Row label="Crop">{z.crop ? `${z.crop.crop_name}${z.crop.variety ? ` (${z.crop.variety})` : ''}` : 'None'}</Row>
          {z.crop && (
            <Row label="Stage">
              {z.crop.stage_name ?? z.crop.status}
              {z.crop.growth_fraction != null && ` · ${Math.round(z.crop.growth_fraction * 100)}% of cycle`}
            </Row>
          )}
          <Row label="Crop health">
            {z.health
              ? `${z.health.state === 'disease' ? 'Possible disease' : z.health.state === 'healthy' ? 'Possibly healthy' : 'Uncertain check'}: ${z.health.label} (${Math.round(z.health.confidence * 100)}%)`
              : 'No disease check in the last 30 days'}
          </Row>
          <Row label="Soil moisture">{z.soil_moisture != null ? `${z.soil_moisture.toFixed(1)} %` : '—'}</Row>
          <Row label="Air temperature">{z.temperature != null ? `${z.temperature.toFixed(1)} °C` : '—'}</Row>
          <Row label="Irrigation">{z.irrigating ? 'Water flowing now' : (z.irrigation_method ?? 'none')}</Row>
          <Row label="Sensors">{zoneSensors.length}</Row>
        </dl>
        {z.health && (
          <p className="mt-2 text-[11px] text-sage-400">
            Checked {new Date(z.health.detected_at).toLocaleDateString()} on the Vision page. A model screening result, not a diagnosis.
          </p>
        )}
        {z.health?.state === 'disease' && z.health.knowledge_key && (
          <div className="mt-2 text-xs"><KnowledgeToggle k={z.health.knowledge_key} label="Disease information" /></div>
        )}
        <p className="mt-3 text-[11px] text-sage-400">
          {z.layout === 'boundary' ? 'Shape from the mapped boundary.' : 'Shape sized from the zone area (no mapped boundary yet).'}
        </p>
      </Panel>
    )
  }

  if (selection.kind === 'sensor') {
    const s = sensors.find((ss) => ss.id === selection.id)
    if (!s) return null
    const st = sensorStatus(s.latest, now)
    const meta = SENSOR_META[s.sensor_type]
    return (
      <Panel title="Sensor">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-display text-lg text-paper">{meta.label}</h3>
          {close}
        </div>
        <p className="mt-1 flex items-baseline gap-1.5">
          <span className="font-mono text-3xl tabular-nums text-paper">{s.latest ? formatValue(s, s.latest.value) : '—'}</span>
          <span className="text-xs text-sage-400">{s.unit}</span>
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {s.is_simulated ? <Pill tone="warn">Simulated</Pill> : <Pill tone="info">Hardware</Pill>}
          <span className="inline-flex items-center gap-1.5 text-xs text-sage-300">
            <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: st.color }} />
            {st.label}
          </span>
        </div>
        <dl className="mt-3 divide-y divide-white/5 text-xs">
          <Row label="Name">{s.name}</Row>
          <Row label="Zone">{twin.zones.find((z) => z.id === s.zone_id)?.name ?? '—'}</Row>
          <Row label="Last reading">{s.latest ? new Date(s.latest.recorded_at).toLocaleTimeString() : '—'}</Row>
        </dl>
      </Panel>
    )
  }

  const item = twin.infrastructure.find((i) => i.id === selection.id)
  if (!item) return null
  return (
    <Panel title="Equipment">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-display text-lg text-paper">{INFRA_LABEL[item.kind]}</h3>
        {close}
      </div>
      <dl className="mt-2 divide-y divide-white/5 text-xs">
        {item.kind === 'tank' && <Row label="Level">{item.level_pct != null ? `${item.level_pct.toFixed(0)} % (from sensors)` : 'No level sensor'}</Row>}
        {item.kind === 'pump' && <Row label="State">{item.running ? 'Running' : 'Idle'}</Row>}
        {item.kind === 'pipe' && <Row label="Flow">{item.flowing ? 'Water flowing' : 'No flow'}</Row>}
        {item.kind === 'weather_station' && twin.weather && (
          <>
            <Row label="Wind">{twin.weather.wind_speed_ms != null ? `${twin.weather.wind_speed_ms.toFixed(1)} m/s` : '—'}</Row>
            <Row label="Cloud cover">{twin.weather.cloud_cover_pct != null ? `${Math.round(twin.weather.cloud_cover_pct)} %` : '—'}</Row>
          </>
        )}
      </dl>
      {item.schematic && (
        <p className="mt-3 rounded-md border border-wheat-400/20 bg-wheat-400/5 px-2.5 py-1.5 text-[11px] text-sage-200">
          Schematic placement: this item&apos;s position is not stored yet, so it is laid out by rule.
        </p>
      )}
    </Panel>
  )
}

export function Legend() {
  return (
    <Panel title="Legend">
      <ul className="space-y-1.5 text-xs text-sage-300">
        {[
          ['#8fbf7a', 'Sensor reporting'],
          ['#e2b35c', 'Suspect reading'],
          ['#8e9e86', 'Stale (>10 min)'],
          ['#6f7a6a', 'No readings'],
        ].map(([c, l]) => (
          <li key={l} className="flex items-center gap-2">
            <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />
            {l}
          </li>
        ))}
      </ul>
      <div className="mt-3">
        <p className="text-[11px] text-sage-400">Soil-moisture map</p>
        <div className="mt-1 h-2 rounded-full" style={{ background: `linear-gradient(90deg, ${MOISTURE_LEGEND_STOPS.join(',')})` }} />
        <div className="mt-0.5 flex justify-between font-mono text-[10px] text-sage-400">
          <span>{MOISTURE_DOMAIN[0]}% dry</span>
          <span>{MOISTURE_DOMAIN[1]}% wet</span>
        </div>
      </div>
      <p className="mt-3 text-[11px] text-sage-400">Buildings, roads, pump, pipe routes, gateway and solar are schematic placements.</p>
    </Panel>
  )
}

/** Keyboard- and screen-reader-accessible way to explore the same scene. */
export function ObjectList({ twin, sensors, selection, onSelect }: { twin: FarmTwin; sensors: TwinSensor[]; selection: Selection; onSelect: (s: Selection) => void }) {
  const btn = (active: boolean) =>
    `w-full truncate rounded-md px-2 py-1 text-left text-xs transition-colors ${active ? 'bg-white/10 text-paper' : 'text-sage-300 hover:bg-white/5 hover:text-paper'}`
  return (
    <Panel title="Objects" className="max-h-[50vh] overflow-y-auto">
      <nav aria-label="Twin objects" className="space-y-3">
        {twin.zones.map((z) => (
          <div key={z.id}>
            <button type="button" className={btn(selection?.kind === 'zone' && selection.id === z.id)} onClick={() => onSelect({ kind: 'zone', id: z.id })}>
              ▸ {z.name}
            </button>
            <ul className="ml-3 mt-0.5">
              {sensors
                .filter((s) => s.zone_id === z.id)
                .map((s) => (
                  <li key={s.id}>
                    <button type="button" className={btn(selection?.kind === 'sensor' && selection.id === s.id)} onClick={() => onSelect({ kind: 'sensor', id: s.id })}>
                      {SENSOR_META[s.sensor_type].label}
                      {s.latest ? ` · ${formatValue(s, s.latest.value)} ${s.unit}` : ''}
                    </button>
                  </li>
                ))}
            </ul>
          </div>
        ))}
        <div>
          <p className="px-2 text-[10px] uppercase tracking-wider text-sage-400">Equipment (schematic)</p>
          {twin.infrastructure
            .filter((i) => i.kind !== 'road' && i.kind !== 'pipe')
            .map((i) => (
              <button key={i.id} type="button" className={btn(selection?.kind === 'infra' && selection.id === i.id)} onClick={() => onSelect({ kind: 'infra', id: i.id })}>
                {INFRA_LABEL[i.kind]}
              </button>
            ))}
        </div>
      </nav>
    </Panel>
  )
}
