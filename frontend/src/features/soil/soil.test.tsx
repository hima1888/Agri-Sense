import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase } from '@/test/fake-supabase'
import { jsonResponse, renderRoute } from '@/test/render'
import { statusTone } from './tone'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof createFakeSupabase> | null }))
vi.mock('@/lib/supabase', async () => {
  const { createFakeSupabase } = await import('@/test/fake-supabase')
  fake.current = createFakeSupabase()
  return { supabase: fake.current.supabase }
})

const NOW = new Date().toISOString()
const FARM = { id: 7, owner_id: 'u', name: 'Kaveri Farm', description: null, latitude: 17.4, longitude: 78.5, area_hectares: 12, timezone: 'Asia/Kolkata', created_at: NOW, updated_at: NOW }
const ZONE = { id: 1, farm_id: 7, name: 'North Field', zone_type: 'field', area_hectares: 4, irrigation_method: 'drip' }
const comp = (value: number, unit: string, status: string, source: string, extra = {}) => ({
  value, unit, status, target: [280, 560], target_source: 'Soil Health Card', source, confidence: 0.9, score: 50, ...extra,
})
const ASSESSMENT = {
  zone_id: 1, zone_name: 'North Field', assessed_at: NOW, method: 'Rule-based scoring against published references (FAO-56, Soil Health Card).',
  crop: { name: 'Tomato', category: 'vegetable', growth_fraction: 0.45, status: 'growing' },
  index: 58.4, rating: 'fair', confidence: 0.42, confidence_reasons: ['uses simulated sensor data'],
  components: {
    nitrogen: comp(224, 'kg/ha', 'low', 'NPK probe 24 h mean (simulated)', { value_mg_kg: 100 }),
    ph: { ...comp(5.4, 'pH', 'acidic', 'lab test 2026-10-25'), target: [6, 6.8], target_source: 'Tomato optimum' },
  },
  not_assessed: ['organic_carbon'],
  factors: [{ key: 'ph', label: 'pH', status: 'acidic', score: 30, weight: 0.2, impact: 14 }],
  water: {
    field_capacity_pct: 25, wilting_point_pct: 12, moisture_pct: 20, root_depth_m: 0.7, depletion_fraction_p: 0.4, kc: 1.15,
    taw_mm: 91, raw_mm: 36.4, depletion_mm: 35, available_fraction: 0.615, status: 'adequate', days_to_stress: 1, forecast_days: 2,
    projection: [
      { date: '2026-11-15', et0_mm: 5, etc_mm: 5.75, effective_rain_mm: 0, depletion_mm: 40.8 },
      { date: '2026-11-16', et0_mm: 5, etc_mm: 5.75, effective_rain_mm: 0, depletion_mm: 46.5 },
    ],
    sources: { moisture: 'soil-moisture sensors (latest) (simulated)' }, confidence: 0.4,
  },
  trends: { soil_moisture: -0.8 },
  guidance: [{ level: 'warning', text: 'pH 5.4 is below the Tomato optimum (6–6.8).' }],
  limitations: ['This is rule-based scoring, not a trained model.', 'Readings are SIMULATED.'],
  uses_simulated_data: true,
}

function mockApi(assessment: object = ASSESSMENT) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/zones')) return jsonResponse({ total: 1, items: [ZONE] })
    if (url.includes('/soil/assessments') && method === 'POST')
      return jsonResponse({ id: 9, zone_id: 1, created_at: NOW, confidence: 0.42, predicted_value: { index: 58.4 }, factors: [], limitations: 'x' }, 201)
    if (url.includes('/soil/assessments')) return jsonResponse({ total: 0, items: [] })
    if (url.includes('/soil-measurements')) return jsonResponse({ id: 3 }, 201)
    if (url.endsWith('/zones/1/soil')) return jsonResponse(assessment)
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('soil page', () => {
  it('explains the assessment: index, confidence, sources, factors, water and limitations', async () => {
    mockApi()
    renderRoute('/soil')
    expect(await screen.findByRole('heading', { name: 'North Field · Tomato' })).toBeInTheDocument()
    expect(screen.getByText('58')).toBeInTheDocument()
    expect(screen.getByText('Confidence 42 %')).toBeInTheDocument()
    expect(screen.getByText(/SIMULATED/, { selector: 'strong' })).toBeInTheDocument()

    const table = screen.getByRole('region', { name: 'Nutrients, pH and salinity' })
    expect(within(table).getByText('NPK probe 24 h mean (simulated)')).toBeInTheDocument()
    expect(within(table).getByText('100 mg/kg')).toBeInTheDocument()
    expect(within(table).getByText(/Not assessed/)).toBeInTheDocument()

    const water = screen.getByRole('region', { name: 'Root-zone water balance (FAO-56)' })
    expect(within(water).getByText('Stress expected in ~1 day')).toBeInTheDocument()
    expect(within(water).getByText('RAW 36.4 mm')).toBeInTheDocument()

    expect(screen.getByText(/below the Tomato optimum/)).toBeInTheDocument()
    expect(screen.getByText('This is rule-based scoring, not a trained model.')).toBeInTheDocument()
  })

  it('saves an assessment and submits a lab soil test with only the entered values', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/soil')
    await user.click(await screen.findByRole('button', { name: 'Save assessment' }))
    expect(await screen.findByText('Assessment saved to history.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add soil test' }))
    await user.click(screen.getByRole('button', { name: 'Save soil test' }))
    expect(screen.getByText('Enter at least one measured value.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('pH'), '6.4')
    await user.click(screen.getByRole('button', { name: 'Save soil test' }))
    await waitFor(() => expect(fetchSpy.mock.calls.some(([u]) => String(u).endsWith('/zones/1/soil-measurements'))).toBe(true))
    const call = fetchSpy.mock.calls.find(([u]) => String(u).endsWith('/zones/1/soil-measurements'))!
    const body = JSON.parse(String(call[1]?.body))
    expect(body).toMatchObject({ source: 'lab', ph: 6.4 })
    expect(body).not.toHaveProperty('nitrogen_mg_kg')
  })

  it('disables saving when nothing could be assessed', async () => {
    mockApi({ ...ASSESSMENT, index: null, rating: null, confidence: 0, components: {}, factors: [], water: null, uses_simulated_data: false })
    renderRoute('/soil')
    expect(await screen.findByRole('button', { name: 'Save assessment' })).toBeDisabled()
    expect(screen.getByText(/No moisture reading/)).toBeInTheDocument()
  })

  it('maps ratings to tones', () => {
    expect([statusTone('in_range'), statusTone('low'), statusTone('severe'), statusTone('high')]).toEqual(['ok', 'warn', 'alert', 'info'])
  })
})
