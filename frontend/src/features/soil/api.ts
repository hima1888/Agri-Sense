import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet, apiSend } from '@/lib/api-client'
import { AssessmentSchema, SavedPage, SavedSchema } from './schemas'

export function useSoil(zoneId: number | null) {
  return useQuery({
    queryKey: ['soil', zoneId],
    queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/soil`, AssessmentSchema, { signal }),
    enabled: zoneId != null,
    refetchInterval: 5 * 60_000,
  })
}

export function useSoilHistory(zoneId: number | null) {
  return useQuery({
    queryKey: ['soil-history', zoneId],
    queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/soil/assessments?limit=10`, SavedPage, { signal }),
    enabled: zoneId != null,
  })
}

export function useSaveAssessment(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend('POST', `/zones/${zoneId}/soil/assessments`, SavedSchema),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['soil-history', zoneId] }),
  })
}

const Created = z.object({ id: z.number() })

/** Lab / field-kit soil test. Only non-null values are sent. */
export function useAddSoilTest(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => apiSend('POST', `/zones/${zoneId}/soil-measurements`, Created, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['soil', zoneId] }),
  })
}

export function useAddSoilProfile(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => apiSend('POST', `/zones/${zoneId}/soil-profiles`, Created, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['soil', zoneId] }),
  })
}
