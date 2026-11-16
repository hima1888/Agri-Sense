import type { ReactNode } from 'react'
import { Card } from '@/features/dashboard/panels'
import type { Analytics, Indicator } from './api'

const fmt = (v: number | null | undefined, digits = 1) => (v == null ? '—' : Number(v.toFixed(digits)).toLocaleString())
const share = (v: number | null | undefined) => (v == null ? '—' : v > 0 && v < 0.1 ? `${(v * 100).toFixed(1)} %` : `${Math.round(v * 100)} %`)

function IndicatorValue({ i, v }: { i: Indicator; v: number | null }) {
  return <>{i.unit === 'share' ? share(v) : `${fmt(v)} ${i.unit}`}</>
}

export function IndicatorTable({ indicators, previous }: { indicators: Indicator[]; previous?: { start: string; end: string } }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-sage-400">
          <tr><th className="py-2 pr-3 font-normal">Indicator</th><th className="pr-3 font-normal">This period</th><th className="pr-3 font-normal">Previous{previous ? ` (${previous.start} to ${previous.end})` : ''}</th><th className="font-normal">Change</th></tr>
        </thead>
        <tbody>
          {indicators.map((i) => (
            <tr key={i.indicator} className="border-t border-white/5 tabular-nums">
              <td className="py-2 pr-3 text-sage-200">{i.indicator}</td>
              <td className="pr-3 text-paper"><IndicatorValue i={i} v={i.current} /></td>
              <td className="pr-3 text-sage-300"><IndicatorValue i={i} v={i.previous} /></td>
              <td className="text-sage-300">{i.change_pct == null ? '—' : `${i.change_pct > 0 ? '+' : ''}${i.change_pct} %`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-sage-400">Change is shown only when both periods have a non-zero value.</p>
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <div className="flex justify-between gap-4 border-t border-white/5 py-1.5 text-sm"><dt className="text-sage-300">{label}</dt><dd className="text-right tabular-nums text-paper">{children}</dd></div>
}

/** Every section of a farm summary (live analytics or a saved report). */
export function Sections({ a }: { a: Partial<Analytics> }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {a.water && (
        <Card title="Water" className="min-w-0">
          <dl>
            <Row label="Irrigation (completed events)">{a.water.irrigation_events} · {fmt(a.water.irrigation_liters, 0)} L{a.water.irrigation_mm != null && ` · ${a.water.irrigation_mm} mm`}</Row>
            {a.water.by_zone.map((z) => <Row key={z.zone} label={`  ${z.zone}`}>{fmt(z.liters, 0)} L{z.mm != null && ` · ${z.mm} mm`}</Row>)}
            <Row label="Rain / ET₀ (stored weather)">{a.water.weather_days_covered ? `${fmt(a.water.rain_mm)} / ${fmt(a.water.et0_mm)} mm over ${a.water.weather_days_covered} day(s)` : 'no weather stored for this period'}</Row>
            {a.water.stress.map((s) => <Row key={s.zone} label={`Hours under water stress · ${s.zone}`}>{s.stress_share == null ? 'no moisture data' : `${share(s.stress_share)} of ${s.measured_hours} h (below ${s.threshold_pct} %)`}</Row>)}
            {a.water.events_without_volume > 0 && <Row label="Events without a volume (not counted)">{a.water.events_without_volume}</Row>}
          </dl>
        </Card>
      )}
      {a.fertilizer && (
        <Card title="Fertilizer" className="min-w-0">
          <dl>
            <Row label="Applications">{a.fertilizer.applications} · {fmt(a.fertilizer.product_kg)} kg product ({fmt(a.fertilizer.organic_kg)} kg organic)</Row>
            {Object.entries(a.fertilizer.nutrients_kg).map(([k, v]) => <Row key={k} label={{ n: 'N', p2o5: 'P₂O₅', k2o: 'K₂O' }[k] ?? k}>{fmt(v as number)} kg</Row>)}
            {a.fertilizer.without_grade > 0 && <Row label="Applications without a grade (no nutrients counted)">{a.fertilizer.without_grade}</Row>}
          </dl>
        </Card>
      )}
      {a.pesticides && (
        <Card title="Pesticides" className="min-w-0">
          <dl>
            <Row label="Applications">{a.pesticides.applications}{Object.keys(a.pesticides.by_type).length > 0 && ` (${Object.entries(a.pesticides.by_type).map(([t, n]) => `${n} ${t}`).join(', ')})`}</Row>
            <Row label="Linked to a disease check">{a.pesticides.with_evidence}</Row>
          </dl>
        </Card>
      )}
      {a.health && (
        <Card title="Crop health & harvests" className="min-w-0">
          <dl>
            <Row label="Disease checks">{a.health.disease_checks}{Object.keys(a.health.by_outcome).length > 0 && ` (${Object.entries(a.health.by_outcome).map(([o, n]) => `${n} ${o.replaceAll('_', ' ')}`).join(', ')})`}</Row>
            {Object.entries(a.health.possible_diseases).map(([d, n]) => <Row key={d} label={`  possible ${d}`}>{n}</Row>)}
            {(a.harvests ?? []).length === 0 ? <Row label="Harvests">none recorded in this period</Row> : (a.harvests ?? []).map((h) => <Row key={`${h.zone}-${h.harvested_on}`} label={`Harvest · ${h.zone} · ${h.crop}`}>{h.yield_kg_ha != null ? `${fmt(h.yield_kg_ha, 0)} kg/ha` : `${fmt(h.yield_kg, 0)} kg`}</Row>)}
          </dl>
        </Card>
      )}
      {a.advice && a.alerts && (
        <Card title="Advice & alerts" className="min-w-0">
          <dl>
            <Row label="Recommendations">{a.advice.recommendations}{Object.keys(a.advice.by_status).length > 0 && ` (${Object.entries(a.advice.by_status).map(([s, n]) => `${n} ${s}`).join(', ')})`}</Row>
            <Row label="Taken up (of decided)">{share(a.advice.uptake)}</Row>
            <Row label="Alerts raised / resolved">{a.alerts.raised} / {a.alerts.resolved}</Row>
            <Row label="Median time to resolve">{a.alerts.median_hours_to_resolve == null ? '—' : `${a.alerts.median_hours_to_resolve} h`}</Row>
          </dl>
        </Card>
      )}
      {a.data && (
        <Card title="Data quality" className="min-w-0">
          <dl>
            <Row label="Sensor readings">{fmt(a.data.readings, 0)}</Row>
            <Row label="Flagged (not good)">{share(a.data.not_good_share)}</Row>
            <Row label="Simulated">{share(a.data.simulated_share)}</Row>
            {a.data.zones_without_area.length > 0 && <Row label="Zones without an area (excluded from per-ha)">{a.data.zones_without_area.join(', ')}</Row>}
          </dl>
        </Card>
      )}
    </div>
  )
}
