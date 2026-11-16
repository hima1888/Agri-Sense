import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { useAuth } from '@/features/auth/auth-context'
import { apiGet, apiSend } from '@/lib/api-client'

export const MeSchema = z.object({
  id: z.uuid(),
  email: z.string(),
  full_name: z.string().nullable(),
  role: z.enum(['farmer', 'agronomist', 'admin']),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Me = z.infer<typeof MeSchema>

const FarmsPageSchema = z.object({
  total: z.number(),
  items: z.array(z.object({ id: z.number(), name: z.string(), area_hectares: z.number().nullable() })),
})

export function useMe() {
  const { status, user } = useAuth()
  return useQuery({
    queryKey: ['me', user?.id],
    queryFn: ({ signal }) => apiGet('/me', MeSchema, { signal }),
    enabled: status === 'signed_in',
  })
}

export function useMyFarms() {
  const { status, user } = useAuth()
  return useQuery({
    queryKey: ['farms', user?.id],
    queryFn: ({ signal }) => apiGet('/farms?limit=50', FarmsPageSchema, { signal }),
    enabled: status === 'signed_in',
  })
}

export function useUpdateMe() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  return useMutation({
    mutationFn: (body: { full_name: string | null }) => apiSend('PATCH', '/me', MeSchema, body),
    onSuccess: (me) => queryClient.setQueryData(['me', user?.id], me),
  })
}
