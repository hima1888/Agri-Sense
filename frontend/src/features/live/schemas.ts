import { z } from 'zod'

export const SENSOR_TYPES = [
  'temperature',
  'humidity',
  'soil_moisture',
  'soil_temperature',
  'soil_ph',
  'nitrogen',
  'phosphorus',
  'potassium',
  'light',
  'rainfall',
  'leaf_wetness',
  'water_level',
] as const
export type SensorType = (typeof SENSOR_TYPES)[number]

const Quality = z.enum(['good', 'suspect', 'bad'])

export const LatestSchema = z.object({ recorded_at: z.string(), value: z.number(), quality: Quality })

export const StreamSensorSchema = z.object({
  id: z.number(),
  name: z.string(),
  zone_id: z.number().nullable(),
  sensor_type: z.enum(SENSOR_TYPES),
  unit: z.string(),
  source: z.enum(['simulated', 'hardware']),
  is_simulated: z.boolean(),
  status: z.string(),
  min_valid: z.number().nullable(),
  max_valid: z.number().nullable(),
  latest: LatestSchema.nullable(),
})
export type StreamSensor = z.infer<typeof StreamSensorSchema>

export const SnapshotSchema = z.object({ farm_id: z.number(), sensors: z.array(StreamSensorSchema) })
export type Snapshot = z.infer<typeof SnapshotSchema>

export const ReadingsEventSchema = z.object({
  farm_id: z.number(),
  readings: z.array(
    z.object({
      sensor_id: z.number(),
      recorded_at: z.string(),
      value: z.number(),
      quality: Quality,
      is_simulated: z.boolean(),
    }),
  ),
})

export const SeriesSchema = z.object({
  sensor_id: z.number(),
  readings: z.array(z.object({ recorded_at: z.string(), value: z.number(), quality: Quality })),
})

export const FarmSchema = z.object({
  id: z.number(),
  name: z.string(),
  latitude: z.number().nullable(),
  longitude: z.number().nullable(),
  timezone: z.string(),
})
export type Farm = z.infer<typeof FarmSchema>
export const FarmPageSchema = z.object({ total: z.number(), items: z.array(FarmSchema) })

export const ZoneSchema = z.object({ id: z.number(), farm_id: z.number(), name: z.string(), zone_type: z.string() })
export type Zone = z.infer<typeof ZoneSchema>
export const ZonePageSchema = z.object({ total: z.number(), items: z.array(ZoneSchema) })

export const SimulatorStatusSchema = z.object({
  enabled: z.boolean(),
  running: z.boolean(),
  interval_seconds: z.number().nullable(),
  last_tick_at: z.string().nullable(),
  last_error: z.string().nullable(),
  simulated_sensors: z.number(),
  live_connections: z.number(),
  note: z.string(),
})

export const BackfillResultSchema = z.object({ inserted: z.number(), sensors: z.number() })
export const ProvisionResultSchema = z.object({ sensors: z.array(z.object({ id: z.number() })) })

/** Display metadata per sensor type: label, decimals, and a natural colour token. */
export const SENSOR_META: Record<SensorType, { label: string; decimals: number; group: 'air' | 'soil' | 'water' }> = {
  temperature: { label: 'Air temperature', decimals: 1, group: 'air' },
  humidity: { label: 'Humidity', decimals: 0, group: 'air' },
  light: { label: 'Light', decimals: 0, group: 'air' },
  rainfall: { label: 'Rainfall', decimals: 1, group: 'water' },
  leaf_wetness: { label: 'Leaf wetness', decimals: 0, group: 'air' },
  soil_moisture: { label: 'Soil moisture', decimals: 1, group: 'soil' },
  soil_temperature: { label: 'Soil temperature', decimals: 1, group: 'soil' },
  soil_ph: { label: 'Soil pH', decimals: 2, group: 'soil' },
  nitrogen: { label: 'Nitrogen (N)', decimals: 0, group: 'soil' },
  phosphorus: { label: 'Phosphorus (P)', decimals: 0, group: 'soil' },
  potassium: { label: 'Potassium (K)', decimals: 0, group: 'soil' },
  water_level: { label: 'Tank level', decimals: 0, group: 'water' },
}

export const AlertEventSchema = z.object({
  type: z.enum(['raised', 'escalated', 'resolved']),
  alert: z.object({
    id: z.number(),
    severity: z.string(),
    category: z.string(),
    status: z.string(),
    title: z.string(),
    message: z.string(),
    zone_id: z.number().nullable(),
  }),
})
