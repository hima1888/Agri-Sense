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
const EST = {
  zone_id: 1, zone_name: 'South Field', status: 'estimate', method: 'FAO-33 water-limited yield', crop: 'Maize', cycle_id: 9, area_hectares: 2,
  reference_is_custom: true, ky: 1.25, ym_kg_ha: 6000, ym_source: 'state variety trial 2024',
  yield_kg_ha: { low: 3500, central: 5100, high: 5700 }, total_kg: { low: 7000, central: 10200, high: 11400 }, relative_et: { low: 0.7, central: 0.88, high: 0.96 },
  water_loss_pct_central: 15, confidence: 0.2, uses_simulated_data: true,
  season: { planted: '2026-10-15', harvest: '2027-02-12', days_total: 121, days_elapsed: 31, days_measured: 3, coverage_elapsed: 0.1, coverage_season: 0.02 },
  factors: [{ name: 'Yield response to water (Ky)', value: 1.25, unit: '', source: 'FAO Irrigation and Drainage Paper 33, seasonal Ky' }],
  limitations: ['Water-limited estimate only (FAO-33): nutrients, pests, diseases are NOT modelled.'],
}
const NO_REF = { zone_id: 1, zone_name: 'South Field', status: 'no_reference', method: 'FAO-33', crop: 'Maize', cycle_id: 9, ky: 1.25, message: 'Enter the attainable yield for this variety and field (kg/ha).', limitations: [] }

function mockApi(est: object = EST) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/zones')) return jsonResponse({ total: 1, items: [ZONE] })
    if (url.endsWith('/zones/1/yield')) return jsonResponse(est)
    if (url.includes('/yield/predictions') && method === 'POST') return jsonResponse({ id: 3 }, 201)
    if (url.includes('/yield/predictions')) return jsonResponse({ total: 0, items: [] })
    if (url.endsWith('/yield/backtest')) return jsonResponse({ n: 0, mean_absolute_error_pct: null, share_within_range: null, cycles: [], message: 'No harvested cycles with a recorded yield and a saved estimate yet: the accuracy of these estimates on this farm is unknown.' })
    if (url.includes('/yield-reference') && method === 'PUT') return jsonResponse({ cycle_id: 9 })
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('yield page', () => {
  it('shows the range, coverage, factors, simulated warning and that accuracy is unknown', async () => {
    mockApi()
    renderRoute('/yield')
    const card = await screen.findByRole('region', { name: 'South Field · Maize' })
    expect(within(card).getByText(`${(5100).toLocaleString()} kg`)).toBeInTheDocument()
    expect(within(card).getByText(/moisture measured on 3 of 31 days/)).toBeInTheDocument()
    expect(within(card).getByText(/FAO Irrigation and Drainage Paper 33/)).toBeInTheDocument()
    expect(within(card).getByText(/15 % below attainable/)).toBeInTheDocument()
    expect(screen.getByText('SIMULATED')).toBeInTheDocument()
    expect(await screen.findByText(/accuracy of these estimates on this farm is unknown/)).toBeInTheDocument()
  })

  it('asks for the attainable yield and saves it with a source', async () => {
    const fetchSpy = mockApi(NO_REF)
    const user = userEvent.setup()
    renderRoute('/yield')
    expect(await screen.findByText(/Enter the attainable yield/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save estimate' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Set attainable yield' }))
    await user.type(screen.getByLabelText('Attainable yield (kg/ha)'), '6000')
    await user.type(screen.getByLabelText('Source'), 'KVK trial 2024')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/crop-cycles/9/yield-reference') && i?.method === 'PUT')
      expect(call && JSON.parse(String(call[1]?.body))).toEqual({ kg_ha: 6000, source: 'KVK trial 2024' })
    })
  })

  it('saves an estimate for later back-testing', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/yield')
    await user.click(await screen.findByRole('button', { name: 'Save estimate' }))
    expect(await screen.findByText(/compared with the actual harvest/)).toBeInTheDocument()
    expect(fetchSpy.mock.calls.some(([u, i]) => String(u).endsWith('/zones/1/yield/predictions') && i?.method === 'POST')).toBe(true)
  })
})
