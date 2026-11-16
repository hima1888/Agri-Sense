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
const ANALYTICS = {
  farm_id: 7, farm_name: 'Kaveri Farm', period: { start: '2026-11-01', end: '2026-11-10', days: 10, timezone: 'Asia/Kolkata' },
  previous_period: { start: '2026-10-22', end: '2026-10-31', days: 10, timezone: 'Asia/Kolkata' }, area_ha: 2, zones: 2,
  indicators: [
    { indicator: 'Irrigation water per ha', unit: 'L/ha', current: 20000, previous: 40000, change_pct: -50 },
    { indicator: 'Sprays linked to a disease check', unit: 'share', current: 0.5, previous: null, change_pct: null },
  ],
  mean_stress_share: 0.1, uses_simulated_data: true, notes: ['Figures come only from records in AGRI-SENSE.'],
  water: { irrigation_events: 2, events_without_volume: 1, irrigation_liters: 40000, irrigation_mm: 2, by_zone: [{ zone: 'A', liters: 30000, mm: 2 }], rain_mm: null, et0_mm: null, weather_days_covered: 0,
    stress: [{ zone: 'A', measured_hours: 48, threshold_pct: 19.8, stress_share: 0.25 }] },
  fertilizer: { applications: 1, product_kg: 100, organic_kg: 0, nutrients_kg: { n: 46, p2o5: 0, k2o: 0 }, without_grade: 0 },
  pesticides: { applications: 1, by_type: { fungicide: 1 }, with_evidence: 0 },
  health: { disease_checks: 0, by_outcome: {}, possible_diseases: {} }, harvests: [],
  advice: { recommendations: 3, by_status: { accepted: 1, pending: 2 }, uptake: 1 },
  alerts: { raised: 0, by_severity: {}, resolved: 0, median_hours_to_resolve: null },
  data: { readings: 5000, not_good_share: 0.001, simulated_share: 1, zones_without_area: [] },
}
const REPORT = { id: 11, farm_id: 7, report_type: 'farm_summary', title: 'Farm summary: Kaveri Farm, 01 Nov 2026 to 10 Nov 2026', status: 'ready', period_start: '2026-11-01', period_end: '2026-11-10', created_at: NOW }

function mockApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/analytics')) return jsonResponse(ANALYTICS)
    if (url.endsWith('/farms/7/reports') && method === 'POST') return jsonResponse({ ...REPORT, content: ANALYTICS }, 201)
    if (url.includes('/farms/7/reports')) return jsonResponse({ total: 1, items: [REPORT] })
    if (url.endsWith('/reports/11')) return jsonResponse({ ...REPORT, content: ANALYTICS })
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('analytics & reports', () => {
  it('shows indicators vs the previous period and every section, flagging missing data', async () => {
    mockApi()
    renderRoute('/analytics')
    const ind = await screen.findByRole('region', { name: 'Sustainability indicators' })
    expect(within(ind).getByText('-50 %')).toBeInTheDocument()
    expect(within(ind).getByText(/Previous \(2026-10-22 to 2026-10-31\)/)).toBeInTheDocument()
    const water = screen.getByRole('region', { name: 'Water' })
    expect(within(water).getByText('no weather stored for this period')).toBeInTheDocument()
    expect(within(water).getByText(/25 % of 48 h \(below 19.8 %\)/)).toBeInTheDocument()
    expect(within(water).getByText('Events without a volume (not counted)')).toBeInTheDocument()
    expect(screen.getByText('simulated', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText(/none recorded in this period/)).toBeInTheDocument()
  })

  it('saves a report for the selected period', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/analytics')
    await user.click(await screen.findByRole('button', { name: 'Last 7 days' }))
    await user.selectOptions(screen.getByLabelText('Report type'), 'sustainability')
    await user.click(screen.getByRole('button', { name: 'Save report for this period' }))
    await waitFor(() => {
      const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/farms/7/reports') && i?.method === 'POST')
      const body = call && JSON.parse(String(call[1]?.body))
      expect(body?.report_type).toBe('sustainability')
      expect(new Date(body.period_end).getTime() - new Date(body.period_start).getTime()).toBe(6 * 86_400_000)
    })
  })

  it('renders a printable saved report', async () => {
    mockApi()
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const user = userEvent.setup()
    renderRoute('/reports/11')
    expect(await screen.findByRole('heading', { name: REPORT.title })).toBeInTheDocument()
    expect(screen.getByText(/Includes/, { selector: 'p' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Print / save as PDF' }))
    expect(print).toHaveBeenCalled()
  })
})
