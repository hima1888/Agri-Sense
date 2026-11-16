import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet, apiSend } from '@/lib/api-client'

const num = z.number()
const Factor = z.object({ name: z.string(), value: z.unknown(), unit: z.string(), source: z.string(), simulated: z.boolean() })
export type Factor = z.infer<typeof Factor>
export const PRIORITIES = ['critical', 'high', 'medium', 'low'] as const

const Rec = z.object({
  id: num.nullable().optional(),
  rule: z.string(),
  zone_id: num.nullable(),
  zone_name: z.string().nullable(),
  category: z.string(),
  priority: z.enum(PRIORITIES),
  title: z.string(),
  rationale: z.string(),
  action: z.record(z.string(), z.unknown()),
  factors: z.array(Factor),
  confidence: num,
  confidence_basis: z.string(),
  expected_impact: z.record(z.string(), z.unknown()).nullable(),
  limitations: z.array(z.string()),
  uses_simulated_data: z.boolean(),
  expires_at: z.string(),
})
export type Recommendation = z.infer<typeof Rec>

export const RecSetSchema = z.object({
  farm_id: num,
  generated_at: z.string(),
  method: z.string(),
  weather_fetched_at: z.string().nullable(),
  forecast_hours: num,
  zones_assessed: num,
  recommendations: z.array(Rec),
  uses_simulated_data: z.boolean(),
  stored: z.object({ created: num, refreshed: num, expired: num }).nullable().optional(),
})
export type RecSet = z.infer<typeof RecSetSchema>

const Stored = z.object({
  id: num,
  zone_id: num.nullable(),
  rule: z.string().nullable(),
  priority: z.string(),
  status: z.enum(['pending', 'accepted', 'rejected', 'applied', 'expired']),
  title: z.string(),
  confidence: num,
  created_at: z.string(),
  responded_at: z.string().nullable(),
})
export type StoredRec = z.infer<typeof Stored>
const StoredPage = z.object({ total: num, items: z.array(Stored) })

export function useGenerate(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend('POST', `/farms/${farmId}/recommendations/generate`, RecSetSchema),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recs', farmId] }),
  })
}

export function useStored(farmId: number) {
  return useQuery({
    queryKey: ['recs', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/recommendations?limit=100`, StoredPage, { signal }),
  })
}

export function useRespond(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'accepted' | 'rejected' | 'applied' }) =>
      apiSend('POST', `/recommendations/${id}/respond`, Stored, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recs', farmId] }),
  })
}
