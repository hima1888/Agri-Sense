import { DemoNote } from '@/components/ui/demo-note'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { FormAlert } from '@/components/ui/form'
import { Pill } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList, useZoneList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { useSaveAssessment, useSoil, useSoilHistory } from '@/features/soil/api'
import { ComponentsTable, FactorList, IndexSummary, SoilProfileForm, SoilTestForm, TrendList, WaterPanel } from '@/features/soil/panels'

const selectCls = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'

export function SoilPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  const farmId = farms.data?.items.find((f) => f.id === Number(params.get('farm')))?.id ?? farms.data?.items[0]?.id ?? null
  const zones = useZoneList(farmId)
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>

  const zoneList = zones.data?.items ?? []
  const zoneId = zoneList.find((z) => z.id === Number(params.get('zone')))?.id ?? zoneList[0]?.id ?? null
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Soil intelligence</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Soil</h1>
        </div>
        <div className="flex gap-2">
          <select aria-label="Farm" className={selectCls} value={farmId ?? ''} onChange={(e) => setParams({ farm: e.target.value })}>
            {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <select aria-label="Zone" className={selectCls} value={zoneId ?? ''} onChange={(e) => setParams({ farm: String(farmId), zone: e.target.value })}>
            {zoneList.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
          </select>
        </div>
      </div>
      {zones.isSuccess && !zoneList.length && <p className="mt-10 text-sage-300">This farm has no zones yet.</p>}
      {zoneId != null && <ZoneSoil key={zoneId} zoneId={zoneId} />}
    </div>
  )
}

function ZoneSoil({ zoneId }: { zoneId: number }) {
  const soil = useSoil(zoneId)
  const history = useSoilHistory(zoneId)
  const save = useSaveAssessment(zoneId)
  const [form, setForm] = useState<'test' | 'profile' | null>(null)
  if (soil.isPending) return <div className="mt-10"><FullPageSpinner /></div>
  if (soil.isError) return <div className="mt-8"><FormAlert>{soil.error.message}</FormAlert></div>
  const a = soil.data
  const toggle = (f: 'test' | 'profile') => setForm((cur) => (cur === f ? null : f))
  const btn = 'rounded-full border border-white/10 px-3 py-1.5 text-xs text-sage-200 hover:border-white/25'

  return (
    <div className="mt-8 space-y-5">
      {a.uses_simulated_data && (
        <DemoNote>Part of this assessment uses readings from the built-in <strong>simulated</strong> sensors.</DemoNote>
      )}
      <Card
        title={`${a.zone_name}${a.crop ? ` · ${a.crop.name}` : ''}`}
        action={
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btn} onClick={() => toggle('test')}>Add soil test</button>
            <button type="button" className={btn} onClick={() => toggle('profile')}>Add soil profile</button>
            <button type="button" className={btn} disabled={a.index == null || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? 'Saving…' : 'Save assessment'}
            </button>
          </div>
        }
      >
        <IndexSummary a={a} />
        {save.isSuccess && <p className="mt-3 text-xs text-moss-300" role="status">Assessment saved to history.</p>}
        {save.error && <div className="mt-3"><FormAlert>{save.error.message}</FormAlert></div>}
        {form === 'test' && <div className="mt-5 border-t border-white/5 pt-5"><SoilTestForm zoneId={zoneId} onDone={() => setForm(null)} /></div>}
        {form === 'profile' && <div className="mt-5 border-t border-white/5 pt-5"><SoilProfileForm zoneId={zoneId} onDone={() => setForm(null)} /></div>}
      </Card>

      <div className="grid gap-5 lg:grid-cols-5">
        <Card title="Root-zone water balance (FAO-56)" className="min-w-0 lg:col-span-3">
          {a.water ? <WaterPanel w={a.water} /> : <p className="text-sm text-sage-400">No moisture reading — add a soil test with moisture or provision sensors.</p>}
        </Card>
        <Card title="What drives the index" className="min-w-0 lg:col-span-2"><FactorList a={a} /></Card>
      </div>

      <Card title="Nutrients, pH and salinity"><ComponentsTable a={a} /></Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Guidance">
          {a.guidance.length ? (
            <ul className="space-y-2 text-sm">
              {a.guidance.map((g) => <li key={g.text} className="flex gap-2"><Pill tone={g.level === 'warning' ? 'warn' : 'info'}>{g.level}</Pill><span className="text-sage-200">{g.text}</span></li>)}
            </ul>
          ) : <p className="text-sm text-sage-400">No guidance — nothing out of range.</p>}
        </Card>
        <Card title="7-day sensor trends"><TrendList trends={a.trends} /></Card>
        <Card title="Saved assessments">
          {history.data?.items.length ? (
            <ul className="space-y-1.5 text-sm">
              {history.data.items.map((h) => {
                const idx = h.predicted_value.index
                return (
                  <li key={h.id} className="flex justify-between">
                    <span className="text-sage-300">{new Date(h.created_at).toLocaleString()}</span>
                    <span className="tabular-nums text-paper">{typeof idx === 'number' ? Math.round(idx) : '—'} · {Math.round(h.confidence * 100)} %</span>
                  </li>
                )
              })}
            </ul>
          ) : <p className="text-sm text-sage-400">None saved yet.</p>}
        </Card>
      </div>

      <Card title="Method and limitations">
        <p className="text-sm text-sage-300">{a.method}</p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-sage-400">{a.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Card>
    </div>
  )
}
