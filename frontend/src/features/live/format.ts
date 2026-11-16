import { SENSOR_META, type StreamSensor } from './schemas'

export function formatValue(sensor: Pick<StreamSensor, 'sensor_type'>, value: number): string {
  const { decimals } = SENSOR_META[sensor.sensor_type]
  return value.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function relativeTime(ms: number): string {
  if (ms < 15_000) return 'just now'
  if (ms < 3_600_000) return `${Math.round(ms / 60_000) || 1} min ago`
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)} h ago`
  return `${Math.round(ms / 86_400_000)} d ago`
}
