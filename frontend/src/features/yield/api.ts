import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet, apiSend } from '@/lib/api-client'

const num = z.number()
const nnum = z.number().nullable()
const Range = z.object({ low: num, central: num, high: num })

export const EstimateSchema = z.object({
  zone_id: num,
  zone_name: z.string(),
  status: z.enum(['estimate', 'no_reference', 'ky_unknown', 'no_crop', 'no_planting_date', 'no_harvest_date']),
  method: z.string(),
  message: z.string().optional(),
  crop: z.string().optional(),
  cycle_id: num.optional(),
  area_hectares: nnum.optional(),
  reference_is_custom: z.boolean().optional(),
  ky: num.optional(),
  ym_kg_ha: num.optional(),
  ym_source: z.string().nullable().optional(),
  yield_kg_ha: Range.optional(),
  total_kg: Range.optional(),
  relative_et: Range.optional(),
  water_loss_pct_central: nnum.optional(),
  season: z
    .object({ planted: z.string(), harvest: z.string(), days_total: num, days_elapsed: num, days_measured: num, coverage_elapsed: num, coverage_season: num })
    .optional(),
  factors: z.array(z.object({ name: z.string(), value: z.union([num, z.string()]).nullable(), unit: z.string(), source: z.string().nullable() })).optional(),
  confidence: num.optional(),
  limitations: z.array(z.string()).optional(),
  uses_simulated_data: z.boolean().optional(),
})
export type YieldEstimate = z.infer<typeof EstimateSchema>

const SavedPage = z.object({
  total: num,
  items: z.array(z.object({ id: num, created_at: z.string(), confidence: num, predicted_value: z.object({ low: num, central: num, high: num }).passthrough() })),
})

const Backtest = z.object({
  n: num,
  mean_absolute_error_pct: nnum,
  share_within_range: nnum,
  message: z.string().nullable(),
  cycles: z.array(z.object({ cycle_id: num, zone_name: z.string(), crop: z.string(), actual_kg_ha: num, predicted_central_kg_ha: num, error_pct: nnum, within_range: z.boolean() })),
})
export type BacktestResult = z.infer<typeof Backtest>

export function useYield(zoneId: number | null) {
  return useQuery({ queryKey: ['yield', zoneId], queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/yield`, EstimateSchema, { signal }), enabled: zoneId != null })
}

export function useSavedYields(zoneId: number | null) {
  return useQuery({ queryKey: ['yield-saved', zoneId], queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/yield/predictions?limit=10`, SavedPage, { signal }), enabled: zoneId != null })
}

export function useBacktest(farmId: number | null) {
  return useQuery({ queryKey: ['yield-backtest', farmId], queryFn: ({ signal }) => apiGet(`/farms/${farmId}/yield/backtest`, Backtest, { signal }), enabled: farmId != null })
}

export function useSetReference(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ cycleId, kg_ha, source }: { cycleId: number; kg_ha: number; source: string }) =>
      apiSend('PUT', `/crop-cycles/${cycleId}/yield-reference`, z.object({ cycle_id: num }), { kg_ha, source }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['yield', zoneId] }),
  })
}

export function useSaveYield(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend('POST', `/zones/${zoneId}/yield/predictions`, z.object({ id: num })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['yield-saved', zoneId] }),
  })
}
