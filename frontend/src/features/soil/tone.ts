import type { Tone } from '@/components/ui/primitives'

export function statusTone(status: string): Tone {
  if (['in_range', 'medium', 'normal', 'good', 'adequate', 'stable'].includes(status)) return 'ok'
  if (['severe', 'poor', 'moderately saline', 'strongly saline'].includes(status)) return 'alert'
  if (['above_field_capacity', 'high'].includes(status)) return 'info'
  return 'warn'
}
