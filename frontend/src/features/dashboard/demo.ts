import { useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiSend } from '@/lib/api-client'

const Created = z.object({ id: z.number() }).passthrough()
const Any = z.unknown()

/**
 * One click to a working farm: a real location (live Open-Meteo weather), one zone per main crop, a full set of
 * simulated sensors per zone and 24 h of simulated history. Every sensor is labelled simulated.
 */
const DEMO_ZONES = ['Tomato field', 'Potato field', 'Corn field', 'Rice field']

export function useDemoFarm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const farm = await apiSend('POST', '/farms', Created, {
        name: 'Demo farm',
        description: 'Created with one click. Sensors are simulated; weather is real.',
        latitude: 17.385,
        longitude: 78.4867,
        area_hectares: 2,
        timezone: 'Asia/Kolkata',
      })
      for (const name of DEMO_ZONES) {
        const zone = await apiSend('POST', `/farms/${farm.id}/zones`, Created, { name, zone_type: 'field', area_hectares: 1 })
        await apiSend('POST', `/zones/${zone.id}/simulator/provision`, Any, {})
      }
      await apiSend('POST', `/farms/${farm.id}/simulator/backfill`, Any, { hours: 24, step_minutes: 10 })
      return farm.id
    },
    onSuccess: () => qc.invalidateQueries(),
  })
}

/** "Corn" -> "Corn field": the zone name used for a crop's own zone. */
export const cropZoneName = (crop: string) => `${crop.charAt(0).toUpperCase()}${crop.slice(1)} field`

/** Create a zone for one crop, with a full set of simulated sensors so it reports live like the others. */
export function useCreateCropZone(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (crop: string) => {
      const zone = await apiSend('POST', `/farms/${farmId}/zones`, Created, { name: cropZoneName(crop), zone_type: 'field' })
      await apiSend('POST', `/zones/${zone.id}/simulator/provision`, Any, {})
      return zone.id
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['zones', farmId] }),
  })
}
