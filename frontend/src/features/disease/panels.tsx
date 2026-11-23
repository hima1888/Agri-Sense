import { Link } from 'react-router'
import { useState, type FormEvent } from 'react'
import { FormAlert, SubmitButton } from '@/components/ui/form'
import { Pill, type Tone } from '@/components/ui/primitives'
import { Card } from '@/features/dashboard/panels'
import { cropZoneName, useCreateCropZone } from '@/features/dashboard/demo'
import type { ZoneDetail } from '@/features/dashboard/schemas'
import { pct } from '@/lib/percent'
import { useAuthedImage } from '@/lib/use-authed-image'
import { useFilePreview } from '@/lib/use-file-preview'
import { HealthyPanel, KnowledgePanel, KnowledgeToggle } from './knowledge'
import { useDeleteDiseaseCheck, useDiseaseChecks, useDiseaseModels, useScreenLeaf, type DiseaseRecord, type Part, type Screening } from './api'

const selectCls = 'mt-1.5 block w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'

const OUTCOME: Record<Screening['outcome'], { title: string; tone: Tone }> = {
  possible_disease: { title: 'Possible disease', tone: 'warn' },
  possible_healthy: { title: 'Possibly healthy', tone: 'ok' },
  uncertain: { title: 'Uncertain', tone: 'muted' },
  cannot_identify: { title: 'Cannot reliably identify', tone: 'muted' },
  not_a_leaf: { title: 'Not a leaf photo', tone: 'muted' },
  unsupported_crop: { title: 'Crop not supported', tone: 'muted' },
}

export function ScreeningResult({ r }: { r: Screening }) {
  const o = r.outcome === 'not_a_leaf' && r.part === 'fruit' ? { title: 'Not the chosen fruit', tone: 'muted' as Tone } : OUTCOME[r.outcome]
  const confident = r.outcome === 'possible_disease' || r.outcome === 'possible_healthy'
  return (
    <div className="space-y-5">
      <div>
        <Pill tone={o.tone}>{o.title}</Pill>
        {r.label && <p className="mt-3 font-display text-3xl text-paper">{confident ? r.label : `Best guess: ${r.label}`}</p>}
        <p className="mt-2 text-sm text-sage-200">{r.reason}</p>
        <p className="mt-1 text-xs text-sage-400">
          {r.model ? `Model: ${r.model.name} (${r.model.version})` : 'No model was run.'}
          {r.crop && ` · crop: ${r.crop}${r.crop_source ? ` (from ${r.crop_source})` : ''}`}
          {r.confidence != null && ` · model confidence ${pct(r.confidence)}`}
          {r.margin != null && ` · margin ${(r.margin * 100).toFixed(1)} pts`}
        </p>
        <p className="mt-1 text-xs text-sage-400">
          {r.saved ? 'Saved to disease-check history.' : 'Not saved.'}
          {r.saved && r.detection_id != null && (
            <> <Link to={`/vision/disease-checks/${r.detection_id}/report`} className="ml-1 font-medium text-wheat-300 hover:underline">Open full report (PDF)</Link></>
          )}
        </p>
      </div>

      {r.outcome === 'possible_disease' && (
        <p className="text-sm text-sage-300">
          {r.part === 'fruit'
            ? 'Severity is not estimated for fruit photos.'
            : <>Affected area (colour heuristic): {r.affected_area_pct == null ? 'not estimated' : `${r.affected_area_pct} %`} · severity {r.severity}</>}
        </p>
      )}

      {r.checks.length > 0 && (
        <div>
          <p className="eyebrow">Checks</p>
          <ul className="mt-2 space-y-1 text-xs">
            {r.checks.map((c) => (
              <li key={c.rule} className="flex gap-2">
                <span aria-hidden className={c.passed ? 'text-moss-300' : 'text-signal-alert'}>{c.passed ? '✓' : '✗'}</span>
                <span className="text-sage-300"><span className="sr-only">{c.passed ? 'passed' : 'failed'}: </span>{c.rule.replaceAll('_', ' ')} — {c.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {r.candidates.length > 0 && (
        <div>
          <p className="eyebrow">Model candidates (all classes)</p>
          <ul className="mt-2 space-y-1.5">
            {r.candidates.map((c) => (
              <li key={c.label}>
                <div className="flex justify-between text-sm"><span className="text-paper">{c.label}</span><span className="tabular-nums text-sage-300">{pct(c.confidence)}</span></div>
                <div className="mt-0.5 h-1 rounded-full bg-white/10"><div className="h-full rounded-full bg-wheat-300" style={{ width: `${c.confidence * 100}%` }} /></div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {r.outcome === 'possible_disease' && (r.knowledge ? <KnowledgePanel k={r.knowledge} /> : (
        <p className="text-sm text-sage-400">No knowledge entry for this label.</p>
      ))}
      {r.outcome === 'possible_healthy' && r.healthy_guidance && <HealthyPanel g={r.healthy_guidance} />}
      {r.outcome === 'uncertain' && (
        <p className="text-sm text-sage-300">
          No disease guidance is shown because the result is uncertain. Retake the photo (one leaf, good light, plain background) or ask an expert.
        </p>
      )}

      <div>
        <p className="eyebrow">Limitations</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-sage-400">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </div>
    </div>
  )
}

function HistoryRow({ d, farmId, zoneName }: { d: DiseaseRecord; farmId: number; zoneName: string | null }) {
  const src = useAuthedImage(`/vision/disease-checks/${d.id}/image`)
  const del = useDeleteDiseaseCheck(farmId)
  const outcome = typeof d.explanation?.outcome === 'string' ? d.explanation.outcome : ''
  const model = (d.explanation?.model as { name?: string } | undefined)?.name
  return (
    <li className="glass overflow-hidden rounded-xl">
      <div className="aspect-square bg-ink-950">{src && <img src={src} alt={`Leaf checked: ${d.disease_label}`} className="h-full w-full object-cover" />}</div>
      <div className="p-3 text-xs">
        <p className="text-sm text-paper">{d.disease_label}</p>
        <p className="text-sage-400">{outcome.replaceAll('_', ' ')} · {pct(d.confidence)}{zoneName ? ` · ${zoneName}` : ''}</p>
        {model && <p className="text-sage-400">{model}</p>}
        <p className="text-sage-400">{new Date(d.detected_at).toLocaleString()}</p>
        <Link to={`/vision/disease-checks/${d.id}/report`} className="block text-wheat-300 hover:underline">Full report (PDF)</Link>
        {d.knowledge_key && outcome === 'possible_disease' && <KnowledgeToggle k={d.knowledge_key} />}
        <button type="button" className="mt-1.5 text-signal-alert/80 hover:text-signal-alert disabled:opacity-50" disabled={del.isPending} onClick={() => del.mutate(d.id)}>Delete</button>
      </div>
    </li>
  )
}

export function DiseaseSection({ farmId, zones }: { farmId: number; zones: ZoneDetail[] }) {
  const models = useDiseaseModels()
  const history = useDiseaseChecks(farmId)
  const screen = useScreenLeaf(farmId)
  const [file, setFile] = useState<File | null>(null)
  const [part, setPart] = useState<Part>('leaf')
  const [crop, setCrop] = useState('')
  const [zoneId, setZoneId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const preview = useFilePreview(file)
  const crops = Object.keys((part === 'fruit' ? models.data?.supported_fruits : models.data?.supported_crops) ?? {})
  const zoneName = (id: number | null) => zones.find((z) => z.id === id)?.name ?? null
  const addZone = useCreateCropZone(farmId)
  const newZoneName = crop ? cropZoneName(crop) : null
  const canAddZone = newZoneName != null && !zones.some((z) => z.name.toLowerCase() === newZoneName.toLowerCase())

  function chooseZone(value: string) {
    if (value !== 'new') return setZoneId(value ? Number(value) : null)
    addZone.mutate(crop, { onSuccess: (id) => setZoneId(id) })
  }
  function chooseCrop(value: string) {
    setCrop(value)
    const own = value ? zones.find((z) => z.name.toLowerCase() === cropZoneName(value).toLowerCase()) : undefined
    if (own) setZoneId(own.id)
  }

  function choosePart(p: Part) {
    screen.reset()
    setPart(p)
    if (crop && !(p === 'fruit' ? models.data?.supported_fruits : models.data?.supported_crops)?.[crop]) setCrop('')
  }
  function pick(f: File | null) {
    screen.reset()
    setError(null)
    if (f && !['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) return setError('Choose a JPEG, PNG or WebP image.')
    setFile(f)
  }
  function submit(e: FormEvent) {
    e.preventDefault()
    if (!file) return setError('Choose a leaf photo first.')
    if (!crop && zoneId == null) return setError('Choose the crop, or a zone with a crop planted.')
    screen.mutate({ file, crop: crop || null, zoneId, part })
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-5">
        <Card title="Disease check" className="lg:col-span-2">
          <p className="rounded-lg border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-sage-200">A first screening, not a diagnosis: confirm with an agronomist before any treatment. The models were trained on lab photos, so accuracy on field photos is limited (see <em>About the disease models</em>).</p>
          <form onSubmit={submit} className="mt-4 space-y-4" aria-label="Check a leaf for disease">
            <div role="radiogroup" aria-label="What the photo shows" className="flex gap-1 rounded-full border border-white/10 p-0.5 text-sm">
              {(['leaf', 'fruit'] as const).map((p) => (
                <button key={p} type="button" role="radio" aria-checked={part === p} onClick={() => choosePart(p)}
                  className={`flex-1 rounded-full px-3 py-1.5 ${part === p ? 'bg-white/10 text-paper' : 'text-sage-400 hover:text-sage-100'}`}>
                  {p === 'leaf' ? 'Leaf' : 'Fruit'}
                </button>
              ))}
            </div>
            {part === 'fruit' && (
              <p className="text-xs text-sage-400">
                Fruit checks cover: {crops.join(', ') || 'none installed'} (citrus canker, melanose or healthy). Other fruits need their own model and are not supported yet.
              </p>
            )}
            <label className="block text-sm text-sage-200">
              {part === 'leaf' ? 'Photo of one leaf' : 'Photo of one fruit'}
              <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="mt-1.5 block w-full text-sm text-sage-300 file:mr-3 file:rounded-full file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-paper" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm text-sage-200">
                Crop
                <select className={selectCls} value={crop} onChange={(e) => chooseCrop(e.target.value)}>
                  <option value="">From zone</option>
                  {crops.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label className="block text-sm text-sage-200">
                Zone
                <select className={selectCls} value={zoneId ?? ''} disabled={addZone.isPending} onChange={(e) => chooseZone(e.target.value)}>
                  <option value="">No zone</option>
                  {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
                  {canAddZone && <option value="new">+ New zone: {newZoneName}</option>}
                </select>
                {addZone.isPending && <span className="mt-1 block text-xs text-sage-400">Creating zone with live sensors…</span>}
                {addZone.isError && <span className="mt-1 block text-xs text-sage-400">Could not create the zone: {addZone.error.message}</span>}
              </label>
            </div>
            {preview && <img src={preview} alt="Leaf to check" className="max-h-64 w-full rounded-xl object-contain" />}
            {(error ?? screen.error) && <FormAlert>{error ?? screen.error?.message}</FormAlert>}
            <SubmitButton busy={screen.isPending}>{screen.isPending ? 'Checking…' : part === 'leaf' ? 'Check leaf' : 'Check fruit'}</SubmitButton>
          </form>
        </Card>
        <Card title="Disease result" className="lg:col-span-3">
          {screen.data ? <ScreeningResult r={screen.data} /> : <p className="text-sm text-sage-400">The result shows which model answered, its confidence, the checks it passed or failed, and its limitations.</p>}
        </Card>
      </div>

      <Card title="Disease-check history">
        {history.data?.items.length ? (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {history.data.items.map((d) => <HistoryRow key={d.id} d={d} farmId={farmId} zoneName={zoneName(d.zone_id)} />)}
          </ul>
        ) : <p className="text-sm text-sage-400">No disease checks saved yet.</p>}
      </Card>

      {models.data && (
        <Card title="About the disease models">
          <ul className="space-y-3 text-sm text-sage-300">
            {models.data.models.map((m) => (
              <li key={m.key}>
                <p className="text-paper">{m.name} {!m.available && <Pill tone="alert">not installed</Pill>}</p>
                <p className="text-xs">{m.architecture}. Used for: {m.used_for.join(', ')}. Licence: {m.licence}.</p>
                <p className="text-xs text-sage-400">Published accuracy: {m.published_accuracy}. Not measured on field photos.</p>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-sage-400">
            A result counts only if the model's top answer is the chosen crop, with at least {Math.round(models.data.thresholds.min_top1 * 100)} % confidence and a {Math.round(models.data.thresholds.min_margin * 100)}-point lead. These thresholds are untuned.
          </p>
        </Card>
      )}
    </div>
  )
}
