import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiBlobUrl, apiGet, apiSend } from '@/lib/api-client'

const num = z.number()
const nnum = z.number().nullable()
const anyRec = z.record(z.string(), z.unknown())

const Indicator = z.object({ indicator: z.string(), unit: z.string(), current: nnum, previous: nnum, change_pct: nnum })
export type Indicator = z.infer<typeof Indicator>

export const AnalyticsSchema = z.object({
  farm_id: num,
  farm_name: z.string(),
  period: z.object({ start: z.string(), end: z.string(), days: num, timezone: z.string() }),
  previous_period: z.object({ start: z.string(), end: z.string(), days: num }).passthrough(),
  area_ha: nnum,
  zones: num.optional(),
  indicators: z.array(Indicator),
  mean_stress_share: nnum,
  notes: z.array(z.string()),
  uses_simulated_data: z.boolean(),
  water: z
    .object({
      irrigation_events: num,
      events_without_volume: num,
      irrigation_liters: num,
      irrigation_mm: nnum,
      by_zone: z.array(z.object({ zone: z.string(), liters: num, mm: nnum })),
      rain_mm: nnum,
      et0_mm: nnum,
      weather_days_covered: num,
      stress: z.array(z.object({ zone: z.string(), measured_hours: num, threshold_pct: nnum, stress_share: nnum })),
    })
    .optional(),
  fertilizer: z.object({ applications: num, product_kg: num, organic_kg: num, nutrients_kg: anyRec, without_grade: num }).optional(),
  pesticides: z.object({ applications: num, by_type: z.record(z.string(), num), with_evidence: num }).optional(),
  health: z.object({ disease_checks: num, by_outcome: z.record(z.string(), num), possible_diseases: z.record(z.string(), num) }).optional(),
  harvests: z.array(z.object({ zone: z.string(), crop: z.string(), harvested_on: z.string(), yield_kg: nnum, yield_kg_ha: nnum })).optional(),
  advice: z.object({ recommendations: num, by_status: z.record(z.string(), num), uptake: nnum }).optional(),
  alerts: z.object({ raised: num, by_severity: z.record(z.string(), num), resolved: num, median_hours_to_resolve: nnum }).optional(),
  data: z.object({ readings: num, not_good_share: nnum, simulated_share: nnum, zones_without_area: z.array(z.string()) }).optional(),
})
export type Analytics = z.infer<typeof AnalyticsSchema>

const ReportMeta = z.object({
  id: num,
  farm_id: num,
  report_type: z.string(),
  title: z.string(),
  status: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  created_at: z.string(),
})
export type ReportMeta = z.infer<typeof ReportMeta>
export const ReportSchema = ReportMeta.extend({ content: AnalyticsSchema.partial({ previous_period: true }).passthrough() })
export type Report = z.infer<typeof ReportSchema>

export function useAnalytics(farmId: number | null, start: string, end: string) {
  return useQuery({
    queryKey: ['analytics', farmId, start, end],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/analytics?start=${start}&end=${end}`, AnalyticsSchema, { signal }),
    enabled: farmId != null && start <= end,
  })
}

export function useReports(farmId: number | null) {
  return useQuery({
    queryKey: ['reports', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/reports?limit=20`, z.object({ total: num, items: z.array(ReportMeta) }), { signal }),
    enabled: farmId != null,
  })
}

export function useReport(id: number) {
  return useQuery({ queryKey: ['report', id], queryFn: ({ signal }) => apiGet(`/reports/${id}`, ReportSchema, { signal }) })
}

export function useCreateReport(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { report_type: 'farm_summary' | 'sustainability'; period_start: string; period_end: string }) =>
      apiSend('POST', `/farms/${farmId}/reports`, ReportMeta.passthrough(), body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports', farmId] }),
  })
}

export function useDeleteReport(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiSend('DELETE', `/reports/${id}`, z.null()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports', farmId] }),
  })
}

/** Download the report CSV with the user's token (a plain link cannot carry it). */
export async function downloadCsv(report: ReportMeta): Promise<void> {
  const url = await apiBlobUrl(`/reports/${report.id}/csv`)
  const a = document.createElement('a')
  a.href = url
  a.download = `agri-sense-report-${report.id}-${report.period_start}-${report.period_end}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
