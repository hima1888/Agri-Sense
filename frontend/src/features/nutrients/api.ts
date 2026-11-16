import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { apiGet, apiSend } from '@/lib/api-client'

const num = z.number()
const nnum = z.number().nullable()
const NPK = z.object({ n: num, p2o5: num, k2o: num })

export const PlanSchema = z.object({
  zone_id: num,
  zone_name: z.string(),
  status: z.enum(['plan', 'complete', 'no_target', 'no_crop']),
  crop: z.string().nullable(),
  cycle_id: nnum,
  message: z.string().optional(),
  area_hectares: nnum.optional(),
  target_is_custom: z.boolean().optional(),
  applications_counted: num.optional(),
  lab_test_age_days: nnum.optional(),
  uses_simulated_data: z.boolean().optional(),
  target_kg_ha: NPK.optional(),
  target_source: z.string().nullable().optional(),
  adjusted_kg_ha: NPK.optional(),
  applied_kg_ha: NPK.optional(),
  remaining_kg_ha: NPK.optional(),
  factors: z
    .array(
      z.object({
        nutrient: z.string(),
        recommended_kg_ha: num,
        soil_rating: z.string().nullable(),
        soil_source: z.string(),
        factor: num,
        adjusted_kg_ha: num,
        applied_kg_ha: num,
        remaining_kg_ha: num,
        surplus_kg_ha: num,
        note: z.string().nullable(),
      }),
    )
    .optional(),
  products: z.array(z.object({ product: z.string(), grade: z.string(), kg_per_ha: num, supplies: z.string(), kg_for_zone: num.optional(), bags_50kg: num.optional() })).optional(),
  surplus_kg_ha: z.record(z.string(), num).optional(),
  soil_test_saving_kg_ha: z.record(z.string(), num).optional(),
  notes: z.array(z.string()).optional(),
  confidence: num.optional(),
  limitations: z.array(z.string()).optional(),
})
export type NutrientPlan = z.infer<typeof PlanSchema>

const Phi = z.object({ id: num, product: z.string(), status: z.string(), detail: z.string().optional(), safe_to_harvest_from: z.string().optional() })
const Summary = z.object({
  applications: num,
  by_type: z.record(z.string(), num),
  quantity_by_unit: z.record(z.string(), num),
  quantity_per_ha_by_unit: z.record(z.string(), num).nullable(),
  with_evidence: num,
  evidence_share: nnum,
  phi: z.array(Phi),
  phi_conflicts: num,
  harvest_blocked_until: z.string().nullable(),
})
export const UseSchema = z.object({
  status: z.string(),
  message: z.string().optional(),
  crop: z.string().optional(),
  current: Summary.optional(),
  previous: Summary.nullable().optional(),
  comparison: z
    .object({
      applications_per_ha: z.object({ current: num, previous: num }),
      change_pct: nnum,
      by_unit_per_ha: z.record(z.string(), z.object({ current: num, previous: num, change_pct: nnum })),
    })
    .nullable()
    .optional(),
  recent: z.array(z.object({ id: num, product_name: z.string(), pesticide_type: z.string(), applied_at: z.string(), quantity: z.union([num, z.string()]), quantity_unit: z.string(), disease_detection_id: nnum })).optional(),
  basis: z.string().optional(),
})
export type ChemicalUse = z.infer<typeof UseSchema>

export const CheckSchema = z.object({
  verdict: z.enum(['ok_to_proceed', 'hold']),
  checks: z.array(z.object({ check: z.string(), status: z.enum(['ok', 'warning', 'unknown']), detail: z.string() })),
  warnings: num,
  evidence: z.array(z.object({ id: num, label: z.string(), detected_at: z.string(), outcome: z.string() })),
  limitations: z.array(z.string()),
})
export type SprayCheck = z.infer<typeof CheckSchema>

export function useNutrientPlan(zoneId: number | null) {
  return useQuery({ queryKey: ['nutrient-plan', zoneId], queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/nutrients/plan`, PlanSchema, { signal }), enabled: zoneId != null })
}

export function useChemicalUse(zoneId: number | null) {
  return useQuery({ queryKey: ['chem-use', zoneId], queryFn: ({ signal }) => apiGet(`/zones/${zoneId}/chemicals/use`, UseSchema, { signal }), enabled: zoneId != null })
}

export function useSprayCheck(zoneId: number) {
  return useMutation({
    mutationFn: ({ type, phi }: { type: string; phi: number | null }) =>
      apiGet(`/zones/${zoneId}/chemicals/spray-check?pesticide_type=${type}${phi != null ? `&phi_days=${phi}` : ''}`, CheckSchema),
  })
}

export function useSetTarget(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ cycleId, body }: { cycleId: number; body: { n: number; p2o5: number; k2o: number; source: string } }) =>
      apiSend('PUT', `/crop-cycles/${cycleId}/nutrient-target`, z.object({ cycle_id: num }), body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['nutrient-plan', zoneId] }),
  })
}

export function useLogFertilizer(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => apiSend('POST', `/zones/${zoneId}/fertilizer-applications`, z.object({ id: num }), body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['nutrient-plan', zoneId] }),
  })
}

export function useLogPesticide(zoneId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => apiSend('POST', `/zones/${zoneId}/pesticide-applications`, z.object({ id: num }), body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['chem-use', zoneId] }),
  })
}
