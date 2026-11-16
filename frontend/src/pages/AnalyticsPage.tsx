import { DemoNote } from '@/components/ui/demo-note'
import { useState } from 'react'
import { localDate, localDateDaysAgo } from '@/lib/dates'
import { Link, useParams, useSearchParams } from 'react-router'
import { FormAlert } from '@/components/ui/form'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useFarmList } from '@/features/dashboard/api'
import { Card, EmptyFarms } from '@/features/dashboard/panels'
import { downloadCsv, useAnalytics, useCreateReport, useDeleteReport, useReport, useReports, type ReportMeta } from '@/features/reports/api'
import { IndicatorTable, Sections } from '@/features/reports/views'

const sel = 'rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-paper'
const iso = localDate
const daysAgo = localDateDaysAgo
const PRESETS = [7, 30, 90] as const

export function AnalyticsPage() {
  const farms = useFarmList()
  const [params, setParams] = useSearchParams()
  const [start, setStart] = useState(daysAgo(29))
  const [end, setEnd] = useState(iso(new Date()))
  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  if (!farms.data.items.length) return <div className="px-4 py-14"><EmptyFarms /></div>
  const farm = farms.data.items.find((f) => f.id === Number(params.get('farm'))) ?? farms.data.items[0]!
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Analytics &amp; reports</p>
          <h1 className="mt-2 font-display text-3xl text-paper">Analytics</h1>
        </div>
        <select aria-label="Farm" className={sel} value={farm.id} onChange={(e) => setParams({ farm: e.target.value })}>
          {farms.data.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      <div className="mt-6 flex flex-wrap items-end gap-3">
        {PRESETS.map((n) => (
          <button key={n} type="button" onClick={() => { setStart(daysAgo(n - 1)); setEnd(iso(new Date())) }}
            className={`rounded-full px-3 py-1.5 text-xs ${start === daysAgo(n - 1) && end === iso(new Date()) ? 'bg-paper text-ink-900' : 'border border-white/10 text-sage-200'}`}>
            Last {n} days
          </button>
        ))}
        <label className="text-xs text-sage-300">From <input aria-label="From" type="date" className={`${sel} ml-1`} value={start} max={end} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="text-xs text-sage-300">To <input aria-label="To" type="date" className={`${sel} ml-1`} value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>
      <FarmAnalytics key={farm.id} farmId={farm.id} start={start} end={end} />
    </div>
  )
}

function FarmAnalytics({ farmId, start, end }: { farmId: number; start: string; end: string }) {
  const a = useAnalytics(farmId, start, end)
  const reports = useReports(farmId)
  const create = useCreateReport(farmId)
  const [type, setType] = useState<'farm_summary' | 'sustainability'>('farm_summary')
  return (
    <div className="mt-6 space-y-5">
      {a.isPending && <FullPageSpinner />}
      {a.error && <FormAlert>{a.error.message}</FormAlert>}
      {a.data && (
        <>
          {a.data.uses_simulated_data && <DemoNote>This period includes <strong>simulated</strong> sensor data ({Math.round((a.data.data?.simulated_share ?? 0) * 100)} % of readings).</DemoNote>}
          <Card title="Sustainability indicators">
            <IndicatorTable indicators={a.data.indicators} previous={a.data.previous_period} />
          </Card>
          <Sections a={a.data} />
          <Card title="About these numbers">
            <ul className="list-disc space-y-1 pl-5 text-xs text-sage-400">{a.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </Card>
        </>
      )}
      <Card
        title="Saved reports"
        action={
          <div className="flex gap-2">
            <select aria-label="Report type" className={sel} value={type} onChange={(e) => setType(e.target.value as typeof type)}>
              <option value="farm_summary">Farm summary</option>
              <option value="sustainability">Sustainability indicators</option>
            </select>
            <button type="button" className="rounded-full bg-paper px-3 py-1.5 text-xs text-ink-900 disabled:opacity-50" disabled={create.isPending}
              onClick={() => create.mutate({ report_type: type, period_start: start, period_end: end })}>
              Save report for this period
            </button>
          </div>
        }
      >
        {create.error && <FormAlert>{create.error.message}</FormAlert>}
        {reports.data?.items.length ? (
          <ul className="space-y-2">{reports.data.items.map((r) => <ReportRow key={r.id} r={r} farmId={farmId} />)}</ul>
        ) : <p className="text-sm text-sage-400">No saved reports. A saved report is a snapshot: later edits to records do not change it.</p>}
      </Card>
    </div>
  )
}

function ReportRow({ r, farmId }: { r: ReportMeta; farmId: number }) {
  const del = useDeleteReport(farmId)
  const [err, setErr] = useState<string | null>(null)
  const btn = 'rounded-full border border-white/10 px-3 py-1 text-xs text-sage-200 hover:border-white/25 disabled:opacity-50'
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pt-2 text-sm">
      <span className="text-sage-200">{r.title}<span className="block text-xs text-sage-400">saved {new Date(r.created_at).toLocaleString()}</span></span>
      <span className="flex gap-2">
        <Link to={`/reports/${r.id}`} className={btn}>Open</Link>
        <button type="button" className={btn} onClick={() => downloadCsv(r).catch((e: Error) => setErr(e.message))}>CSV</button>
        <button type="button" className={btn} disabled={del.isPending} onClick={() => del.mutate(r.id)}>Delete</button>
      </span>
      {err && <span className="w-full text-xs text-signal-alert">{err}</span>}
    </li>
  )
}

/** Printable report: use the browser's Print → Save as PDF. */
export function ReportPage() {
  const id = Number(useParams().reportId)
  const report = useReport(id)
  if (report.isPending) return <FullPageSpinner />
  if (report.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{report.error.message}</FormAlert></div>
  const r = report.data
  const c = r.content
  return (
    <div className="print-sheet mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="no-print mb-6 flex gap-2">
        <Link to="/analytics" className="text-sm text-sage-400 hover:text-paper">← Analytics</Link>
        <button type="button" className="ml-auto rounded-full bg-paper px-3 py-1.5 text-xs text-ink-900" onClick={() => window.print()}>Print / save as PDF</button>
        <button type="button" className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-sage-200" onClick={() => void downloadCsv(r)}>CSV</button>
      </div>
      <p className="eyebrow">AGRI-SENSE report · {r.report_type.replace('_', ' ')}</p>
      <h1 className="mt-2 font-display text-3xl text-paper">{r.title}</h1>
      <p className="mt-1 text-sm text-sage-300">{c.farm_name} · {r.period_start} to {r.period_end}{c.area_ha != null && ` · ${c.area_ha} ha`} · saved {new Date(r.created_at).toLocaleString()}</p>
      {c.uses_simulated_data && <p className="mt-3 text-sm text-sage-400">Includes <strong>simulated</strong> sensor data (demo mode).</p>}
      <div className="mt-6 space-y-5">
        {c.indicators && <Card title="Sustainability indicators"><IndicatorTable indicators={c.indicators} previous={c.previous_period} /></Card>}
        <Sections a={c} />
        {c.notes && <Card title="About these numbers"><ul className="list-disc space-y-1 pl-5 text-xs text-sage-400">{c.notes.map((n) => <li key={n}>{n}</li>)}</ul></Card>}
      </div>
    </div>
  )
}
