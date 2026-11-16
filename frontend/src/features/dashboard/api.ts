import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { useAuth } from '@/features/auth/auth-context'
import type { SensorType } from '@/features/live/schemas'
import { apiGet, apiSend } from '@/lib/api-client'
import {
  AlertSchema,
  DashboardSchema,
  FarmDetailPage,
  FarmDetailSchema,
  SeriesSchema,
  WeatherSchema,
  ZoneDetailPage,
  ZoneDetailSchema,
} from './schemas'

const Empty = z.null()

export function useFarmList() {
  const { status, user } = useAuth()
  return useQuery({
    queryKey: ['farms', user?.id, 'detail'],
    queryFn: ({ signal }) => apiGet('/farms?limit=100', FarmDetailPage, { signal }),
    enabled: status === 'signed_in',
  })
}

export function useDashboard(farmId: number | null) {
  return useQuery({
    queryKey: ['dashboard', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/dashboard`, DashboardSchema, { signal }),
    enabled: farmId != null,
    refetchInterval: 30_000,
  })
}

export function useSeries(farmId: number | null, sensorType: SensorType, hours: number) {
  return useQuery({
    queryKey: ['series', farmId, sensorType, hours],
    queryFn: ({ signal }) =>
      apiGet(`/farms/${farmId}/series?sensor_type=${sensorType}&hours=${hours}`, SeriesSchema, { signal }),
    enabled: farmId != null,
    refetchInterval: 60_000,
    placeholderData: (prev) => (prev?.sensor_type === sensorType ? prev : undefined),
  })
}

export function useWeather(farmId: number | null) {
  return useQuery({
    queryKey: ['weather', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/weather`, WeatherSchema, { signal }),
    enabled: farmId != null,
    refetchInterval: 15 * 60_000,
  })
}

export function useRefreshWeather(farmId: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiGet(`/farms/${farmId}/weather?refresh=true`, WeatherSchema),
    onSuccess: (w) => qc.setQueryData(['weather', farmId], w),
  })
}

export function useAlertAction(farmId: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'acknowledge' | 'resolve' }) =>
      apiSend('POST', `/alerts/${id}/${action}`, AlertSchema),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard', farmId] }),
  })
}

export function useLogIrrigation(farmId: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { zoneId: number; liters: number; method: string; minutesAgo: number }) =>
      apiSend('POST', `/zones/${input.zoneId}/irrigation-events`, z.object({ id: z.number() }), {
        method: input.method,
        status: 'completed',
        trigger: 'manual',
        started_at: new Date(Date.now() - input.minutesAgo * 60_000).toISOString(),
        volume_liters: input.liters,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard', farmId] }),
  })
}

// --- farm & zone management -------------------------------------------------
export function useZoneList(farmId: number | null) {
  return useQuery({
    queryKey: ['zones', farmId, 'detail'],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/zones?limit=100`, ZoneDetailPage, { signal }),
    enabled: farmId != null,
  })
}

export interface FarmInput {
  name: string
  description: string | null
  latitude: number | null
  longitude: number | null
  area_hectares: number | null
  timezone: string
}

function invalidateFarm(qc: ReturnType<typeof useQueryClient>, farmId?: number | null) {
  void qc.invalidateQueries({ queryKey: ['farms'] })
  if (farmId != null) {
    void qc.invalidateQueries({ queryKey: ['zones', farmId] })
    void qc.invalidateQueries({ queryKey: ['dashboard', farmId] })
  }
}

export function useCreateFarm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: FarmInput) => apiSend('POST', '/farms', FarmDetailSchema, input),
    onSuccess: () => invalidateFarm(qc),
  })
}

export function useUpdateFarm(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: Partial<FarmInput>) => apiSend('PATCH', `/farms/${farmId}`, FarmDetailSchema, input),
    onSuccess: () => invalidateFarm(qc, farmId),
  })
}

export function useDeleteFarm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (farmId: number) => apiSend('DELETE', `/farms/${farmId}`, Empty),
    onSuccess: () => invalidateFarm(qc),
  })
}

export interface ZoneInput {
  name: string
  zone_type: string
  area_hectares: number | null
  irrigation_method: string | null
}

export function useCreateZone(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: ZoneInput) => apiSend('POST', `/farms/${farmId}/zones`, ZoneDetailSchema, input),
    onSuccess: () => invalidateFarm(qc, farmId),
  })
}

export function useDeleteZone(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (zoneId: number) => apiSend('DELETE', `/zones/${zoneId}`, Empty),
    onSuccess: () => invalidateFarm(qc, farmId),
  })
}
