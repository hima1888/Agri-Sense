import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { AlertSchema } from '@/features/dashboard/schemas'
import { apiGet, apiSend } from '@/lib/api-client'

const num = z.number()
export const FullAlertSchema = AlertSchema.extend({ context: z.record(z.string(), z.unknown()).nullable().optional() })
export type FullAlert = z.infer<typeof FullAlertSchema>
const AlertPage = z.object({ total: num, items: z.array(FullAlertSchema) })

export const SettingsSchema = z.object({
  rules: z.array(z.object({ rule: z.string(), description: z.string(), enabled: z.boolean() })),
  thresholds: z.record(z.string(), num),
  defaults: z.record(z.string(), num),
})
export type AlertSettings = z.infer<typeof SettingsSchema>

const EvalSchema = z.object({ raised: num, updated: num, resolved: num, conditions: z.array(z.record(z.string(), z.unknown())) })

export function useAlerts(farmId: number | null, status: string) {
  return useQuery({
    queryKey: ['alerts', farmId, status],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/alerts?limit=100${status ? `&status=${status}` : ''}`, AlertPage, { signal }),
    enabled: farmId != null,
  })
}

export function useAlertSettings(farmId: number | null) {
  return useQuery({ queryKey: ['alert-settings', farmId], queryFn: ({ signal }) => apiGet(`/farms/${farmId}/alert-settings`, SettingsSchema, { signal }), enabled: farmId != null })
}

export function useEvaluate(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend('POST', `/farms/${farmId}/alerts/evaluate`, EvalSchema),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts', farmId] }),
  })
}

export function useAct(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'acknowledge' | 'resolve' }) => apiSend('POST', `/alerts/${id}/${action}`, AlertSchema),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['alerts', farmId] })
      void qc.invalidateQueries({ queryKey: ['dashboard', farmId] })
    },
  })
}

export function useSaveSettings(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { disabled_rules: string[]; thresholds: Record<string, number> }) => apiSend('PUT', `/farms/${farmId}/alert-settings`, SettingsSchema, body),
    onSuccess: (s) => qc.setQueryData(['alert-settings', farmId], s),
  })
}
