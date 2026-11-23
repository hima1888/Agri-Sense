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
const FARM = {
  id: 7, owner_id: 'u', name: 'Kaveri Farm', description: null, latitude: 17.385, longitude: 78.487,
  area_hectares: 12.5, timezone: 'Asia/Kolkata', created_at: NOW, updated_at: NOW,
}
const zone = (id: number, name: string, moisture: number) => ({
  id, name, zone_type: 'field', area_hectares: 4, irrigation_method: 'drip', sensor_count: 2,
  active_cycle: id === 1 ? { id: 3, crop_name: 'Tomato', variety: 'Arka Rakshak', status: 'growing', planted_on: '2026-09-01', expected_harvest_on: null } : null,
  latest: { soil_moisture: { value: moisture, recorded_at: NOW, unit: '%' }, temperature: { value: 24.2, recorded_at: NOW, unit: '°C' } },
})
const alert = (id: number, severity: string, title: string) => ({
  id, farm_id: 7, zone_id: 1, sensor_id: null, severity, category: 'soil', status: 'open', title, message: 'Check the zone',
  triggered_at: NOW, acknowledged_at: null, resolved_at: null,
})
const DASHBOARD = {
  farm_id: 7, generated_at: NOW,
  zones: [zone(1, 'North Field', 22.4), zone(2, 'South Field', 28.6)],
  sensors: { total: 4, active: 4, simulated: 4, hardware: 0, reporting: 4 },
  alerts: { open: 2, by_severity: { info: 0, warning: 1, critical: 1 }, recent: [alert(11, 'critical', 'Soil very dry'), alert(12, 'warning', 'Tank low')] },
  activity: [{ kind: 'irrigation', id: 5, zone_id: 1, at: NOW, title: 'drip', amount: 1500, unit: 'L', status: 'completed' }],
  water_7d: { liters: 1500, events: 1 },
  readings_24h: { count: 576, not_good: 2 },
  stats_24h: [],
}
const WEATHER = {
  farm_id: 7, source: 'open-meteo', attribution: 'Weather data by Open-Meteo.com (CC BY 4.0)', timezone: 'Asia/Kolkata',
  fetched_at: NOW, stale: false, error: null,
  current: { valid_at: NOW, temperature_c: 26.3, relative_humidity_pct: 58, precipitation_mm: 0, precipitation_probability_pct: null, wind_speed_ms: 1.6, wind_direction_deg: 73, cloud_cover_pct: 40, shortwave_radiation_wm2: 500, et0_mm: null },
  hourly: [],
  daily: [{ date: '2026-11-14', temp_min_c: 17.2, temp_max_c: 29.6, precipitation_mm: 0.4, precipitation_probability_max_pct: 35, et0_mm: 4.1 }],
}

function stalledStream() {
  const body = new ReadableStream<Uint8Array>({
    start: (c) => c.enqueue(new TextEncoder().encode('event: snapshot\ndata: {"farm_id":7,"sensors":[]}\n\n')),
  })
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

function mockApi(farms = [FARM]) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/stream')) return stalledStream()
    if (url.includes('/alerts/') && method === 'POST') return jsonResponse({ ...alert(11, 'critical', 'Soil very dry'), status: 'resolved' })
    if (url.endsWith('/farms') && method === 'POST') return jsonResponse({ ...FARM, ...JSON.parse(String(init?.body)), id: 99 }, 201)
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: farms.length, items: farms })
    if (url.endsWith('/dashboard')) return jsonResponse(DASHBOARD)
    if (url.includes('/weather')) return jsonResponse(WEATHER)
    if (url.includes('/series')) return jsonResponse({ sensor_type: 'soil_moisture', unit: '%', includes_simulated: true, bucket_minutes: 15, start: NOW, end: NOW, zones: [] })
    if (url.includes('/zones')) return jsonResponse({ total: 0, items: [] })
    return jsonResponse({ status: 'ok', service: 'x', version: '1', timestamp: NOW })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('dashboard', () => {
  it('shows KPIs, weather, zones and alerts from the API, labelling simulated data', async () => {
    mockApi()
    renderRoute('/dashboard')
    expect(await screen.findByRole('heading', { name: 'Kaveri Farm', level: 1 })).toBeInTheDocument()

    expect(screen.getByText(/4 of 4 sensors are simulated/i)).toBeInTheDocument()
    expect(screen.getByText('25.5')).toBeInTheDocument() // mean soil moisture of the two zones
    expect(await screen.findByText('26.3')).toBeInTheDocument() // Open-Meteo current temperature
    expect(screen.getAllByText('30°')).toHaveLength(2) // today's max: KPI tile + 7-day outlook
    expect(screen.getByText('1.5')).toBeInTheDocument() // 1,500 L in m³
    expect(screen.getByText(/Weather data by Open-Meteo.com/)).toBeInTheDocument()

    const zones = screen.getByRole('region', { name: 'Zones' })
    expect(within(zones).getByText('North Field')).toBeInTheDocument()
    expect(within(zones).getByText('Tomato')).toBeInTheDocument()

    const alerts = screen.getByRole('region', { name: 'Alerts' })
    expect(within(alerts).getByText('Critical')).toBeInTheDocument() // severity has a text label, not colour alone
    expect(within(alerts).getByText('Soil very dry')).toBeInTheDocument()
  })

  it('resolves an alert through the API', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/dashboard')
    const alerts = await screen.findByRole('region', { name: 'Alerts' })
    await user.click(within(alerts).getAllByRole('button', { name: 'Resolve' })[0]!)
    await waitFor(() =>
      expect(fetchSpy.mock.calls.some(([u, i]) => String(u).endsWith('/alerts/11/resolve') && i?.method === 'POST')).toBe(true),
    )
  })

  it('invites the user to create a farm when there is none', async () => {
    mockApi([])
    renderRoute('/dashboard')
    expect(await screen.findByRole('button', { name: 'Set up a demo farm' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Create my own farm' })).toHaveAttribute('href', '/farms')
  })
})

describe('farms', () => {
  it('validates coordinates and creates a farm with a real time zone', async () => {
    const fetchSpy = mockApi([])
    const user = userEvent.setup()
    renderRoute('/farms')
    await user.type(await screen.findByLabelText('Farm name'), 'Godavari Farm')
    await user.type(screen.getByLabelText('Latitude'), '123')
    await user.click(screen.getByRole('button', { name: 'Create farm' }))
    expect(screen.getByText('Latitude must be between -90 and 90.')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Latitude'))
    await user.type(screen.getByLabelText('Latitude'), '16.5')
    await user.type(screen.getByLabelText('Longitude'), '81.8')
    await user.click(screen.getByRole('button', { name: 'Create farm' }))
    await waitFor(() => expect(fetchSpy.mock.calls.some(([u, i]) => String(u).endsWith('/farms') && i?.method === 'POST')).toBe(true))
    const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/farms') && i?.method === 'POST')!
    const body = JSON.parse(String(call[1]?.body))
    expect(body).toMatchObject({ name: 'Godavari Farm', latitude: 16.5, longitude: 81.8, area_hectares: null })
    expect(typeof body.timezone).toBe('string')
  })

  it("keeps the farm's saved time zone selected (no silent fallback to another zone)", async () => {
    const supported = vi.spyOn(Intl, 'supportedValuesOf').mockReturnValue(['Africa/Abidjan', 'Asia/Calcutta', 'UTC'])
    mockApi()
    renderRoute('/farms/7')
    const select = (await screen.findByLabelText('Time zone')) as HTMLSelectElement
    expect(select.value).toBe('Asia/Kolkata')
    expect([...select.options].map((o) => o.value)).not.toContain('Asia/Calcutta') // legacy name modernised
    supported.mockRestore()
  })
})
