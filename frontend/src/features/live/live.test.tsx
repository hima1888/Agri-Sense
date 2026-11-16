import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase } from '@/test/fake-supabase'
import { jsonResponse, renderRoute } from '@/test/render'
import { STALL_TIMEOUT_MS, streamReducer, type StreamState } from './use-farm-stream'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof createFakeSupabase> | null }))
vi.mock('@/lib/supabase', async () => {
  const { createFakeSupabase } = await import('@/test/fake-supabase')
  fake.current = createFakeSupabase()
  return { supabase: fake.current.supabase }
})

const NOW = new Date().toISOString()
const sensor = (id: number, sensor_type: string, unit: string, value: number) => ({
  id,
  name: `${sensor_type} · North Field`,
  zone_id: 10,
  sensor_type,
  unit,
  source: 'simulated',
  is_simulated: true,
  status: 'active',
  min_valid: 0,
  max_valid: 100,
  latest: { recorded_at: NOW, value, quality: 'good' },
})

const SNAPSHOT = { farm_id: 1, sensors: [sensor(1, 'soil_moisture', '%', 26.4), sensor(2, 'temperature', '°C', 24.25)] }

/** A text/event-stream body we can push events into while the page is mounted. */
function sseResponse() {
  const encoder = new TextEncoder()
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({ start: (c) => void (controller = c) })
  const send = (text: string) => controller.enqueue(encoder.encode(text))
  return { response: new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }), send }
}

describe('live sensors page', () => {
  beforeEach(() => {
    fake.current!.reset()
    fake.current!.signInAs('grower@example.com')
  })

  it('streams a snapshot then live updates, labelled as simulated', async () => {
    const stream = sseResponse()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/stream')) return stream.response
      if (url.endsWith('/farms?limit=100'))
        return jsonResponse({ total: 1, items: [{ id: 1, name: 'North Farm', latitude: 17.4, longitude: 78.5, timezone: 'Asia/Kolkata' }] })
      if (url.includes('/zones')) return jsonResponse({ total: 1, items: [{ id: 10, farm_id: 1, name: 'North Field', zone_type: 'field' }] })
      if (url.endsWith('/simulator'))
        return jsonResponse({ enabled: true, running: true, interval_seconds: 10, last_tick_at: NOW, last_error: null, simulated_sensors: 2, live_connections: 1, note: '' })
      if (url.includes('/readings')) return jsonResponse({ sensor_id: 1, readings: [] })
      return jsonResponse({ status: 'ok', service: 'x', version: '1', timestamp: NOW })
    })

    renderRoute('/live')
    stream.send('retry: 5000\n\n')
    stream.send(`event: snapshot\ndata: ${JSON.stringify(SNAPSHOT)}\n\n`)

    expect(await screen.findByRole('heading', { name: 'North Farm' })).toBeInTheDocument()
    expect(await screen.findByText('26.4')).toBeInTheDocument()
    expect(screen.getByText('24.3')).toBeInTheDocument() // 1 decimal for temperature
    expect(screen.getAllByText('Simulated')).toHaveLength(2)
    expect(screen.getByText(/No physical hardware is connected/i)).toBeInTheDocument()
    expect(within(screen.getAllByRole('status')[0]!.parentElement!).getByText('Live')).toBeInTheDocument()

    const later = new Date(Date.now() + 10_000).toISOString()
    stream.send(`id: 3\nevent: readings\ndata: ${JSON.stringify({ farm_id: 1, readings: [{ sensor_id: 1, recorded_at: later, value: 31.9, quality: 'good', is_simulated: true }] })}\n\n`)
    expect(await screen.findByText('31.9')).toBeInTheDocument()

    // The stream is opened with the bearer token in a header, never in the URL.
    const call = fetchSpy.mock.calls.find(([u]) => String(u).includes('/stream'))!
    expect(String(call[0])).not.toContain('token')
    expect((call[1]?.headers as Record<string, string>).Authorization).toBe('Bearer token-for-grower@example.com')
  })
})

describe('stream watchdog', () => {
  beforeEach(() => {
    fake.current!.reset()
    fake.current!.signInAs('grower@example.com')
  })

  it('drops a silent connection and reconnects with a fresh snapshot', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const streams: ReturnType<typeof sseResponse>[] = []
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
        const url = String(input)
        if (url.includes('/stream')) {
          const s = sseResponse()
          // A dead proxy: the request is accepted, then nothing ever arrives and the body never closes.
          streams.push(s)
          s.send(`event: snapshot
data: ${JSON.stringify(SNAPSHOT)}

`)
          return s.response
        }
        if (url.endsWith('/farms?limit=100'))
          return jsonResponse({ total: 1, items: [{ id: 1, name: 'North Farm', latitude: 17.4, longitude: 78.5, timezone: 'UTC' }] })
        if (url.includes('/zones')) return jsonResponse({ total: 0, items: [] })
        if (url.includes('/readings')) return jsonResponse({ sensor_id: 1, readings: [] })
        return jsonResponse({ enabled: true, running: true, interval_seconds: 10, last_tick_at: null, last_error: null, simulated_sensors: 2, live_connections: 1, note: '' })
      })
      renderRoute('/live')
      expect(await screen.findByText('26.4')).toBeInTheDocument()
      expect(streams).toHaveLength(1)
      await vi.advanceTimersByTimeAsync(STALL_TIMEOUT_MS + 6_000) // silence -> abort -> backoff -> reconnect
      await vi.waitFor(() => expect(streams.length).toBeGreaterThanOrEqual(2))
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('streamReducer', () => {
  const base: StreamState = { status: 'connecting', sensors: [], history: {}, alertEvents: [], lastEventAt: null, error: null }

  it('keeps the 20 most recent alert events, newest first', () => {
    let s = base
    for (let i = 1; i <= 25; i++) {
      s = streamReducer(s, { type: 'alert', event: { type: 'raised', alert: { id: i, severity: 'warning', category: 'soil', status: 'open', title: `A${i}`, message: '', zone_id: null }, receivedAt: i } })
    }
    expect(s.alertEvents).toHaveLength(20)
    expect(s.alertEvents[0]!.alert.id).toBe(25)
  })

  it('keeps history ordered, de-duplicated and updates latest values', () => {
    let s = streamReducer(base, { type: 'snapshot', sensors: [sensor(1, 'humidity', '%', 50)] as never })
    s = streamReducer(s, {
      type: 'readings',
      items: [
        { sensor_id: 1, recorded_at: '2030-01-01T00:00:20Z', value: 52, quality: 'good' },
        { sensor_id: 1, recorded_at: '2030-01-01T00:00:10Z', value: 51, quality: 'suspect' },
      ],
    })
    s = streamReducer(s, { type: 'readings', items: [{ sensor_id: 1, recorded_at: '2030-01-01T00:00:20Z', value: 52, quality: 'good' }] })
    const values = s.history[1]!.map((p) => p.v)
    expect(values.slice(-2)).toEqual([51, 52])
    expect(values.filter((v) => v === 52)).toHaveLength(1)
    expect(s.sensors[0]!.latest?.value).toBe(52)
    expect(s.status).toBe('live')
  })
})
