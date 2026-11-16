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
const alert = (id: number, severity: string, title: string, auto: boolean) => ({
  id, farm_id: 7, zone_id: 1, sensor_id: null, severity, category: auto ? 'irrigation' : 'system', status: 'open', title, message: 'Root-zone depletion 50 mm is past the 36.4 mm threshold.',
  triggered_at: NOW, acknowledged_at: null, resolved_at: null,
  context: auto ? { source: 'rule', rule: 'soil_dry', key: 'soil_dry:zone:1', rule_description: 'Root zone past the stress threshold (FAO-56 water balance)' } : null,
})
const SETTINGS = {
  rules: [{ rule: 'soil_dry', description: 'Root zone past the stress threshold', enabled: true }, { rule: 'heat_forecast', description: 'Extreme heat forecast', enabled: true }],
  thresholds: { heat_c: 35, wind_ms: 12 }, defaults: { heat_c: 35, wind_ms: 12 },
}

function stream(events: string[]) {
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      c.enqueue(new TextEncoder().encode('event: snapshot\ndata: {"farm_id":7,"sensors":[]}\n\n'))
      for (const e of events) c.enqueue(new TextEncoder().encode(e))
    },
  })
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

function mockApi(events: string[] = []) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/stream')) return stream(events)
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/alerts?')) return jsonResponse({ total: 2, items: [alert(1, 'critical', 'North Field: soil at wilting point', true), alert(2, 'info', 'Manual note', false)] })
    if (url.endsWith('/alerts/evaluate')) return jsonResponse({ raised: 1, updated: 0, resolved: 2, conditions: [{ rule: 'soil_dry' }] })
    if (url.endsWith('/alert-settings') && method === 'PUT') return jsonResponse(SETTINGS)
    if (url.endsWith('/alert-settings')) return jsonResponse(SETTINGS)
    if (url.includes('/acknowledge')) return jsonResponse({ ...alert(1, 'critical', 'x', true), status: 'acknowledged' })
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('alerts page', () => {
  it('lists automatic and manual alerts with the rule, and acknowledges', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/alerts')
    const row = await screen.findByRole('listitem', { name: 'North Field: soil at wilting point' })
    expect(within(row).getByText('critical')).toBeInTheDocument()
    expect(within(row).getByText(/automatic/)).toBeInTheDocument()
    expect(within(row).getByText(/Rule: Root zone past the stress threshold/)).toBeInTheDocument()
    expect(within(screen.getByRole('listitem', { name: 'Manual note' })).getByText(/manual/)).toBeInTheDocument()
    await user.click(within(row).getByRole('button', { name: 'Acknowledge' }))
    await waitFor(() => expect(fetchSpy.mock.calls.some(([u, i]) => String(u).endsWith('/alerts/1/acknowledge') && i?.method === 'POST')).toBe(true))
  })

  it('checks now and reports the outcome', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/alerts')
    await user.click(await screen.findByRole('button', { name: 'Check now' }))
    expect(await screen.findByText(/1 condition\(s\) true · 1 raised · 2 resolved/)).toBeInTheDocument()
  })

  it('shows an alert pushed over the live stream', async () => {
    const event = 'event: alert\ndata: {"type":"raised","alert":{"id":9,"severity":"warning","category":"weather","status":"open","title":"Heat forecast: up to 38 °C","message":"m","zone_id":null}}\n\n'
    mockApi([event])
    renderRoute('/alerts')
    const toast = await screen.findByText('Heat forecast: up to 38 °C')
    expect(within(toast.closest('[role="status"]') as HTMLElement).getByText('raised')).toBeInTheDocument()
  })

  it('saves settings: disabled rules and changed thresholds only', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/alerts')
    const form = await screen.findByRole('form', { name: 'Alert settings' })
    await user.click(within(form).getByLabelText(/Extreme heat forecast/))
    const wind = within(form).getByLabelText(/Strong wind/)
    await user.clear(wind)
    await user.type(wind, '15')
    await user.click(within(form).getByRole('button', { name: 'Save settings' }))
    await waitFor(() => {
      const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/alert-settings') && i?.method === 'PUT')
      expect(call && JSON.parse(String(call[1]?.body))).toEqual({ disabled_rules: ['heat_forecast'], thresholds: { wind_ms: 15 } })
    })
  })
})
