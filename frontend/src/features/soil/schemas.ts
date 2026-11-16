import { z } from 'zod'

const num = z.number()
const nnum = z.number().nullable()

export const SOIL_TEXTURES = [
  'sand', 'loamy_sand', 'sandy_loam', 'loam', 'silt_loam', 'silt', 'sandy_clay_loam',
  'clay_loam', 'silty_clay_loam', 'sandy_clay', 'silty_clay', 'clay',
] as const
export const MEASUREMENT_SOURCES = ['lab', 'field_kit', 'manual'] as const

export const ComponentSchema = z.object({
  value: num,
  unit: z.string(),
  value_mg_kg: nnum.optional(),
  status: z.string(),
  target: z.array(num),
  target_source: z.string(),
  source: z.string(),
  confidence: num,
  score: num,
})
export type SoilComponent = z.infer<typeof ComponentSchema>

export const WaterSchema = z.object({
  field_capacity_pct: num,
  wilting_point_pct: num,
  moisture_pct: num,
  root_depth_m: num,
  depletion_fraction_p: num,
  kc: num,
  taw_mm: num,
  raw_mm: num,
  depletion_mm: num,
  available_fraction: nnum,
  status: z.enum(['above_field_capacity', 'adequate', 'stress', 'severe']),
  days_to_stress: nnum,
  forecast_days: num,
  projection: z.array(
    z.object({ date: z.string(), et0_mm: num, etc_mm: num, effective_rain_mm: num, depletion_mm: num }),
  ),
  sources: z.record(z.string(), z.string()),
  confidence: num,
})
export type WaterBalance = z.infer<typeof WaterSchema>

export const AssessmentSchema = z.object({
  zone_id: num,
  zone_name: z.string(),
  assessed_at: z.string(),
  method: z.string(),
  crop: z
    .object({ name: z.string(), category: z.string(), growth_fraction: nnum, status: z.string().nullable() })
    .nullable(),
  index: nnum,
  rating: z.enum(['good', 'fair', 'poor']).nullable(),
  confidence: num,
  confidence_reasons: z.array(z.string()),
  components: z.record(z.string(), ComponentSchema),
  not_assessed: z.array(z.string()),
  factors: z.array(
    z.object({ key: z.string(), label: z.string(), status: z.string(), score: num, weight: num, impact: num }),
  ),
  water: WaterSchema.nullable(),
  trends: z.record(z.string(), num),
  guidance: z.array(z.object({ level: z.enum(['info', 'warning']), text: z.string() })),
  limitations: z.array(z.string()),
  uses_simulated_data: z.boolean(),
})
export type SoilAssessment = z.infer<typeof AssessmentSchema>

export const SavedSchema = z.object({
  id: num,
  zone_id: nnum,
  created_at: z.string(),
  confidence: num,
  predicted_value: z.record(z.string(), z.unknown()),
  factors: z.array(z.record(z.string(), z.unknown())),
  limitations: z.string(),
})
export const SavedPage = z.object({ total: num, items: z.array(SavedSchema) })
export type SavedAssessment = z.infer<typeof SavedSchema>

export const LABELS: Record<string, string> = {
  ph: 'pH',
  nitrogen: 'Nitrogen (N)',
  phosphorus: 'Phosphorus (P)',
  potassium: 'Potassium (K)',
  organic_carbon: 'Organic carbon',
  salinity: 'Salinity (EC)',
  water: 'Root-zone water',
}
