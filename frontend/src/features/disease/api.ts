import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet, apiSend } from '@/lib/api-client'

const num = z.number()

export const OUTCOMES = ['possible_disease', 'possible_healthy', 'uncertain', 'cannot_identify', 'not_a_leaf', 'unsupported_crop'] as const

export const KnowledgeSchema = z.object({
  key: z.string(),
  name: z.string(),
  pathogen: z.string(),
  pathogen_type: z.string(),
  crops: z.array(z.string()),
  what: z.string(),
  symptoms: z.array(z.string()),
  causes: z.string(),
  conditions: z.string(),
  spread: z.string(),
  management: z.array(z.string()),
  prevention: z.array(z.string()),
  sustainable: z.array(z.string()),
  monitor: z.array(z.string()),
  seek_advice: z.string(),
  source: z.string(),
  reviewed: z.boolean(),
})
export type Knowledge = z.infer<typeof KnowledgeSchema>

const HealthySchema = z.object({
  what: z.string(),
  monitor: z.array(z.string()),
  prevention: z.array(z.string()),
  seek_advice: z.string(),
  source: z.string(),
  reviewed: z.boolean(),
})
export type HealthyGuidance = z.infer<typeof HealthySchema>

export const ScreeningSchema = z.object({
  outcome: z.enum(OUTCOMES),
  part: z.enum(['leaf', 'fruit']).default('leaf'),
  crop: z.string().nullable(),
  crop_source: z.string().nullable(),
  model: z.object({ key: z.string(), name: z.string(), version: z.string(), id: num.nullable().optional() }).nullable(),
  label: z.string().nullable(),
  disease: z.string().nullable(),
  is_healthy: z.boolean().nullable(),
  confidence: num.nullable(),
  margin: num.nullable(),
  candidates: z.array(z.object({ label: z.string(), crop: z.string().nullable(), disease: z.string().nullable(), is_healthy: z.boolean(), confidence: num })),
  checks: z.array(z.object({ rule: z.string(), passed: z.boolean(), detail: z.string() })),
  quality: z.array(z.object({ key: z.string(), value: z.union([num, z.string()]), status: z.string(), note: z.string() })),
  affected_area_pct: num.nullable(),
  severity: z.string().nullable(),
  reason: z.string(),
  limitations: z.array(z.string()),
  image_size: z.array(num),
  detection_id: num.nullable(),
  saved: z.boolean(),
  knowledge_key: z.string().nullable().optional(),
  knowledge: KnowledgeSchema.nullable().optional(),
  healthy_guidance: HealthySchema.nullable().optional(),
})
export type Screening = z.infer<typeof ScreeningSchema>

const RecordSchema = z.object({
  id: num,
  zone_id: num.nullable(),
  disease_label: z.string(),
  is_healthy: z.boolean(),
  confidence: num,
  severity: z.string(),
  affected_area_pct: num.nullable(),
  detected_at: z.string(),
  explanation: z.record(z.string(), z.unknown()).nullable(),
  knowledge_key: z.string().nullable().optional(),
})
export type DiseaseRecord = z.infer<typeof RecordSchema>
const RecordPage = z.object({ total: num, items: z.array(RecordSchema) })

const ModelsSchema = z.object({
  models: z.array(
    z.object({
      key: z.string(),
      name: z.string(),
      available: z.boolean(),
      architecture: z.string(),
      used_for: z.array(z.string()),
      part: z.enum(['leaf', 'fruit']).default('leaf'),
      published_accuracy: z.string(),
      licence: z.string(),
      source: z.string(),
      limitations: z.array(z.string()),
    }),
  ),
  supported_crops: z.record(z.string(), z.string()),
  supported_fruits: z.record(z.string(), z.string()).default({}),
  thresholds: z.object({ min_top1: num, min_margin: num }),
  limitations: z.array(z.string()),
})
export type DiseaseModels = z.infer<typeof ModelsSchema>

export function useDiseaseModels() {
  return useQuery({ queryKey: ['disease-models'], queryFn: ({ signal }) => apiGet('/vision/disease/models', ModelsSchema, { signal }) })
}

/** Structured guidance for one disease, from the backend knowledge layer. */
export function useDiseaseKnowledge(key: string | null | undefined) {
  return useQuery({
    queryKey: ['disease-knowledge', key],
    queryFn: ({ signal }) => apiGet(`/knowledge/diseases/${key}`, KnowledgeSchema, { signal }),
    enabled: !!key,
    staleTime: Infinity,
  })
}

export function useDiseaseChecks(farmId: number | null) {
  return useQuery({
    queryKey: ['disease-checks', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/vision/disease-checks?limit=24`, RecordPage, { signal }),
    enabled: farmId != null,
  })
}

export type Part = 'leaf' | 'fruit'

export function useScreenLeaf(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, crop, zoneId, part = 'leaf' }: { file: File; crop: string | null; zoneId: number | null; part?: Part }) => {
      const form = new FormData()
      form.append('file', file)
      form.append('part', part)
      if (crop) form.append('crop', crop)
      if (zoneId != null) form.append('zone_id', String(zoneId))
      return apiSend('POST', `/farms/${farmId}/vision/disease-checks`, ScreeningSchema, form)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['disease-checks', farmId] }),
  })
}

export function useDeleteDiseaseCheck(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiSend('DELETE', `/vision/disease-checks/${id}`, z.null()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['disease-checks', farmId] }),
  })
}
