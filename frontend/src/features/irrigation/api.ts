import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet, apiSend } from '@/lib/api-client'

const num = z.number()
const nnum = z.number().nullable()

const Event = z.object({
  date: z.string(),
  day_index: num,
  net_mm: num,
  gross_mm: num,
  volume_liters: nnum,
  depletion_before_mm: num,
  urgent: z.boolean(),
  reason: z.string(),
  window: z.object({ start_local_hour: num, wind_speed_ms: nnum.optional(), basis: z.string() }),
  scheduled_for: z.string(),
  already_scheduled: z.boolean(),
})
export type PlanEvent = z.infer<typeof Event>

const Day = z.object({
  date: z.string(),
  et0_mm: num,
  etc_mm: num,
  rain_mm: num,
  effective_rain_mm: num,
  depletion_start_mm: num,
  irrigation_net_mm: nnum,
  depletion_end_mm: num,
  note: z.string().nullable(),
})
export type PlanDay = z.infer<typeof Day>

export const ZonePlanSchema = z.object({
  zone_id: num,
  zone_name: z.string(),
  crop: z.string().nullable(),
  irrigation_method: z.string().nullable(),
  area_hectares: nnum,
  status: z.enum(['irrigate_today', 'planned', 'no_irrigation_needed', 'no_moisture_data']),
  method: z.string(),
  uses_simulated_data: z.boolean(),
  limitations: z.array(z.string()),
  confidence: num,
  message: z.string().optional(),
  scheduled: z.array(z.object({ id: num, scheduled_for: z.string(), local_date: z.string(), volume_liters: nnum, trigger: z.string() })),
  water: z
    .object({
      moisture_pct: num,
      field_capacity_pct: num,
      wilting_point_pct: num,
      taw_mm: num,
      raw_mm: num,
      depletion_mm: num,
      status: z.string(),
      kc: num,
      root_depth_m: num,
      measured_at: z.string().nullable(),
      irrigation_since_mm: num,
      sources: z.record(z.string(), z.string()),
    })
    .nullable(),
  plan: z
    .object({
      events: z.array(Event),
      days: z.array(Day),
      total_net_mm: num,
      total_gross_mm: num,
      total_volume_liters: nnum,
      application_efficiency: num,
      deferred_by_rain_mm: num,
    })
    .nullable(),
  rain_aware_saving: z.object({ gross_mm: num, volume_liters: nnum, basis: z.string() }).optional(),
})
export type ZonePlan = z.infer<typeof ZonePlanSchema>

const WaterUseSchema = z.object({
  days: num,
  events: num,
  events_without_volume: num,
  applied_liters: num,
  applied_gross_mm: nnum,
  applied_net_mm: nnum,
  estimated_need_mm: num,
  weather_days_covered: num,
  applied_to_need_ratio: nnum,
  basis: z.string(),
})
export type WaterUse = z.infer<typeof WaterUseSchema>

export function useZonePlan(zoneId: number | null) {
  return useQuery({
    queryKey: ['irrigation-plan', zoneId],
    queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/irrigation/plan`, ZonePlanSchema, { signal }),
    enabled: zoneId != null,
  })
}

export function useWaterUse(zoneId: number | null, days: number) {
  return useQuery({
    queryKey: ['water-use', zoneId, days],
    queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/irrigation/water-use?days=${days}`, WaterUseSchema, { signal }),
    enabled: zoneId != null,
  })
}

export function useSchedule(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (date: string) => apiSend('POST', `/zones/${zoneId}/irrigation/schedule`, z.object({ id: num }), { date }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['irrigation-plan', zoneId] }),
  })
}

export function useCompleteEvent(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, volume }: { id: number; volume: number | null }) =>
      apiSend('PATCH', `/irrigation-events/${id}`, z.object({ id: num }), {
        status: 'completed',
        started_at: new Date().toISOString(),
        ...(volume != null ? { volume_liters: volume } : {}),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['irrigation-plan', zoneId] })
      void qc.invalidateQueries({ queryKey: ['water-use', zoneId] })
    },
  })
}
