import { z } from 'zod'
import { SENSOR_TYPES } from '@/features/live/schemas'

const xy = z.tuple([z.number(), z.number()])
const xyz = z.tuple([z.number(), z.number(), z.number()])

export const TwinZoneSchema = z.object({
  id: z.number(),
  name: z.string(),
  zone_type: z.string(),
  area_hectares: z.number().nullable(),
  irrigation_method: z.string().nullable(),
  polygon: z.array(xy).min(3),
  center: xy,
  size: xy,
  layout: z.enum(['auto', 'boundary']),
  crop: z
    .object({
      cycle_id: z.number(),
      crop_name: z.string(),
      variety: z.string().nullable(),
      category: z.string(),
      status: z.string(),
      planted_on: z.string().nullable(),
      expected_harvest_on: z.string().nullable(),
      growth_fraction: z.number().nullable(),
      row_spacing_m: z.number(),
      form: z.enum(['grass', 'bush', 'tree']),
      stage_key: z.string().nullable().optional(),
      stage_name: z.string().nullable().optional(),
    })
    .nullable(),
  soil_moisture: z.number().nullable(),
  temperature: z.number().nullable(),
  irrigating: z.boolean(),
  irrigation_started_at: z.string().nullable(),
  // Latest saved disease check in this zone (last 30 days), from the API.
  health: z
    .object({
      state: z.enum(['disease', 'healthy', 'uncertain']),
      detection_id: z.number(),
      label: z.string(),
      confidence: z.number(),
      severity: z.string(),
      knowledge_key: z.string().nullable(),
      detected_at: z.string(),
    })
    .nullable()
    .optional(),
})
export type TwinZone = z.infer<typeof TwinZoneSchema>

export const TwinSensorSchema = z.object({
  id: z.number(),
  name: z.string(),
  zone_id: z.number().nullable(),
  device_id: z.number().nullable(),
  sensor_type: z.enum(SENSOR_TYPES),
  unit: z.string(),
  source: z.enum(['simulated', 'hardware']),
  is_simulated: z.boolean(),
  status: z.string(),
  position: xyz,
  latest: z.object({ value: z.number(), quality: z.enum(['good', 'suspect', 'bad']), recorded_at: z.string() }).nullable(),
})
export type TwinSensor = z.infer<typeof TwinSensorSchema>

const Base = { id: z.string(), schematic: z.boolean() }
export const InfraSchema = z.discriminatedUnion('kind', [
  z.object({ ...Base, kind: z.literal('farmhouse'), position: xyz, rotation: z.number().optional() }),
  z.object({ ...Base, kind: z.literal('shed'), position: xyz, rotation: z.number().optional() }),
  z.object({ ...Base, kind: z.literal('road'), from: xy, to: xy, width: z.number() }),
  z.object({ ...Base, kind: z.literal('channel'), from: xy, to: xy, width: z.number() }),
  z.object({ ...Base, kind: z.literal('tank'), position: xyz, level_pct: z.number().nullable(), capacity_l: z.number() }),
  z.object({ ...Base, kind: z.literal('pump'), position: xyz, running: z.boolean() }),
  z.object({ ...Base, kind: z.literal('pipe'), zone_id: z.number(), path: z.array(xy).min(2), flowing: z.boolean() }),
  z.object({ ...Base, kind: z.literal('weather_station'), position: xyz }),
  z.object({ ...Base, kind: z.literal('gateway'), position: xyz }),
  z.object({ ...Base, kind: z.literal('solar'), position: xyz, optional: z.boolean().optional() }),
])
export type Infra = z.infer<typeof InfraSchema>
export type InfraOf<K extends Infra['kind']> = Extract<Infra, { kind: K }>

export const FarmTwinSchema = z.object({
  farm_id: z.number(),
  farm_name: z.string(),
  generated_at: z.string(),
  units: z.string(),
  extent: z.object({ min: xy, max: xy }),
  sun: z.object({ elevation_deg: z.number(), azimuth_deg: z.number() }).nullable(),
  weather: z
    .object({
      observed_at: z.string(),
      temperature_c: z.number().nullable(),
      wind_speed_ms: z.number().nullable(),
      wind_direction_deg: z.number().nullable(),
      cloud_cover_pct: z.number().nullable(),
      precipitation_mm: z.number().nullable(),
    })
    .nullable(),
  zones: z.array(TwinZoneSchema),
  sensors: z.array(TwinSensorSchema),
  infrastructure: z.array(InfraSchema),
})
export type FarmTwin = z.infer<typeof FarmTwinSchema>

export type Selection =
  | { kind: 'zone'; id: number }
  | { kind: 'sensor'; id: number }
  | { kind: 'infra'; id: string }
  | null

export const LAYERS = ['crops', 'sensors', 'irrigation', 'infrastructure', 'landscape', 'labels', 'moisture', 'solar'] as const
export type Layer = (typeof LAYERS)[number]
export type Layers = Record<Layer, boolean>

export const DEFAULT_LAYERS: Layers = {
  crops: true,
  sensors: true,
  irrigation: true,
  infrastructure: true,
  landscape: true,
  labels: true,
  moisture: false,
  solar: false, // optional, schematic only
}

export const LAYER_LABELS: Record<Layer, string> = {
  crops: 'Crops',
  sensors: 'Sensors',
  irrigation: 'Irrigation',
  infrastructure: 'Buildings & roads',
  landscape: 'Landscape',
  labels: 'Labels',
  moisture: 'Soil-moisture map',
  solar: 'Solar panels (optional)',
}
