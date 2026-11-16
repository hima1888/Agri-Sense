import { z } from 'zod'
import { SENSOR_TYPES } from '@/features/live/schemas'

const num = z.number()
const nnum = z.number().nullable()

export const AlertSchema = z.object({
  id: num,
  farm_id: num,
  zone_id: nnum,
  sensor_id: nnum,
  severity: z.enum(['info', 'warning', 'critical']),
  category: z.string(),
  status: z.enum(['open', 'acknowledged', 'resolved']),
  title: z.string(),
  message: z.string(),
  triggered_at: z.string(),
  acknowledged_at: z.string().nullable(),
  resolved_at: z.string().nullable(),
})
export type Alert = z.infer<typeof AlertSchema>

const KeyValue = z.object({ value: num, recorded_at: z.string(), unit: z.string() })

export const ZoneSummarySchema = z.object({
  id: num,
  name: z.string(),
  zone_type: z.string(),
  area_hectares: nnum,
  irrigation_method: z.string().nullable(),
  sensor_count: num,
  active_cycle: z
    .object({
      id: num,
      crop_name: z.string(),
      variety: z.string().nullable(),
      status: z.string(),
      planted_on: z.string().nullable(),
      expected_harvest_on: z.string().nullable(),
    })
    .nullable(),
  latest: z.record(z.string(), KeyValue),
})
export type ZoneSummary = z.infer<typeof ZoneSummarySchema>

export const DashboardSchema = z.object({
  farm_id: num,
  generated_at: z.string(),
  zones: z.array(ZoneSummarySchema),
  sensors: z.object({ total: num, active: num, simulated: num, hardware: num, reporting: num }),
  alerts: z.object({ open: num, by_severity: z.record(z.string(), num), recent: z.array(AlertSchema) }),
  activity: z.array(
    z.object({
      kind: z.enum(['irrigation', 'fertilizer', 'pesticide']),
      id: num,
      zone_id: num,
      at: z.string().nullable(),
      title: z.string(),
      amount: nnum,
      unit: z.string(),
      status: z.string(),
    }),
  ),
  water_7d: z.object({ liters: num, events: num }),
  readings_24h: z.object({ count: num, not_good: num }),
  stats_24h: z.array(
    z.object({ sensor_type: z.enum(SENSOR_TYPES), unit: z.string(), min: num, max: num, avg: num, count: num }),
  ),
})
export type Dashboard = z.infer<typeof DashboardSchema>

export const SeriesSchema = z.object({
  sensor_type: z.enum(SENSOR_TYPES),
  unit: z.string().nullable(),
  includes_simulated: z.boolean(),
  bucket_minutes: num,
  start: z.string(),
  end: z.string(),
  zones: z.array(
    z.object({
      zone_id: nnum,
      zone_name: z.string(),
      points: z.array(z.object({ t: z.string(), avg: num, min: num, max: num, n: num })),
    }),
  ),
})
export type Series = z.infer<typeof SeriesSchema>

const WeatherPoint = z.object({
  valid_at: z.string(),
  temperature_c: nnum,
  relative_humidity_pct: nnum,
  precipitation_mm: nnum,
  precipitation_probability_pct: nnum,
  wind_speed_ms: nnum,
  wind_direction_deg: nnum,
  cloud_cover_pct: nnum,
  shortwave_radiation_wm2: nnum,
  et0_mm: nnum,
})
export type WeatherPoint = z.infer<typeof WeatherPoint>

export const WeatherSchema = z.object({
  farm_id: num,
  source: z.string(),
  attribution: z.string(),
  timezone: z.string(),
  fetched_at: z.string().nullable(),
  stale: z.boolean(),
  error: z.string().nullable(),
  current: WeatherPoint.nullable(),
  hourly: z.array(WeatherPoint),
  daily: z.array(
    z.object({
      date: z.string(),
      temp_min_c: nnum,
      temp_max_c: nnum,
      precipitation_mm: num,
      precipitation_probability_max_pct: nnum,
      et0_mm: num,
    }),
  ),
})
export type Weather = z.infer<typeof WeatherSchema>

export const FarmDetailSchema = z.object({
  id: num,
  owner_id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  latitude: nnum,
  longitude: nnum,
  area_hectares: nnum,
  timezone: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type FarmDetail = z.infer<typeof FarmDetailSchema>
export const FarmDetailPage = z.object({ total: num, items: z.array(FarmDetailSchema) })

export const ZoneDetailSchema = z.object({
  id: num,
  farm_id: num,
  name: z.string(),
  zone_type: z.string(),
  area_hectares: nnum,
  irrigation_method: z.string().nullable(),
})
export type ZoneDetail = z.infer<typeof ZoneDetailSchema>
export const ZoneDetailPage = z.object({ total: num, items: z.array(ZoneDetailSchema) })
