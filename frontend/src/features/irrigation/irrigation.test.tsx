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
const ZONE = { id: 1, farm_id: 7, name: 'North Field', zone_type: 'field', area_hectares: 0.5, irrigation_method: 'drip' }
const day = (i: number, end: number, irr: number | null = null, note: string | null = null) => ({
  date: `2026-11-${14 + i}`, et0_mm: 6, etc_mm: 6.9, rain_mm: 0, effective_rain_mm: 0, depletion_start_mm: end - 6.9, irrigation_net_mm: irr, depletion_end_mm: end, note,
})
const EVENT = {
  date: '2026-11-15', day_index: 1, net_mm: 34.9, gross_mm: 38.8, volume_liters: 194000, depletion_before_mm: 41.8, urgent: false,
  reason: 'depletion would reach 41.8 mm, past the 36.4 mm stress threshold', window: { start_local_hour: 5, wind_speed_ms: 1, basis: 'calmest early-morning hour in the forecast' },
  scheduled_for: NOW, already_scheduled: false,
}
const PLAN = {
  zone_id: 1, zone_name: 'North Field', crop: 'Tomato', irrigation_method: 'drip', area_hectares: 0.5, status: 'planned',
  method: 'FAO-56 daily root-zone water balance with forecast ET0 and rain', uses_simulated_data: true, confidence: 0.4,
  limitations: ['Moisture comes from SIMULATED sensors: the plan demonstrates the method only.'], scheduled: [],
  water: { moisture_pct: 21, field_capacity_pct: 25, wilting_point_pct: 12, taw_mm: 91, raw_mm: 36.4, depletion_mm: 28, status: 'adequate', kc: 1.15, root_depth_m: 0.7, measured_at: NOW, irrigation_since_mm: 0, sources: { moisture: 'soil-moisture sensors (latest) (simulated)' } },
  plan: { events: [EVENT], days: [day(0, 34.9), day(1, 0, 34.9), day(2, 6.9, null, 'deferred: 12 mm rain')], total_net_mm: 34.9, total_gross_mm: 38.8, total_volume_liters: 194000, application_efficiency: 0.9, deferred_by_rain_mm: 0 },
  rain_aware_saving: { gross_mm: 7.7, volume_liters: 38500, basis: 'same rules with forecast rain ignored' },
}
const USE = { days: 7, events: 2, events_without_volume: 1, applied_liters: 20000, applied_gross_mm: 4, applied_net_mm: 3.6, estimated_need_mm: 0, weather_days_covered: 0, applied_to_need_ratio: null, basis: 'need = Kc x ET0' }

function mockApi(plan: object = PLAN) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/zones')) return jsonResponse({ total: 1, items: [ZONE] })
    if (url.endsWith('/irrigation/plan')) return jsonResponse(plan)
    if (url.includes('/irrigation/water-use')) return jsonResponse(USE)
    if (url.endsWith('/irrigation/schedule') && init?.method === 'POST') return jsonResponse({ id: 55 }, 201)
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('irrigation page', () => {
  it('shows the plan, why, the saving estimate, water use and the simulated warning', async () => {
    mockApi()
    renderRoute('/irrigation')
    const planned = await screen.findByRole('region', { name: 'Planned irrigations' })
    expect(within(planned).getByText(`38.8 mm gross (34.9 mm net) · ${(194000).toLocaleString()} L`)).toBeInTheDocument() // host locale grouping
    expect(within(planned).getByText(/past the 36.4 mm stress threshold/)).toBeInTheDocument()
    expect(within(planned).getByText((t) => t.includes(`avoids an estimated 7.7 mm (${(38500).toLocaleString()} L)`))).toBeInTheDocument()
    expect(screen.getByText('simulated', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('deferred')).toBeInTheDocument()
    const use = screen.getByRole('region', { name: 'Water use' })
    expect(await within(use).findByText(/1 event\(s\) have no volume/)).toBeInTheDocument()
    expect(within(use).getByText(/stored weather covers 0 of 7 days/)).toBeInTheDocument()
  })

  it('schedules a planned irrigation for its date', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/irrigation')
    await user.click(await screen.findByRole('button', { name: 'Schedule' }))
    await waitFor(() => {
      const call = fetchSpy.mock.calls.find(([u]) => String(u).endsWith('/zones/1/irrigation/schedule'))
      expect(call && JSON.parse(String(call[1]?.body))).toEqual({ date: '2026-11-15' })
    })
  })

  it('explains when there is no moisture data', async () => {
    mockApi({ ...PLAN, status: 'no_moisture_data', water: null, plan: null, confidence: 0, uses_simulated_data: false, message: 'No soil-moisture reading: add a soil test with moisture.' })
    renderRoute('/irrigation')
    expect(await screen.findByText('No moisture data')).toBeInTheDocument()
    expect(screen.getByText(/No soil-moisture reading/)).toBeInTheDocument()
  })
})
