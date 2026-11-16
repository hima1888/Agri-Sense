import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet, apiSend } from '@/lib/api-client'

const num = z.number()
const nnum = z.number().nullable()
const Metrics = z.object({ mae_persistence: num, mae_local_only: num, mae_federated: num, test_samples: num })
const Your = z.object({ train_samples: num, test_samples: num, mae_persistence: num, mae_local_only: num, mae_federated: num })

const Run = z.object({
  id: num,
  status: z.string(),
  rounds: num,
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  clients: nnum.optional(),
  overall: Metrics.nullable().optional(),
  history: z.array(z.object({ round: num, test_mse: num })).nullable().optional(),
  reason: z.string().nullable().optional(),
  uses_simulated_data: z.boolean().nullable().optional(),
  your_metrics: Your.nullable().optional(),
  explanation: z.array(z.object({ feature: z.string(), weight: num })).nullable().optional(),
  participated: z.boolean(),
})
export type FlRun = z.infer<typeof Run>

export const FarmFlSchema = z.object({
  farm_id: num,
  enrollment: z.object({ status: z.string(), client_key: z.string(), enrolled_at: z.string(), last_seen_at: z.string().nullable() }).nullable(),
  local_samples: num,
  min_samples: num,
  uses_simulated_data: z.boolean(),
  shared: z.string(),
  not_shared: z.string(),
  runs: z.array(Run),
  limitations: z.array(z.string()),
})
export type FarmFl = z.infer<typeof FarmFlSchema>

export const ForecastSchema = z.object({
  status: z.enum(['forecast', 'no_model', 'no_recent_data']),
  message: z.string().optional(),
  model_version: z.string().optional(),
  moisture_now_pct: num.optional(),
  predicted_change_6h_pct_points: num.optional(),
  predicted_moisture_6h_pct: num.optional(),
  expected_error_pct_points: nnum.optional(),
  persistence_error_pct_points: nnum.optional(),
  beats_baseline: z.boolean().optional(),
  advice: z.string().nullable().optional(),
  uses_simulated_data: z.boolean().optional(),
})
export type Forecast = z.infer<typeof ForecastSchema>

export function useFarmFl(farmId: number | null) {
  return useQuery({ queryKey: ['fl', farmId], queryFn: ({ signal }) => apiGet(`/farms/${farmId}/federated`, FarmFlSchema, { signal }), enabled: farmId != null })
}

export function useForecast(zoneId: number | null) {
  return useQuery({ queryKey: ['fl-forecast', zoneId], queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/federated/forecast`, ForecastSchema, { signal }), enabled: zoneId != null })
}

export function useEnrollment(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (action: 'enroll' | 'leave') => apiSend('POST', `/farms/${farmId}/federated/${action}`, z.object({ status: z.string() })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fl', farmId] }),
  })
}
