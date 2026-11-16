/** Phase 18: tests for code the coverage report showed as untested. */
import { render, renderHook, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { DataTable, Legend, TrendChart, WeatherCharts } from '@/features/dashboard/charts'
import { clientToNdc } from '@/features/twin/events'
import { useAuthedImage } from '@/lib/use-authed-image'
import { createFakeSupabase } from '@/test/fake-supabase'
import { jsonResponse, renderRoute } from '@/test/render'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof createFakeSupabase> | null }))
vi.mock('@/lib/supabase', async () => {
  const { createFakeSupabase } = await import('@/test/fake-supabase')
  fake.current = createFakeSupabase()
  return { supabase: fake.current.supabase }
})

beforeAll(() => {
  URL.createObjectURL = vi.fn(() => 'blob:image')
  URL.revokeObjectURL = vi.fn()
})
beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('useAuthedImage', () => {
  it('fetches with the bearer token, returns an object URL and revokes it on unmount', async () => {
    const { setAccessTokenProvider } = await import('@/lib/api-client')
    setAccessTokenProvider(async () => 'tok')
    // jsdom's Response cannot stream a Blob, so hand back the parts the hook uses.
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(['x']) } as Response)
    const { result, unmount } = renderHook(() => useAuthedImage('/vision/recognitions/1/image'))
    await waitFor(() => expect(result.current).toBe('blob:image'))
    expect((spy.mock.calls[0]![1] as RequestInit).headers).toEqual({ Authorization: 'Bearer tok' })
    unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:image')
    setAccessTokenProvider(async () => null)
  })

  it('stays null when the image cannot be loaded', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 404 } as Response)
    const { result } = renderHook(() => useAuthedImage('/missing'))
    await new Promise((r) => setTimeout(r, 20))
    expect(result.current).toBeNull()
  })
})

describe('charts', () => {
  const series = {
    sensor_type: 'soil_moisture' as const, unit: '%', includes_simulated: true, bucket_minutes: 15,
    start: '2026-11-15T00:00:00Z', end: '2026-11-15T01:00:00Z',
    zones: [
      { zone_id: 2, zone_name: 'South', points: [{ t: '2026-11-15T00:00:00Z', avg: 21.25, min: 21, max: 22, n: 4 }] },
      { zone_id: 1, zone_name: 'North', points: [{ t: '2026-11-15T00:00:00Z', avg: 24.5, min: 24, max: 25, n: 4 }] },
    ],
  }

  it('gives every chart an accessible data table, colouring zones by fixed order not by rank', () => {
    render(<TrendChart series={series} zoneOrder={[1, 2]} tz="UTC" decimals={1} />)
    const legend = screen.getByRole('list', { name: 'Legend' })
    const swatch = (name: string) => (within(legend).getByText(name).querySelector('span') as HTMLElement).style.background
    expect(swatch('North')).toBe('rgb(57, 135, 229)') // zone 1 -> first palette colour (#3987e5)
    expect(swatch('South')).toBe('rgb(217, 89, 38)') // zone 2 -> second (#d95926)
    const table = screen.getByRole('table')
    expect(within(table).getByText('24.5')).toBeInTheDocument()
    expect(within(table).getByText('21.3')).toBeInTheDocument() // decimals applied
  })

  it('renders weather charts and a standalone table', () => {
    const hourly = [{ valid_at: '2026-11-15T06:00:00Z', temperature_c: 22.4, relative_humidity_pct: 60, precipitation_mm: 0.5, precipitation_probability_pct: 30, wind_speed_ms: 2, wind_direction_deg: 90, cloud_cover_pct: 20, shortwave_radiation_wm2: 300, et0_mm: 0.2 }]
    render(<WeatherCharts hourly={hourly} tz="UTC" />)
    const wx = screen.getByRole('table', { name: 'Hourly forecast: temperature and chance of rain' })
    expect(within(wx).getByText('22.4')).toBeInTheDocument()
    render(<WeatherCharts hourly={[]} tz="UTC" />)
    expect(screen.getByText('No forecast available.')).toBeInTheDocument()
    render(<DataTable caption="Demo" headers={['a', 'b']} rows={[['1', '2']]} />)
    expect(screen.getByRole('table', { name: 'Demo' })).toBeInTheDocument()
    render(<Legend items={[{ key: 'x', label: 'Rain', color: '#00f' }]} />)
  })
})

describe('twin pointer maths', () => {
  it('maps client coordinates to normalised device coordinates', () => {
    const rect = { left: 100, top: 50, width: 200, height: 100 }
    expect(clientToNdc(200, 100, rect)).toEqual([0, 0])
    expect(clientToNdc(100, 50, rect)).toEqual([-1, 1])
    expect(clientToNdc(300, 150, rect)).toEqual([1, -1])
  })
})

describe('live page set-up', () => {
  it('creates a farm with its first zone, then provisions a simulated kit', async () => {
    const created = { id: 9, owner_id: 'u', name: 'New Farm', description: null, latitude: 17.4, longitude: 78.5, area_hectares: null, timezone: 'Asia/Kolkata', created_at: '', updated_at: '' }
    let farms: unknown[] = []
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/farms') && method === 'POST') {
        farms = [created]
        return jsonResponse(created, 201)
      }
      if (url.endsWith('/farms/9/zones') && method === 'POST') return jsonResponse({ id: 3, farm_id: 9, name: 'North Field', zone_type: 'field', area_hectares: null, irrigation_method: null }, 201)
      if (url.includes('/farms?limit=100')) return jsonResponse({ total: farms.length, items: farms })
      if (url.includes('/farms/9/zones')) return jsonResponse({ total: 1, items: [{ id: 3, farm_id: 9, name: 'North Field', zone_type: 'field', area_hectares: null, irrigation_method: null }] })
      if (url.includes('/simulator/provision')) return jsonResponse({ zone_id: 3, created: 12, sensors: [] }, 201)
      if (url.endsWith('/farms/9/simulator')) return jsonResponse({ farm_id: 9, simulated_sensors: 0, running: true, interval_seconds: 10, last_tick_at: null })
      if (url.includes('/stream')) return new Response(new ReadableStream({ start: (c) => c.enqueue(new TextEncoder().encode('event: snapshot\ndata: {"farm_id":9,"sensors":[]}\n\n')) }), { headers: { 'Content-Type': 'text/event-stream' } })
      return jsonResponse({})
    })
    const user = userEvent.setup()
    renderRoute('/live')
    await user.type(await screen.findByLabelText('Farm name'), 'New Farm')
    await user.type(screen.getByLabelText('Latitude'), '17.4')
    await user.type(screen.getByLabelText('Longitude'), '78.5')
    await user.click(screen.getByRole('button', { name: 'Create farm' }))
    await waitFor(() => expect(spy.mock.calls.some(([u, i]) => String(u).endsWith('/farms/9/zones') && i?.method === 'POST')).toBe(true))
    await user.click(await screen.findByRole('button', { name: 'Add simulated sensor kit' }))
    await waitFor(() => expect(spy.mock.calls.some(([u, i]) => String(u).endsWith('/zones/3/simulator/provision') && i?.method === 'POST')).toBe(true))
  })
})
