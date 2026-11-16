import { useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet } from '@/lib/api-client'

export const HealthSchema = z.object({
  status: z.literal('ok'),
  service: z.string(),
  version: z.string(),
  timestamp: z.string(),
})
export type Health = z.infer<typeof HealthSchema>

const ServiceState = z.enum(['ok', 'degraded', 'not_configured', 'planned'])

export const SystemInfoSchema = z.object({
  name: z.string(),
  version: z.string(),
  environment: z.string(),
  api_prefix: z.string(),
  data_mode: z.object({
    sensors: z.enum(['none', 'simulated', 'hardware', 'mixed']),
    note: z.string(),
  }),
  services: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      state: ServiceState,
      detail: z.string(),
    }),
  ),
})
export type SystemInfo = z.infer<typeof SystemInfoSchema>
export type ServiceStateValue = z.infer<typeof ServiceState>

export function useHealth() {
  return useQuery({
    queryKey: ['system', 'health'],
    queryFn: ({ signal }) => apiGet('/health', HealthSchema, { signal }),
    refetchInterval: 15_000,
    retry: 1,
  })
}

export function useSystemInfo() {
  return useQuery({
    queryKey: ['system', 'info'],
    queryFn: ({ signal }) => apiGet('/system/info', SystemInfoSchema, { signal }),
    retry: 1,
  })
}
