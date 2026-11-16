import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { FormAlert } from '@/components/ui/form'
import { Pill } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { plantForm, useCrops, useGrowth, type CropGrowth, type StageKey } from '@/features/growth/api'
import { PlantIllustration } from '@/features/growth/Plant'
import { useTwin } from '@/features/twin/api'

const sel = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'

function Timeline({ g, active, onPick }: { g: CropGrowth; active: StageKey; onPick: (k: StageKey) => void }) {
  const day = g.current?.day
  return (
    <div>
      <ol className="flex h-14 overflow-hidden rounded-lg border border-white/10" aria-label="Growth stages">
        {g.stages.map((s) => {
          const days = Math.max(1, s.end_day - s.start_day + 1)
          const isCurrent = g.current?.stage_key === s.key
          return (
            <li key={s.key} style={{ flexGrow: s.key === 'seed' || s.key === 'harvest' ? 0 : days, flexBasis: s.key === 'seed' || s.key === 'harvest' ? '2.25rem' : 0 }}>
              <button
                type="button"
                onClick={() => onPick(s.key)}
                aria-current={active === s.key ? 'step' : undefined}
                className={`flex h-full w-full flex-col items-center justify-center border-r border-white/10 px-1 text-[10px] leading-tight transition-colors ${active === s.key ? 'bg-moss-500/40 text-paper' : 'bg-ink-950/40 text-sage-300 hover:bg-white/5'}`}
                title={`${s.name}: day ${s.start_day}–${s.end_day}`}
              >
                <span className="truncate">{s.name}</span>
                {isCurrent && <span className="mt-0.5 rounded-full bg-wheat-300 px-1 text-[9px] text-ink-950">today</span>}
              </button>
            </li>
          )
        })}
      </ol>
      <div className="mt-1 flex justify-between text-[10px] text-sage-400">
        <span>Day 0 (sowing)</span>
        {day != null && day >= 0 && <span>Today: day {day}</span>}
        <span>Day {g.cycle_days} (harvest)</span>
      </div>
    </div>
  )
}

function GrowthView({ g, category }: { g: CropGrowth; category?: string }) {
  const initial = g.current?.stage_key ?? 'seed'
  const [active, setActive] = useState<StageKey>(initial)
  const [playing, setPlaying] = useState(false)
  useEffect(() => {
    if (!playing) return
    const i = g.stages.findIndex((s) => s.key === active)
    const s = g.stages[i]
    const next = g.stages[i + 1]
    if (!s) return
    // Each stage stays on screen in proportion to its real length in days (60 ms per day, at least 0.7 s).
    const ms = Math.max(700, (s.end_day - s.start_day + 1) * 60)
    const id = setTimeout(() => (next ? setActive(next.key) : setPlaying(false)), ms)
    return () => clearTimeout(id)
  }, [playing, active, g])
  const stage = g.stages.find((s) => s.key === active)!
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-5">
        <Card title={`${g.crop} · ${stage.name}`} className="lg:col-span-2">
          <PlantIllustration stage={active} form={plantForm(g.crop_key, category)} label={`${g.crop} at the ${stage.name.toLowerCase()} stage`} />
          <div className="mt-2 flex gap-2">
            <button type="button" className="rounded-full bg-moss-500 px-4 py-1.5 text-sm text-paper hover:bg-moss-400" onClick={() => (active === 'harvest' && setActive('seed'), setPlaying((p) => !p))}>
              {playing ? 'Pause' : active === 'harvest' ? 'Replay' : 'Play growth'}
            </button>
            {g.current?.stage_key && (
              <button type="button" className="rounded-full border border-white/15 px-4 py-1.5 text-sm text-sage-200 hover:bg-white/5" onClick={() => (setPlaying(false), setActive(g.current!.stage_key!))}>
                Show today
              </button>
            )}
          </div>
        </Card>
        <Card title="This stage" className="lg:col-span-3">
          <p className="font-display text-2xl text-paper">{stage.name}</p>
          <p className="mt-1 text-sm text-sage-300">
            {stage.start_day === stage.end_day ? `Day ${stage.start_day}` : `Days ${stage.start_day}–${stage.end_day} (${stage.end_day - stage.start_day + 1} days)`} · FAO-56 stage: {stage.fao_stage}
            {stage.approximate_boundary && <> · <Pill tone="muted">approximate boundary</Pill></>}
          </p>
          <p className="mt-3 text-sm text-sage-200">{stage.description}</p>
          {g.current && (
            <p className="mt-3 text-sm text-sage-300">
              This crop cycle was sown {g.planted_on ? new Date(g.planted_on).toLocaleDateString() : '—'}; today is day {g.current.day} ({Math.round(g.current.progress * 100)}% of the cycle).
              {g.current.note && ` ${g.current.note}`}
            </p>
          )}
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-sage-400 sm:grid-cols-4">
            <div><dt>Initial</dt><dd className="text-paper">{g.fao56.initial} d</dd></div>
            <div><dt>Development</dt><dd className="text-paper">{g.fao56.development} d</dd></div>
            <div><dt>Mid-season</dt><dd className="text-paper">{g.fao56.mid_season} d</dd></div>
            <div><dt>Late season</dt><dd className="text-paper">{g.fao56.late_season} d</dd></div>
          </dl>
          <p className="mt-1 text-xs text-sage-400">FAO-56 Table 11 ({g.fao56.region}), scaled to {g.cycle_days} days from the {g.cycle_days_source}.</p>
        </Card>
      </div>
      <Card title="Stages from sowing to harvest">
        <Timeline g={g} active={active} onPick={(k) => (setPlaying(false), setActive(k))} />
        <p className="mt-3 text-xs text-sage-400">{g.method}</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-sage-400">{g.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Card>
    </div>
  )
}

export function GrowthPage() {
  const farms = useFarmList()
  const crops = useCrops()
  const [params, setParams] = useSearchParams()
  const farmId = farms.data?.items.find((f) => f.id === Number(params.get('farm')))?.id ?? farms.data?.items[0]?.id ?? null
  const twin = useTwin(farmId)
  const supported = new Set((crops.data ?? []).map((c) => c.common_name))
  const cycles = (twin.data?.zones ?? []).filter((z) => z.crop && supported.has(z.crop.crop_name)).map((z) => ({ zone: z.name, ...z.crop! }))
  const first = cycles[0] ? `cycle:${cycles[0].cycle_id}` : crops.data?.[0] ? `crop:${crops.data[0].id}` : null
  const requested = params.get('pick')
  const valid = (p: string) => p.startsWith('cycle:') ? cycles.some((c) => `cycle:${c.cycle_id}` === p) : (crops.data ?? []).some((c) => `crop:${c.id}` === p)
  const pick = requested && valid(requested) ? requested : first
  const [kind, idText] = pick?.split(':') ?? []
  const target = kind === 'cycle' ? { cycleId: Number(idText) } : kind === 'crop' ? { cropId: Number(idText) } : null
  const growth = useGrowth(target)
  const category = kind === 'cycle' ? cycles.find((c) => c.cycle_id === Number(idText))?.category : crops.data?.find((c) => c.id === Number(idText))?.category

  if (farms.isPending || crops.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Crop growth</p>
          <h1 className="mt-2 font-display text-3xl text-paper">From seed to harvest</h1>
          <p className="mt-1 max-w-xl text-sm text-sage-300">Stages and their lengths come from FAO-56 crop data via the API; for a zone's crop cycle the app also shows where it is today.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select aria-label="Farm" className={sel} value={farmId ?? ''} onChange={(e) => setParams({ farm: e.target.value })}>
            {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <select aria-label="Crop" className={sel} value={pick ?? ''} onChange={(e) => setParams({ farm: String(farmId), pick: e.target.value })}>
            {cycles.length > 0 && (
              <optgroup label="Crops in your zones">
                {cycles.map((c) => <option key={c.cycle_id} value={`cycle:${c.cycle_id}`}>{c.crop_name} · {c.zone}</option>)}
              </optgroup>
            )}
            <optgroup label="Crop catalogue">
              {(crops.data ?? []).map((c) => <option key={c.id} value={`crop:${c.id}`}>{c.common_name}</option>)}
            </optgroup>
          </select>
        </div>
      </div>

      <div className="mt-8">
        {!target && <Card title="Crop growth"><p className="text-sm text-sage-400">Add a crop to one of your zones to see its growth stages here.</p></Card>}
        {target && growth.isPending && <p className="text-sm text-sage-400" role="status">Loading growth stages…</p>}
        {growth.isError && (
          <Card title="Could not load growth stages">
            <FormAlert>{growth.error.message}</FormAlert>
          </Card>
        )}
        {growth.data && <GrowthView key={`${pick}`} g={growth.data} category={category} />}
      </div>
    </div>
  )
}
