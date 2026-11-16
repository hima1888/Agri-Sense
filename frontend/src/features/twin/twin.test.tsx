import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase } from '@/test/fake-supabase'
import { jsonResponse, renderRoute } from '@/test/render'
import { clientToNdc } from './events'
import { canopySize, canopyTint, cropInstances, cropRows, moistureColor, pointInPolygon, sensorStatus, sunDirection } from './layout'
import { mergeLiveSensors, mergeLiveZones } from './merge-live'
import type { FarmTwin, TwinSensor, TwinZone } from './schemas'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof createFakeSupabase> | null }))
vi.mock('@/lib/supabase', async () => {
  const { createFakeSupabase } = await import('@/test/fake-supabase')
  fake.current = createFakeSupabase()
  return { supabase: fake.current.supabase }
})
// WebGL is not available in jsdom: stand in for the canvas and expose what it was given.
vi.mock('@/features/twin/Scene', () => ({
  TwinCanvas: (p: { layers: Record<string, boolean>; selection: unknown; sensors: TwinSensor[] }) => (
    <div data-testid="canvas" data-layers={JSON.stringify(p.layers)} data-selection={JSON.stringify(p.selection)} data-sensor-values={p.sensors.map((s) => s.latest?.value).join(',')} />
  ),
}))

const NOW = new Date().toISOString()
const zone = (over: Partial<TwinZone> = {}): TwinZone => ({
  id: 1, name: 'North', zone_type: 'field', area_hectares: 1, irrigation_method: 'drip',
  polygon: [[-50, -30], [50, -30], [50, 30], [-50, 30]], center: [0, 0], size: [100, 60], layout: 'auto',
  crop: { cycle_id: 1, crop_name: 'Tomato', variety: null, category: 'vegetable', status: 'growing', planted_on: '2026-09-01',
          expected_harvest_on: null, growth_fraction: 0.5, row_spacing_m: 0.75, form: 'bush' },
  soil_moisture: 24, temperature: 23, irrigating: false, irrigation_started_at: null, ...over,
})
const sensor = (id: number, type: TwinSensor['sensor_type'], value: number, quality: 'good' | 'suspect' = 'good', at = NOW): TwinSensor => ({
  id, name: `${type} · North`, zone_id: 1, device_id: 9, sensor_type: type, unit: type === 'temperature' ? '°C' : '%',
  source: 'simulated', is_simulated: true, status: 'active', position: [0, 0, 0], latest: { value, quality, recorded_at: at },
})

describe('twin geometry', () => {
  it('tests points against polygons', () => {
    const tri = [[0, 0], [10, 0], [0, 10]] as const
    expect(pointInPolygon([2, 2], tri)).toBe(true)
    expect(pointInPolygon([8, 8], tri)).toBe(false)
  })

  it('lays crop rows inside the zone within the instance budget, scaled by growth', () => {
    const plants = cropInstances(zone(), 500)
    expect(plants.length).toBeGreaterThan(300)
    expect(plants.length).toBeLessThanOrEqual(500)
    expect(plants.every((p) => Math.abs(p.x) <= 50 && Math.abs(p.z) <= 30)).toBe(true)
    const mature = cropInstances(zone({ crop: { ...zone().crop!, growth_fraction: 1 } }), 200)
    const planned = cropInstances(zone({ crop: { ...zone().crop!, status: 'planned', growth_fraction: null } }), 200)
    const mean = (ps: { scale: number }[]) => ps.reduce((a, p) => a + p.scale, 0) / ps.length
    expect(mean(mature)).toBeGreaterThan(mean(plants))
    expect(mean(planned)).toBeLessThan(0.2)
    expect(cropInstances(zone({ crop: null }))).toEqual([])
  })

  it('is deterministic (same scene every render)', () => {
    expect(cropInstances(zone(), 300)).toEqual(cropInstances(zone(), 300))
  })

  it('maps soil moisture to a single-hue scale that darkens as it gets wetter', () => {
    const lum = (hex: string) => {
      const n = parseInt(hex.slice(1), 16)
      return 0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)
    }
    const values = [5, 10, 18, 25, 32, 40, 55].map(moistureColor)
    for (let i = 1; i < values.length; i++) expect(lum(values[i]!)).toBeLessThanOrEqual(lum(values[i - 1]!))
    expect(moistureColor(null)).toBe('#4a4a42') // no data is neutral, never a guessed value
  })

  it('classifies sensor status by quality and freshness', () => {
    const t = Date.parse(NOW)
    expect(sensorStatus(null, t).key).toBe('none')
    expect(sensorStatus({ quality: 'suspect', recorded_at: NOW }, t).key).toBe('suspect')
    expect(sensorStatus({ quality: 'good', recorded_at: NOW }, t).key).toBe('good')
    expect(sensorStatus({ quality: 'good', recorded_at: NOW }, t + 11 * 60_000).key).toBe('stale')
  })

  it('points the sun east, south and overhead correctly (x east, z south)', () => {
    const [ex, , ez] = sunDirection(0, 90)
    expect(ex).toBeCloseTo(1)
    expect(ez).toBeCloseTo(0)
    expect(sunDirection(0, 180)[2]).toBeCloseTo(1)
    expect(sunDirection(0, 0)[2]).toBeCloseTo(-1)
    expect(sunDirection(90, 0)[1]).toBeCloseTo(1)
  })
})

describe('row crops and canopy', () => {
  it('draws rows at the real spacing along the long axis, clipped to the zone', () => {
    const z = zone({ crop: { ...zone().crop!, row_spacing_m: 2 } }) // 60 m deep -> ~30 rows of 100 m
    const rows = cropRows(z)
    expect(rows.every((r) => r.alongX)).toBe(true) // the zone is wider (x) than deep (z)
    const distinctRows = new Set(rows.map((r) => r.z.toFixed(2)))
    expect(distinctRows.size).toBeGreaterThanOrEqual(28)
    expect(distinctRows.size).toBeLessThanOrEqual(31)
    expect(rows.every((r) => Math.abs(r.x) <= 50 && Math.abs(r.z) <= 30)).toBe(true)
    const triangle = zone({ polygon: [[-50, -30], [50, -30], [-50, 30]] })
    expect(cropRows(triangle).every((r) => pointInPolygon([r.x, r.z], triangle.polygon as never))).toBe(true)
  })

  it('thins rows above the budget instead of drawing thousands of stripes', () => {
    const dense = zone({ crop: { ...zone().crop!, row_spacing_m: 0.1 } })
    expect(new Set(cropRows(dense, 40).map((r) => r.z.toFixed(2))).size).toBeLessThanOrEqual(40)
    expect(cropRows(zone({ crop: { ...zone().crop!, form: 'tree' } }))).toEqual([]) // orchards use individual trees
  })

  it('grows canopy with crop stage and tints the field accordingly', () => {
    const young = canopySize(zone({ crop: { ...zone().crop!, growth_fraction: 0.1 } }))
    const mature = canopySize(zone({ crop: { ...zone().crop!, growth_fraction: 0.9 } }))
    expect(mature.width).toBeGreaterThan(young.width)
    expect(mature.height).toBeGreaterThan(young.height)
    expect(mature.cover).toBeGreaterThan(young.cover)
    expect(canopySize(zone({ crop: null })).cover).toBe(0)
    expect(canopyTint('#5a4331', 0)).toBe('#5a4331') // bare soil
    expect(canopyTint('#5a4331', 1)).toBe('#4f7f3a') // full canopy
  })
})

describe('pointer mapping', () => {
  it('maps client coordinates to NDC against the canvas rect (independent of offsetX and device scale)', () => {
    const rect = { left: 0, top: 65, width: 983, height: 421 }
    expect(clientToNdc(0, 65, rect)).toEqual([-1, 1])
    expect(clientToNdc(983, 486, rect)).toEqual([1, -1])
    const [x, y] = clientToNdc(560, 300, rect)
    expect(x).toBeCloseTo(0.139, 3)
    expect(y).toBeCloseTo(-0.116, 3)
  })
})

describe('live merge', () => {
  it('applies only newer stream readings and recomputes zone values from good readings', () => {
    const older = new Date(Date.parse(NOW) - 60_000).toISOString()
    const newer = new Date(Date.parse(NOW) + 60_000).toISOString()
    const api = [sensor(1, 'soil_moisture', 20), sensor(2, 'soil_moisture', 22)]
    const merged = mergeLiveSensors(api, [
      { ...api[0]!, zone_id: 1, min_valid: 0, max_valid: 100, latest: { value: 30, quality: 'good', recorded_at: newer } },
      { ...api[1]!, zone_id: 1, min_valid: 0, max_valid: 100, latest: { value: 99, quality: 'good', recorded_at: older } },
    ] as never)
    expect(merged.map((s) => s.latest?.value)).toEqual([30, 22])
    const zones = mergeLiveZones([zone()], [...merged, sensor(3, 'soil_moisture', 90, 'suspect')])
    expect(zones[0]!.soil_moisture).toBe(26) // mean of 30 and 22; the suspect 90 is ignored
  })
})

// --- page ------------------------------------------------------------------------
const TWIN: FarmTwin = {
  farm_id: 7, farm_name: 'Kaveri Farm', generated_at: NOW, units: 'metres',
  extent: { min: [-50, -30], max: [50, 30] }, sun: { elevation_deg: 42, azimuth_deg: 160 },
  weather: { observed_at: NOW, temperature_c: 26, wind_speed_ms: 2.4, wind_direction_deg: 90, cloud_cover_pct: 40, precipitation_mm: 0 },
  zones: [zone()],
  sensors: [sensor(11, 'soil_moisture', 24.4), sensor(12, 'temperature', 23.1)],
  infrastructure: [
    { kind: 'tank', id: 'tank', position: [0, 0, 60], level_pct: 72, capacity_l: 20000, schematic: false },
    { kind: 'farmhouse', id: 'farmhouse', position: [20, 0, 70], schematic: true },
    { kind: 'solar', id: 'solar', position: [60, 0, 70], schematic: true, optional: true },
  ],
}

function mockApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/stream')) {
      const later = new Date(Date.parse(NOW) + 5_000).toISOString()
      const snap = { farm_id: 7, sensors: [{ ...TWIN.sensors[0], min_valid: 0, max_valid: 100, latest: { value: 27.5, quality: 'good', recorded_at: later } }] }
      const body = new ReadableStream<Uint8Array>({ start: (c) => c.enqueue(new TextEncoder().encode(`event: snapshot\ndata: ${JSON.stringify(snap)}\n\n`)) })
      return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
    }
    if (url.includes('/farms?limit=100'))
      return jsonResponse({ total: 1, items: [{ id: 7, owner_id: 'u', name: 'Kaveri Farm', description: null, latitude: 17.4, longitude: 78.5, area_hectares: 5, timezone: 'Asia/Kolkata', created_at: NOW, updated_at: NOW }] })
    if (url.endsWith('/twin')) return jsonResponse(TWIN)
    if (url.includes('/readings')) return jsonResponse({ sensor_id: 11, readings: [] })
    return jsonResponse({ status: 'ok', service: 'x', version: '1', timestamp: NOW })
  })
}

describe('twin page', () => {
  beforeEach(() => {
    fake.current!.reset()
    fake.current!.signInAs('grower@example.com')
  })

  it('loads lazily, shows farm context and merges live readings into the scene', async () => {
    mockApi()
    renderRoute('/twin')
    expect(await screen.findByRole('heading', { name: 'Kaveri Farm' })).toBeInTheDocument()
    expect(screen.getByText(/Sun 42° high · wind 2.4 m\/s · 2 simulated sensors/)).toBeInTheDocument()
    const canvas = screen.getByTestId('canvas')
    await waitFor(() => expect(canvas.dataset.sensorValues).toBe('27.5,23.1')) // live value replaced 24.4
  })

  it('toggles layers, with the optional solar layer off by default', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/twin')
    const layers = JSON.parse((await screen.findByTestId('canvas')).dataset.layers!)
    expect(layers).toMatchObject({ crops: true, sensors: true, moisture: false, solar: false })
    const panel = screen.getAllByRole('region', { name: 'Layers' })[0]!
    await user.click(within(panel).getByLabelText('Soil-moisture map'))
    await user.click(within(panel).getByLabelText('Crops'))
    expect(JSON.parse(screen.getByTestId('canvas').dataset.layers!)).toMatchObject({ moisture: true, crops: false })
  })

  it('selects objects from the keyboard list and labels simulated and schematic items', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/twin')
    const nav = (await screen.findAllByRole('navigation', { name: 'Twin objects' }))[0]!

    await user.click(within(nav).getByRole('button', { name: /Air temperature/ }))
    const details = screen.getByRole('region', { name: 'Sensor' })
    expect(within(details).getByText('23.1')).toBeInTheDocument()
    expect(within(details).getByText('Simulated')).toBeInTheDocument()
    expect(JSON.parse(screen.getByTestId('canvas').dataset.selection!)).toEqual({ kind: 'sensor', id: 12 })

    await user.click(within(nav).getByRole('button', { name: 'Farmhouse' }))
    expect(within(screen.getByRole('region', { name: 'Equipment' })).getByText(/Schematic placement/)).toBeInTheDocument()

    await user.click(within(nav).getByRole('button', { name: 'Water tank' }))
    const tank = screen.getByRole('region', { name: 'Equipment' })
    expect(within(tank).getByText('72 % (from sensors)')).toBeInTheDocument()
    expect(within(tank).queryByText(/Schematic placement/)).not.toBeInTheDocument() // data-backed

    await user.click(within(tank).getByRole('button', { name: 'Close details' }))
    expect(screen.queryByRole('region', { name: 'Equipment' })).not.toBeInTheDocument()
  })
})
