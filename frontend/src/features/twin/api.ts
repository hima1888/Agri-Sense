import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/lib/api-client'
import { FarmTwinSchema } from './schemas'

/** Scene description from the API. Live sensor values are overlaid from the SSE stream. */
export function useTwin(farmId: number | null) {
  return useQuery({
    queryKey: ['twin', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/twin`, FarmTwinSchema, { signal }),
    enabled: farmId != null,
    refetchInterval: 60_000, // crop stage, irrigation state, weather and sun move slowly
  })
}
