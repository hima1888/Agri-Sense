import type { StreamSensor } from '@/features/live/schemas'
import type { TwinSensor, TwinZone } from './schemas'

/** Overlay live stream values (newer only) onto the API's sensor list. */
export function mergeLiveSensors(apiSensors: TwinSensor[], live: StreamSensor[]): TwinSensor[] {
  if (!live.length) return apiSensors
  const byId = new Map(live.map((s) => [s.id, s]))
  return apiSensors.map((s) => {
    const l = byId.get(s.id)?.latest
    if (!l) return s
    if (s.latest && Date.parse(s.latest.recorded_at) >= Date.parse(l.recorded_at)) return s
    return { ...s, latest: { value: l.value, quality: l.quality, recorded_at: l.recorded_at } }
  })
}

/** Recompute each zone's moisture/temperature from the (live) sensors, good readings only. */
export function mergeLiveZones(zones: TwinZone[], sensors: TwinSensor[]): TwinZone[] {
  const avg = (zoneId: number, type: string) => {
    const vals = sensors.filter((s) => s.zone_id === zoneId && s.sensor_type === type && s.latest?.quality === 'good').map((s) => s.latest!.value)
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  }
  return zones.map((z) => ({
    ...z,
    soil_moisture: avg(z.id, 'soil_moisture') ?? z.soil_moisture,
    temperature: avg(z.id, 'temperature') ?? z.temperature,
  }))
}
