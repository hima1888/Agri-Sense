import { useState } from 'react'
import { Pill } from '@/components/ui/primitives'
import { pct } from '@/lib/percent'
import { useDeleteDetection, useDetectionImage, type Detection, type Recognition } from './api'


/** Centre-square crop of the photo (what the model sees) with the occlusion heat-map on top. */
export function ExplainedImage({ src, grid }: { src: string; grid: number[][] | null }) {
  const [show, setShow] = useState(true)
  return (
    <figure>
      <div className="relative aspect-square w-full overflow-hidden rounded-xl bg-ink-950">
        <img src={src} alt="Uploaded photo, centre crop" className="h-full w-full object-cover" />
        {grid && show && (
          <div aria-hidden className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${grid.length}, 1fr)` }}>
            {grid.flat().map((v, i) => (
              <span key={i} style={{ background: `rgb(217 89 38 / ${(v * 0.6).toFixed(2)})` }} />
            ))}
          </div>
        )}
      </div>
      <figcaption className="mt-2 flex items-center justify-between gap-3 text-xs text-sage-400">
        <span>{grid ? 'Orange = regions the prediction relied on most (occlusion test).' : 'No heat-map: nothing was recognised.'}</span>
        {grid && (
          <label className="flex items-center gap-1.5 whitespace-nowrap">
            <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Heat-map
          </label>
        )}
      </figcaption>
    </figure>
  )
}

export function ResultPanel({ r }: { r: Recognition }) {
  const tone = r.outcome === 'recognized' ? 'ok' : r.outcome === 'uncertain' ? 'warn' : 'muted'
  return (
    <div className="space-y-5">
      <div>
        <Pill tone={tone}>{r.outcome}</Pill>
        <p className="mt-3 font-display text-3xl text-paper">
          {r.outcome === 'unsupported' ? 'Not a supported produce class' : r.label}
        </p>
        {r.outcome !== 'unsupported' && (
          <p className="mt-1 text-sm text-sage-300">
            {r.subject_type} · confidence {pct(r.confidence)}
            {r.outcome === 'uncertain' && ' — low confidence, treat as a guess'}
          </p>
        )}
        <p className="mt-1 text-xs text-sage-400">{r.saved ? 'Saved to recognition history.' : 'Not saved (nothing recognised).'}</p>
      </div>

      {r.outcome !== 'unsupported' && (
        <div>
          <p className="eyebrow">Top produce candidates</p>
          <ul className="mt-2 space-y-1.5">
            {r.candidates.map((c) => (
              <li key={c.label}>
                <div className="flex justify-between text-sm"><span className="text-paper">{c.label}</span><span className="tabular-nums text-sage-300">{pct(c.confidence)}</span></div>
                <div className="mt-0.5 h-1 rounded-full bg-white/10"><div className="h-full rounded-full bg-moss-400" style={{ width: `${c.confidence * 100}%` }} /></div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="eyebrow">What the general model sees (all 1000 ImageNet classes)</p>
        <p className="mt-1 text-sm text-sage-300">{r.model_sees.map((m) => `${m.label} ${pct(m.confidence)}`).join(' · ')}</p>
      </div>

      <div>
        <p className="eyebrow">Image quality</p>
        <ul className="mt-2 grid grid-cols-2 gap-2 text-xs">
          {r.quality.map((q) => (
            <li key={q.key} title={q.note} className="flex items-center justify-between rounded-lg border border-white/5 px-2.5 py-1.5">
              <span className="text-sage-300">{q.key}</span>
              <Pill tone={q.status === 'ok' ? 'ok' : 'warn'}>{q.status}</Pill>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="eyebrow">Limitations</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-sage-400">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="mt-2 text-xs text-sage-400">Method: {r.explanation.method}. Model: {r.model.name} ({r.model.version}).</p>
      </div>
    </div>
  )
}

export function HistoryItem({ d, farmId, zoneName }: { d: Detection; farmId: number; zoneName: string | null }) {
  const src = useDetectionImage(d.id)
  const del = useDeleteDetection(farmId)
  const outcome = typeof d.explanation?.outcome === 'string' ? d.explanation.outcome : null
  return (
    <li className="glass overflow-hidden rounded-xl">
      <div className="aspect-square bg-ink-950">{src && <img src={src} alt={`Photo recognised as ${d.predicted_label}`} className="h-full w-full object-cover" />}</div>
      <div className="p-3 text-xs">
        <p className="text-sm text-paper">{d.predicted_label}</p>
        <p className="text-sage-400">{pct(d.confidence)}{outcome === 'uncertain' ? ' · uncertain' : ''}{zoneName ? ` · ${zoneName}` : ''}</p>
        <p className="text-sage-400">{new Date(d.detected_at).toLocaleString()}</p>
        <button type="button" className="mt-1.5 text-signal-alert/80 hover:text-signal-alert disabled:opacity-50" disabled={del.isPending} onClick={() => del.mutate(d.id)}>
          Delete
        </button>
      </div>
    </li>
  )
}
