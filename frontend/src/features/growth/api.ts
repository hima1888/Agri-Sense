import { useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet } from '@/lib/api-client'

const num = z.number()

export const STAGE_KEYS = ['seed', 'germination', 'seedling', 'vegetative', 'flowering', 'formation', 'maturity', 'harvest'] as const
export type StageKey = (typeof STAGE_KEYS)[number]

const StageSchema = z.object({
  key: z.enum(STAGE_KEYS),
  name: z.string(),
  start_day: num,
  end_day: num,
  fao_stage: z.string(),
  approximate_boundary: z.boolean(),
  description: z.string(),
})
export type GrowthStage = z.infer<typeof StageSchema>

export const GrowthSchema = z.object({
  crop: z.string(),
  crop_key: z.string(),
  crop_id: num,
  cycle_id: num.nullable().optional(),
  planted_on: z.string().nullable().optional(),
  cycle_days: num,
  cycle_days_source: z.string(),
  fao56: z.object({ initial: num, development: num, mid_season: num, late_season: num, region: z.string() }),
  stages: z.array(StageSchema).length(8),
  current: z.object({ day: num, stage_key: z.enum(STAGE_KEYS).nullable(), progress: num, note: z.string().nullable() }).nullable().optional(),
  method: z.string(),
  limitations: z.array(z.string()),
})
export type CropGrowth = z.infer<typeof GrowthSchema>

const CropList = z.array(z.object({ id: num, common_name: z.string(), category: z.string(), typical_cycle_days: num.nullable() }))

export function useCrops() {
  // Only crops with growth-stage data: the API leaves out perennials such as banana and mango.
  return useQuery({ queryKey: ['growth-crops'], queryFn: ({ signal }) => apiGet('/growth/crops', CropList, { signal }), staleTime: 5 * 60_000 })
}

/** Stages for a zone's crop cycle (with today's position) or, without a cycle, for the crop itself. */
export function useGrowth(target: { cycleId: number } | { cropId: number } | null) {
  const path = !target ? null : 'cycleId' in target ? `/crop-cycles/${target.cycleId}/growth` : `/crops/${target.cropId}/growth`
  return useQuery({
    queryKey: ['growth', path],
    queryFn: ({ signal }) => apiGet(path!, GrowthSchema, { signal }),
    enabled: path != null,
    retry: false,
  })
}

/** Which illustration fits the crop (cereal ear, fruit, underground organ or generic). */
export function plantForm(cropKey: string, category: string | undefined): 'cereal' | 'fruit' | 'tuber' | 'other' {
  if (['maize', 'rice', 'wheat'].includes(cropKey) || category === 'cereal') return 'cereal'
  if (cropKey === 'potato' || cropKey === 'onion' || cropKey === 'groundnut') return 'tuber'
  if (['tomato', 'chilli pepper', 'cotton', 'soybean'].includes(cropKey)) return 'fruit'
  return 'other'
}
