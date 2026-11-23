import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { FormAlert, SubmitButton } from '@/components/ui/form'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList, useZoneList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { DiseaseSection } from '@/features/disease/panels'
import { useDetections, useModelInfo, useRecognize } from '@/features/vision/api'
import { ExplainedImage, HistoryItem, ResultPanel } from '@/features/vision/panels'
import { useFilePreview } from '@/lib/use-file-preview'

const selectCls = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
const MAX_MB = 8

export function VisionPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>
  const farm = farms.data.items.find((f) => f.id === Number(params.get('farm'))) ?? farms.data.items[0]!

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Objective 1 · crop disease detection</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Disease detection</h1>
        </div>
        <select aria-label="Farm" className={selectCls} value={farm.id} onChange={(e) => setParams({ farm: e.target.value })}>
          {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      <VisionTabs key={farm.id} farmId={farm.id} />
    </div>
  )
}

function VisionTabs({ farmId }: { farmId: number }) {
  const [params, setParams] = useSearchParams()
  const zones = useZoneList(farmId)
  const tab = params.get('tab') === 'disease' ? 'disease' : 'produce'
  const tabCls = (t: string) => `rounded-full px-4 py-1.5 text-sm ${tab === t ? 'bg-paper text-ink-900' : 'text-sage-300 hover:text-paper'}`
  const go = (t: string) => setParams((p) => { p.set('tab', t); return p })
  return (
    <>
      <div role="tablist" aria-label="Vision tools" className="mt-6 inline-flex gap-1 rounded-full border border-white/10 p-1">
        <button type="button" role="tab" aria-selected={tab === 'produce'} className={tabCls('produce')} onClick={() => go('produce')}>Produce recognition</button>
        <button type="button" role="tab" aria-selected={tab === 'disease'} className={tabCls('disease')} onClick={() => go('disease')}>Leaf disease check</button>
      </div>
      <div className="mt-6">{tab === 'disease' ? <DiseaseSection farmId={farmId} zones={zones.data?.items ?? []} /> : <FarmVision farmId={farmId} />}</div>
    </>
  )
}

function FarmVision({ farmId }: { farmId: number }) {
  const zones = useZoneList(farmId)
  const model = useModelInfo()
  const history = useDetections(farmId)
  const recognize = useRecognize(farmId)
  const [file, setFile] = useState<File | null>(null)
  const [zoneId, setZoneId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const preview = useFilePreview(file)
  const zoneName = (id: number | null) => zones.data?.items.find((z) => z.id === id)?.name ?? null

  function pick(f: File | null) {
    recognize.reset()
    setError(null)
    if (f && !['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) return setError('Choose a JPEG, PNG or WebP image.')
    if (f && f.size > MAX_MB * 1024 * 1024) return setError(`Images must be at most ${MAX_MB} MB.`)
    setFile(f)
  }
  function submit(e: FormEvent) {
    e.preventDefault()
    if (!file) return setError('Choose a photo first.')
    recognize.mutate({ file, zoneId })
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-5">
        <Card title="Photo" className="lg:col-span-2">
          <p className="mb-4 rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-sage-200">
            Identifies <strong>which</strong> fruit or vegetable is in the photo (25 types); it does not check for disease.
            To check a plant for disease, use the <Link to="/vision?tab=disease" className="text-wheat-300 hover:underline">Leaf disease check</Link> with a photo of a leaf.
          </p>
          <form onSubmit={submit} className="space-y-4" aria-label="Recognise a photo">
            <label className="block text-sm text-sage-200">
              Photo of a fruit, vegetable or crop
              <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="mt-1.5 block w-full text-sm text-sage-300 file:mr-3 file:rounded-full file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-paper" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            </label>
            <label className="block text-sm text-sage-200">
              Zone (optional)
              <select className={`mt-1.5 block w-full ${selectCls}`} value={zoneId ?? ''} onChange={(e) => setZoneId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">No zone</option>
                {zones.data?.items.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
              </select>
            </label>
            {preview && <ExplainedImage src={preview} grid={recognize.data?.explanation.grid ?? null} />}
            {(error ?? recognize.error) && <FormAlert>{error ?? recognize.error?.message}</FormAlert>}
            <SubmitButton busy={recognize.isPending}>{recognize.isPending ? 'Analysing…' : 'Recognise'}</SubmitButton>
          </form>
        </Card>
        <Card title="Result" className="lg:col-span-3">
          {recognize.data ? <ResultPanel r={recognize.data} /> : <p className="text-sm text-sage-400">Upload a photo to see the prediction, its confidence, the regions it relied on and its limitations.</p>}
        </Card>
      </div>

      <Card title="Recognition history">
        {history.data?.items.length ? (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {history.data.items.map((d) => <HistoryItem key={d.id} d={d} farmId={farmId} zoneName={zoneName(d.zone_id)} />)}
          </ul>
        ) : <p className="text-sm text-sage-400">No recognitions saved yet.</p>}
      </Card>

      {model.data && (
        <Card title="About the model">
          <p className="text-sm text-sage-300">
            {model.data.name} ({model.data.version}), trained on {model.data.training_dataset}. Published accuracy over all 1000 classes:
            {' '}{Math.round(Number(model.data.metrics.top1_accuracy) * 1000) / 10} % top-1, {Math.round(Number(model.data.metrics.top5_accuracy) * 1000) / 10} % top-5 — not measured on farm photos.
            Results below {Math.round(model.data.min_confidence * 100)} % are marked uncertain.
          </p>
          <p className="mt-3 eyebrow">Supported classes ({model.data.supported.length})</p>
          <p className="mt-1 text-xs text-sage-400">{model.data.supported.map((s) => s.label).join(' · ')}</p>
          {!model.data.available && <div className="mt-3"><FormAlert>The model file is not installed on the server.</FormAlert></div>}
        </Card>
      )}
    </div>
  )
}
