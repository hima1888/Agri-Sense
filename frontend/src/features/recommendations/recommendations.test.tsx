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
const IRRIGATE = {
  id: 31, rule: 'irrigate_now', zone_id: 1, zone_name: 'North Field', category: 'irrigation', priority: 'high',
  title: 'Irrigate North Field now: about 44.4 mm (~222,000 L for 0.5 ha)',
  rationale: 'Root-zone depletion 40 mm is past the 36.4 mm stress threshold for Tomato.',
  action: { type: 'irrigate', gross_mm: 44.4 },
  factors: [
    { name: 'Soil moisture', value: 19.3, unit: '% vol', source: 'soil-moisture sensors (latest) (simulated)', simulated: true },
    { name: 'Forecast rain, next 48 h', value: 0, unit: 'mm', source: 'Open-Meteo forecast', simulated: false },
  ],
  confidence: 0.76, confidence_basis: 'data confidence 0.80 x rule certainty 0.95', expected_impact: null,
  limitations: ['Based partly on SIMULATED sensor data: a demonstration, not advice for a real field.'],
  uses_simulated_data: true, expires_at: NOW,
}
const SOIL_TEST = { ...IRRIGATE, id: 32, rule: 'soil_test_needed', category: 'soil', priority: 'low', title: 'Get a lab soil test for South Field', zone_id: 2, zone_name: 'South Field', factors: [], uses_simulated_data: false, action: { type: 'soil_test' }, limitations: [] }
const SET = { farm_id: 7, generated_at: NOW, method: 'rule-based', weather_fetched_at: NOW, forecast_hours: 72, zones_assessed: 2, recommendations: [IRRIGATE, SOIL_TEST], uses_simulated_data: true, stored: { created: 2, refreshed: 0, expired: 0 } }
const stored = (id: number, status: string, title: string) => ({ id, zone_id: 1, rule: 'x', priority: 'high', status, title, confidence: 0.7, created_at: NOW, responded_at: status === 'pending' ? null : NOW })

function mockApi(set: object = SET, history = [stored(31, 'pending', IRRIGATE.title), stored(32, 'pending', SOIL_TEST.title)]) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.endsWith('/recommendations/generate')) return jsonResponse(set)
    if (url.includes('/respond')) return jsonResponse({ ...stored(31, JSON.parse(String(init?.body)).status, IRRIGATE.title) })
    if (url.includes('/recommendations?')) return jsonResponse({ total: history.length, items: history })
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('recommendations page', () => {
  it('shows prioritised advice with confidence, evidence and the simulated-data warning', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/advice')
    const card = await screen.findByRole('listitem', { name: IRRIGATE.title })
    expect(within(card).getByText('high')).toBeInTheDocument()
    expect(within(card).getByText(/Confidence 76 % \(data confidence 0.80 x rule certainty 0.95\)/)).toBeInTheDocument()
    expect(screen.getByText('SIMULATED')).toBeInTheDocument()
    const items = screen.getAllByRole('listitem').filter((li) => li.getAttribute('aria-label'))
    expect(items.map((li) => li.getAttribute('aria-label'))).toEqual([IRRIGATE.title, SOIL_TEST.title])

    await user.click(within(card).getByRole('button', { name: /Why\?/ }))
    expect(within(card).getByText('Forecast rain, next 48 h')).toBeInTheDocument()
    expect(within(card).getByText(/soil-moisture sensors \(latest\) \(simulated\)/)).toBeInTheDocument()
  })

  it('records a decision through the API', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/advice')
    const card = await screen.findByRole('listitem', { name: IRRIGATE.title })
    await user.click(within(card).getByRole('button', { name: 'Accept' }))
    await waitFor(() => {
      const call = fetchSpy.mock.calls.find(([u]) => String(u).endsWith('/recommendations/31/respond'))
      expect(call && JSON.parse(String(call[1]?.body))).toEqual({ status: 'accepted' })
    })
  })

  it('says so when no rule fires and when there is no forecast', async () => {
    mockApi({ ...SET, recommendations: [], forecast_hours: 0, uses_simulated_data: false }, [])
    renderRoute('/advice')
    expect(await screen.findByText(/None of the rules fired/)).toBeInTheDocument()
    expect(screen.getByText(/No stored weather forecast/)).toBeInTheDocument()
  })
})
