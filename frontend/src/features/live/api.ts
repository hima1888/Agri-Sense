import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/auth-context'
import { apiGet, apiSend } from '@/lib/api-client'
import {
  BackfillResultSchema,
  FarmPageSchema,
  FarmSchema,
  ProvisionResultSchema,
  SimulatorStatusSchema,
  ZonePageSchema,
  ZoneSchema,
} from './schemas'

export function useFarms() {
  const { status, user } = useAuth()
  return useQuery({
    queryKey: ['farms', user?.id, 'list'],
    queryFn: ({ signal }) => apiGet('/farms?limit=100', FarmPageSchema, { signal }),
    enabled: status === 'signed_in',
  })
}

export function useZones(farmId: number | null) {
  return useQuery({
    queryKey: ['zones', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/zones?limit=100`, ZonePageSchema, { signal }),
    enabled: farmId != null,
  })
}

export function useSimulatorStatus(farmId: number | null) {
  return useQuery({
    queryKey: ['simulator', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/simulator`, SimulatorStatusSchema, { signal }),
    enabled: farmId != null,
    refetchInterval: 30_000,
  })
}

export interface QuickStartInput {
  name: string
  latitude: number
  longitude: number
  timezone: string
  zoneName: string
}

/** Create a farm and its first zone in one step (full farm setup arrives with the dashboard). */
export function useQuickStartFarm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: QuickStartInput) => {
      const farm = await apiSend('POST', '/farms', FarmSchema, {
        name: input.name,
        latitude: input.latitude,
        longitude: input.longitude,
        timezone: input.timezone,
      })
      await apiSend('POST', `/farms/${farm.id}/zones`, ZoneSchema, { name: input.zoneName })
      return farm
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['farms'] }),
  })
}

export function useProvisionZone(farmId: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (zoneId: number) => apiSend('POST', `/zones/${zoneId}/simulator/provision`, ProvisionResultSchema, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['simulator', farmId] }),
  })
}

export function useBackfill(farmId: number | null) {
  return useMutation({
    mutationFn: (hours: number) =>
      apiSend('POST', `/farms/${farmId}/simulator/backfill`, BackfillResultSchema, { hours, step_minutes: 10 }),
  })
}
