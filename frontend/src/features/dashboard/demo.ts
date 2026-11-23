import { useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiSend } from '@/lib/api-client'

const Created = z.object({ id: z.number() }).passthrough()
const Any = z.unknown()

/**
 * One click to a working farm: a real location (live Open-Meteo weather), two zones, a full set of
 * simulated sensors per zone and 24 h of simulated history. Every sensor is labelled simulated.
 */
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
      for (const name of ['North field', 'South field']) {
        const zone = await apiSend('POST', `/farms/${farm.id}/zones`, Created, { name, zone_type: 'field', area_hectares: 1 })
        await apiSend('POST', `/zones/${zone.id}/simulator/provision`, Any, {})
      }
      await apiSend('POST', `/farms/${farm.id}/simulator/backfill`, Any, { hours: 24, step_minutes: 10 })
      return farm.id
    },
    onSuccess: () => qc.invalidateQueries(),
  })
}
