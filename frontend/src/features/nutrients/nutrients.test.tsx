import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase } from '@/test/fake-supabase'
import { jsonResponse, renderRoute } from '@/test/render'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof createFakeSupabase> | null }))
vi.mock('@/lib/supabase', async () => {
  const { createFakeSupabase } = await import('@/test/fake-supabase')
  fake.current = createFakeSupabase()
  return { supabase: fake.current.supabase }
})

const NOW = new Date().toISOString()
const FARM = { id: 7, owner_id: 'u', name: 'Kaveri Farm', description: null, latitude: 17.4, longitude: 78.5, area_hectares: 12, timezone: 'Asia/Kolkata', created_at: NOW, updated_at: NOW }
const ZONE = { id: 1, farm_id: 7, name: 'South Field', zone_type: 'field', area_hectares: 2, irrigation_method: 'drip' }
const factor = (nutrient: string, rec: number, rating: string | null, f: number, adj: number, applied = 0, note: string | null = null) => ({
  nutrient, recommended_kg_ha: rec, soil_rating: rating, soil_source: 'lab test (10 days old)', factor: f, adjusted_kg_ha: adj,
  applied_kg_ha: applied, remaining_kg_ha: Math.max(0, adj - applied), surplus_kg_ha: Math.max(0, applied - adj), note,
})
const PLAN = {
  zone_id: 1, zone_name: 'South Field', status: 'plan', crop: 'Maize', cycle_id: 9, area_hectares: 2, target_is_custom: false,
  applications_counted: 1, lab_test_age_days: 10, uses_simulated_data: false,
  target_kg_ha: { n: 120, p2o5: 60, k2o: 40 }, target_source: 'indicative national-level general recommendation',
  adjusted_kg_ha: { n: 150, p2o5: 45, k2o: 40 }, applied_kg_ha: { n: 0, p2o5: 50, k2o: 0 }, remaining_kg_ha: { n: 150, p2o5: 0, k2o: 40 },
  factors: [factor('n', 120, 'low', 1.25, 150), factor('p2o5', 60, 'high', 0.75, 45, 50), factor('k2o', 40, 'medium', 1, 40)],
  products: [{ product: 'MOP', grade: '0-0-60', kg_per_ha: 66.7, supplies: 'K2O', kg_for_zone: 133.4, bags_50kg: 2.7 }, { product: 'Urea', grade: '46-0-0', kg_per_ha: 326.1, supplies: 'remaining N', kg_for_zone: 652.2, bags_50kg: 13 }],
  surplus_kg_ha: { p2o5: 5 }, soil_test_saving_kg_ha: { p2o5: 15 }, notes: ['Apply N in splits.'], confidence: 0.5,
  limitations: ['Using an INDICATIVE reference dose: set your state recommended dose.'],
}
const USE = {
  status: 'ok', crop: 'Maize', basis: 'computed from this farm\'s pesticide logs',
  current: { applications: 2, by_type: { fungicide: 2 }, quantity_by_unit: { l: 2 }, quantity_per_ha_by_unit: { l: 1 }, with_evidence: 1, evidence_share: 0.5, phi: [], phi_conflicts: 1, harvest_blocked_until: '2026-12-01' },
  previous: null, comparison: null, recent: [],
}
const CHECK = {
  verdict: 'hold', warnings: 2, limitations: ['Advisory only.'],
  evidence: [{ id: 44, label: 'Corn: Common rust', detected_at: NOW, outcome: 'possible_disease' }],
  checks: [{ check: 'evidence', status: 'ok', detail: 'possible disease: Corn: Common rust' }, { check: 'wind', status: 'warning', detail: 'Wind up to 6.5 m/s: drift risk above 4 m/s.' }, { check: 'pre_harvest_interval', status: 'warning', detail: 'Safe to harvest from 05 Dec' }],
}

function mockApi(plan: object = PLAN) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/zones')) return jsonResponse({ total: 1, items: [ZONE] })
    if (url.endsWith('/nutrients/plan')) return jsonResponse(plan)
    if (url.endsWith('/chemicals/use')) return jsonResponse(USE)
    if (url.includes('/chemicals/spray-check')) return jsonResponse(CHECK)
    if (url.includes('/nutrient-target') && method === 'PUT') return jsonResponse({ cycle_id: 9 })
    if (url.endsWith('/pesticide-applications') && method === 'POST') return jsonResponse({ id: 77 }, 201)
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('nutrients & chemicals page', () => {
  it('explains the soil-test adjustment, products, surplus and indicative-dose warning', async () => {
    mockApi()
    renderRoute('/nutrients')
    const card = await screen.findByRole('region', { name: 'Fertilizer plan · Maize' })
    expect(within(card).getByText(/Urea/)).toBeInTheDocument()
    expect(within(card).getByText(/652.2 kg here \(13 × 50 kg bags\)/)).toBeInTheDocument()
    expect(within(card).getByText(/lowers the dose by 15 kg\/ha P₂O₅/)).toBeInTheDocument()
    expect(within(card).getByText(/Applied above the adjusted dose: 5 kg\/ha P₂O₅/)).toBeInTheDocument()
    expect(within(card).getByText(/INDICATIVE reference dose/)).toBeInTheDocument()
    const use = screen.getByRole('region', { name: 'Chemical use this crop cycle' })
    expect(await within(use).findByText(/1 spray\(s\) would still be within the pre-harvest interval/)).toBeInTheDocument()
    expect(within(use).getByText(/No previous crop cycle/)).toBeInTheDocument()
  })

  it('saves the recommended dose with its source', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/nutrients')
    await user.click(await screen.findByRole('button', { name: 'Set recommended dose' }))
    const n = screen.getByLabelText('N (kg/ha)')
    await user.clear(n)
    await user.type(n, '100')
    await user.type(screen.getByLabelText('Source'), 'State PoP 2024')
    await user.click(screen.getByRole('button', { name: 'Save dose for this crop cycle' }))
    await waitFor(() => {
      const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/crop-cycles/9/nutrient-target') && i?.method === 'PUT')
      expect(call && JSON.parse(String(call[1]?.body))).toEqual({ n: 100, p2o5: 60, k2o: 40, source: 'State PoP 2024' })
    })
  })

  it('runs the spray check, shows warnings and links the spray to the evidence', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/nutrients')
    await user.type(await screen.findByLabelText('PHI (days, from label)'), '21')
    await user.click(screen.getByRole('button', { name: 'Check before spraying' }))
    expect(await screen.findByText('Hold: 2 warning(s)')).toBeInTheDocument()
    expect(screen.getByText(/drift risk/)).toBeInTheDocument()
    expect(fetchSpy.mock.calls.some(([u]) => String(u).includes('spray-check?pesticide_type=fungicide&phi_days=21'))).toBe(true)

    await user.type(screen.getByLabelText('Product'), 'Mancozeb 75 WP')
    await user.type(screen.getByLabelText('Quantity (whole zone)'), '2')
    await user.click(screen.getByRole('button', { name: 'Log spray' }))
    await waitFor(() => {
      const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/zones/1/pesticide-applications') && i?.method === 'POST')
      expect(call && JSON.parse(String(call[1]?.body))).toMatchObject({ product_name: 'Mancozeb 75 WP', pesticide_type: 'fungicide', quantity: 2, pre_harvest_interval_days: 21, disease_detection_id: 44 })
    })
  })
})
