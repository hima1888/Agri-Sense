import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { FormAlert, SubmitButton } from '@/components/ui/form'
import { Pill, type Tone } from '@/components/ui/primitives'
import { useAct, useAlerts, useAlertSettings, useEvaluate, useSaveSettings, type AlertSettings, type FullAlert } from '@/features/alerts/api'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { ConnectionBadge } from '@/features/live/components'
import { useFarmStream } from '@/features/live/use-farm-stream'
import { useNow } from '@/lib/use-now'

const sel = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
const TONE: Record<string, Tone> = { critical: 'alert', warning: 'warn', info: 'info' }
const THRESHOLD_LABEL: Record<string, string> = {
  heat_c: 'Heat (°C, forecast max)', frost_c: 'Frost (°C, forecast min)', heavy_rain_mm: 'Heavy rain (mm/day)', wind_ms: 'Strong wind (m/s)',
  silent_hours: 'Sensor silent after (h)', bad_quality_share: 'Flagged readings share (0–1)', disease_days: 'Disease alert kept open (days)',
}

export function AlertsPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>
  const farm = farms.data.items.find((f) => f.id === Number(params.get('farm'))) ?? farms.data.items[0]!
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Alerts</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Alerts</h1>
        </div>
        <select aria-label="Farm" className={sel} value={farm.id} onChange={(e) => setParams({ farm: e.target.value })}>
          {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      <FarmAlerts key={farm.id} farmId={farm.id} />
    </div>
  )
}

function FarmAlerts({ farmId }: { farmId: number }) {
  const [status, setStatus] = useState('open')
  const alerts = useAlerts(farmId, status)
  const evaluate = useEvaluate(farmId)
  const stream = useFarmStream(farmId, 0)
  const qc = useQueryClient()
  const latest = stream.alertEvents[0]
  const now = useNow(10_000)
  useEffect(() => {
    if (latest) void qc.invalidateQueries({ queryKey: ['alerts', farmId] })
  }, [latest, qc, farmId])

  return (
    <div className="mt-8 space-y-5">
      {latest && now - latest.receivedAt < 60_000 && (
        <div role="status" className="rounded-xl border border-white/10 bg-ink-950/80 px-4 py-3 text-sm">
          <Pill tone={latest.type === 'resolved' ? 'ok' : TONE[latest.alert.severity] ?? 'muted'}>{latest.type}</Pill>
          <span className="ml-2 text-paper">{latest.alert.title}</span>
        </div>
      )}
      <Card
        title="Alerts"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <ConnectionBadge status={stream.status} />
            <select aria-label="Status" className={sel} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="open">Open</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option><option value="">All</option>
            </select>
            <button type="button" className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-sage-200 disabled:opacity-50" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>
              {evaluate.isPending ? 'Checking…' : 'Check now'}
            </button>
          </div>
        }
      >
        {evaluate.data && <p className="mb-3 text-xs text-sage-400" role="status">Checked: {evaluate.data.conditions.length} condition(s) true · {evaluate.data.raised} raised · {evaluate.data.resolved} resolved.</p>}
        {evaluate.error && <FormAlert>{evaluate.error.message}</FormAlert>}
        {alerts.isPending ? <p className="text-sm text-sage-400">Loading…</p> : alerts.data?.items.length ? (
          <ul className="space-y-3">{alerts.data.items.map((a) => <AlertRow key={a.id} a={a} farmId={farmId} />)}</ul>
        ) : <p className="text-sm text-sage-400">No {status || ''} alerts.</p>}
        <p className="mt-4 text-xs text-sage-400">Rules are checked automatically every few minutes; new and resolved alerts appear here live. Alerts are in-app only: no e-mail or SMS provider is configured.</p>
      </Card>
      <SettingsCard farmId={farmId} />
    </div>
  )
}

function AlertRow({ a, farmId }: { a: FullAlert; farmId: number }) {
  const act = useAct(farmId)
  const auto = a.context?.source === 'rule'
  const btn = 'rounded-full border border-white/10 px-3 py-1 text-xs text-sage-200 disabled:opacity-50'
  return (
    <li className="rounded-xl border border-white/5 p-3" aria-label={a.title}>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={TONE[a.severity] ?? 'muted'}>{a.severity}</Pill>
        <Pill>{a.category}</Pill>
        <span className="text-xs text-sage-400">{a.status}{auto ? ' · automatic' : ' · manual'}{a.context?.auto_resolved ? ' · resolved automatically' : ''}</span>
        <span className="ml-auto text-xs text-sage-400">{new Date(a.triggered_at).toLocaleString()}</span>
      </div>
      <p className="mt-2 text-paper">{a.title}</p>
      <p className="text-sm text-sage-300">{a.message}</p>
      {typeof a.context?.rule_description === 'string' && <p className="mt-1 text-xs text-sage-400">Rule: {a.context.rule_description}</p>}
      {a.status !== 'resolved' && (
        <div className="mt-2 flex gap-2">
          {a.status === 'open' && <button type="button" className={btn} disabled={act.isPending} onClick={() => act.mutate({ id: a.id, action: 'acknowledge' })}>Acknowledge</button>}
          <button type="button" className={btn} disabled={act.isPending} onClick={() => act.mutate({ id: a.id, action: 'resolve' })}>Resolve</button>
        </div>
      )}
    </li>
  )
}

function SettingsCard({ farmId }: { farmId: number }) {
  const settings = useAlertSettings(farmId)
  if (!settings.data) return null
  return <Card title="Alert settings"><SettingsForm key={JSON.stringify(settings.data)} farmId={farmId} s={settings.data} /></Card>
}

function SettingsForm({ farmId, s }: { farmId: number; s: AlertSettings }) {
  const save = useSaveSettings(farmId)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const thresholds: Record<string, number> = {}
    for (const k of Object.keys(s.thresholds)) {
      const v = Number(fd.get(`t_${k}`))
      if (v !== s.defaults[k]) thresholds[k] = v
    }
    save.mutate({ disabled_rules: s.rules.filter((r) => !fd.get(`r_${r.rule}`)).map((r) => r.rule), thresholds })
  }
  return (
    <form onSubmit={submit} className="space-y-4" aria-label="Alert settings">
      <fieldset className="grid gap-2 sm:grid-cols-2">
        <legend className="eyebrow mb-2">Rules</legend>
        {s.rules.map((r) => (
          <label key={r.rule} className="flex items-start gap-2 text-sm text-sage-200">
            <input type="checkbox" name={`r_${r.rule}`} defaultChecked={r.enabled} className="mt-1" /> {r.description}
          </label>
        ))}
      </fieldset>
      <fieldset className="grid gap-3 sm:grid-cols-3">
        <legend className="eyebrow mb-2">Thresholds</legend>
        {Object.entries(s.thresholds).map(([k, v]) => (
          <label key={k} className="block text-xs text-sage-300">
            {THRESHOLD_LABEL[k] ?? k}
            <input type="number" step="any" name={`t_${k}`} defaultValue={v} className={`mt-1 block w-full ${sel}`} />
          </label>
        ))}
      </fieldset>
      {save.error && <FormAlert>{save.error.message}</FormAlert>}
      {save.isSuccess && <p className="text-xs text-moss-300" role="status">Saved. Takes effect at the next check.</p>}
      <SubmitButton busy={save.isPending}>Save settings</SubmitButton>
    </form>
  )
}
