import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet, apiSend } from '@/lib/api-client'
import { useAuthedImage } from '@/lib/use-authed-image'

const num = z.number()

export const RecognitionSchema = z.object({
  outcome: z.enum(['recognized', 'uncertain', 'unsupported']),
  label: z.string().nullable(),
  subject_type: z.string().nullable(),
  confidence: num,
  produce_probability: num,
  candidates: z.array(z.object({ label: z.string(), subject_type: z.string(), confidence: num })),
  model_sees: z.array(z.object({ label: z.string(), confidence: num })),
  quality: z.array(z.object({ key: z.string(), value: z.union([num, z.string()]), status: z.string(), note: z.string() })),
  explanation: z.object({ method: z.string(), grid: z.array(z.array(num)).nullable(), crop: z.string() }),
  limitations: z.array(z.string()),
  image_size: z.array(num),
  detection_id: num.nullable(),
  saved: z.boolean(),
  model: z.object({ id: num, name: z.string(), version: z.string() }),
})
export type Recognition = z.infer<typeof RecognitionSchema>

const DetectionSchema = z.object({
  id: num,
  zone_id: num.nullable(),
  subject_type: z.string(),
  predicted_label: z.string(),
  confidence: num,
  detected_at: z.string(),
  explanation: z.record(z.string(), z.unknown()).nullable(),
})
export type Detection = z.infer<typeof DetectionSchema>
const DetectionPage = z.object({ total: num, items: z.array(DetectionSchema) })

const ModelInfoSchema = z.object({
  name: z.string(),
  version: z.string(),
  available: z.boolean(),
  source: z.string(),
  training_dataset: z.string(),
  metrics: z.record(z.string(), z.union([num, z.string()])),
  supported: z.array(z.object({ label: z.string(), subject_type: z.string() })),
  min_confidence: num,
})
export type ModelInfo = z.infer<typeof ModelInfoSchema>

export function useModelInfo() {
  return useQuery({ queryKey: ['vision-model'], queryFn: ({ signal }) => apiGet('/vision/model', ModelInfoSchema, { signal }) })
}

export function useDetections(farmId: number | null) {
  return useQuery({
    queryKey: ['detections', farmId],
    queryFn: ({ signal }) => apiGet(`/farms/${farmId}/vision/recognitions?limit=24`, DetectionPage, { signal }),
    enabled: farmId != null,
  })
}

export function useRecognize(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, zoneId }: { file: File; zoneId: number | null }) => {
      const form = new FormData()
      form.append('file', file)
      if (zoneId != null) form.append('zone_id', String(zoneId))
      return apiSend('POST', `/farms/${farmId}/vision/recognitions`, RecognitionSchema, form)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['detections', farmId] }),
  })
}

export function useDeleteDetection(farmId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiSend('DELETE', `/vision/recognitions/${id}`, z.null()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['detections', farmId] }),
  })
}

/** Authenticated stored image as an object URL. */
export function useDetectionImage(id: number): string | null {
  return useAuthedImage(`/vision/recognitions/${id}/image`)
}
