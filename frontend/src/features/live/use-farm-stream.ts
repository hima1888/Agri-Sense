import { useEffect, useReducer } from 'react'
import { apiGet, apiUrl, getAccessToken } from '@/lib/api-client'
import { readSse, SseHttpError, SseParser } from '@/lib/sse'
import { AlertEventSchema, ReadingsEventSchema, SeriesSchema, SnapshotSchema, type StreamSensor } from './schemas'

export interface Point {
  t: number
  v: number
  q: 'good' | 'suspect' | 'bad'
}

export type StreamStatus = 'connecting' | 'live' | 'reconnecting' | 'unauthorized' | 'closed'

/** An automatic-alert change pushed by the server (Phase 17). */
export interface AlertEvent {
  type: 'raised' | 'escalated' | 'resolved'
  alert: { id: number; severity: string; category: string; status: string; title: string; message: string; zone_id: number | null }
  receivedAt: number
}

export interface StreamState {
  status: StreamStatus
  sensors: StreamSensor[]
  history: Record<number, Point[]>
  alertEvents: AlertEvent[]
  lastEventAt: number | null
  error: string | null
}

const HISTORY_LIMIT = 240
/** The server pings every 10 s; silence this long means the connection is dead even if TCP never said so. */
export const STALL_TIMEOUT_MS = 25_000
const initial: StreamState = { status: 'connecting', sensors: [], history: {}, alertEvents: [], lastEventAt: null, error: null }

type Action =
  | { type: 'status'; status: StreamStatus; error?: string | null }
  | { type: 'snapshot'; sensors: StreamSensor[] }
  | { type: 'history'; sensorId: number; points: Point[] }
  | { type: 'readings'; items: { sensor_id: number; recorded_at: string; value: number; quality: Point['q'] }[] }
  | { type: 'heartbeat' }
  | { type: 'alert'; event: AlertEvent }

function mergePoints(existing: Point[], incoming: Point[]): Point[] {
  const byTime = new Map(existing.map((p) => [p.t, p]))
  for (const p of incoming) byTime.set(p.t, p)
  return [...byTime.values()].sort((a, b) => a.t - b.t).slice(-HISTORY_LIMIT)
}

export function streamReducer(state: StreamState, action: Action): StreamState {
  switch (action.type) {
    case 'status':
      return { ...state, status: action.status, error: action.error ?? null }
    case 'heartbeat':
      return { ...state, lastEventAt: Date.now() }
    case 'alert':
      return { ...state, alertEvents: [action.event, ...state.alertEvents].slice(0, 20), lastEventAt: Date.now() }
    case 'snapshot': {
      const history = { ...state.history }
      for (const s of action.sensors) {
        if (s.latest) {
          const p: Point = { t: Date.parse(s.latest.recorded_at), v: s.latest.value, q: s.latest.quality }
          history[s.id] = mergePoints(history[s.id] ?? [], [p])
        }
      }
      return { ...state, status: 'live', sensors: action.sensors, history, lastEventAt: Date.now(), error: null }
    }
    case 'history':
      return { ...state, history: { ...state.history, [action.sensorId]: mergePoints(state.history[action.sensorId] ?? [], action.points) } }
    case 'readings': {
      const history = { ...state.history }
      const latest = new Map<number, (typeof action.items)[number]>()
      for (const r of action.items) {
        history[r.sensor_id] = mergePoints(history[r.sensor_id] ?? [], [{ t: Date.parse(r.recorded_at), v: r.value, q: r.quality }])
        latest.set(r.sensor_id, r)
      }
      const sensors = state.sensors.map((s) => {
        const r = latest.get(s.id)
        return r ? { ...s, latest: { recorded_at: r.recorded_at, value: r.value, quality: r.quality } } : s
      })
      return { ...state, sensors, history, lastEventAt: Date.now() }
    }
  }
}

/**
 * Live readings for one farm: a snapshot, the last 2 h of history for sparklines,
 * then streamed updates. Reconnects with backoff; a fresh snapshot resynchronises.
 */
export function useFarmStream(farmId: number | null, historyHours = 2): StreamState {
  const [state, dispatch] = useReducer(streamReducer, initial)

  useEffect(() => {
    if (farmId == null) return
    const abort = new AbortController()
    let attempt = 0

    async function loadHistory(sensors: StreamSensor[]) {
      if (historyHours <= 0) return // the page does not draw sparklines
      const start = new Date(Date.now() - historyHours * 3_600_000).toISOString()
      await Promise.all(
        sensors.map(async (s) => {
          try {
            const series = await apiGet(
              `/sensors/${s.id}/readings?start=${encodeURIComponent(start)}&limit=${HISTORY_LIMIT}`,
              SeriesSchema,
              { signal: abort.signal },
            )
            const points = series.readings.map((r) => ({ t: Date.parse(r.recorded_at), v: r.value, q: r.quality }))
            if (!abort.signal.aborted) dispatch({ type: 'history', sensorId: s.id, points })
          } catch {
            /* sparkline history is best-effort; live values still arrive */
          }
        }),
      )
    }

    const parser = (touch: () => void) =>
      new SseParser(
        (msg) => {
          touch()
          try {
            if (msg.event === 'snapshot') {
              const snap = SnapshotSchema.parse(JSON.parse(msg.data))
              attempt = 0
              dispatch({ type: 'snapshot', sensors: snap.sensors })
              void loadHistory(snap.sensors)
            } else if (msg.event === 'readings') {
              dispatch({ type: 'readings', items: ReadingsEventSchema.parse(JSON.parse(msg.data)).readings })
            } else if (msg.event === 'alert') {
              const e = AlertEventSchema.parse(JSON.parse(msg.data))
              dispatch({ type: 'alert', event: { ...e, receivedAt: Date.now() } })
            }
          } catch {
            /* ignore a malformed event rather than tearing down the stream */
          }
        },
        () => {
          touch()
          dispatch({ type: 'heartbeat' })
        },
      )

    async function run() {
      dispatch({ type: 'status', status: 'connecting' })
      while (!abort.signal.aborted) {
        // One controller per connection: aborted by unmount OR by the stall watchdog.
        const conn = new AbortController()
        const stop = () => conn.abort()
        abort.signal.addEventListener('abort', stop)
        let lastActivity = Date.now()
        const p = parser(() => (lastActivity = Date.now()))
        const watchdog = setInterval(() => {
          if (Date.now() - lastActivity > STALL_TIMEOUT_MS) conn.abort()
        }, 2_500)
        try {
          const token = await getAccessToken()
          await readSse(apiUrl(`/farms/${farmId}/stream`), { headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: conn.signal }, p)
        } catch (err) {
          if (abort.signal.aborted) return
          if (err instanceof SseHttpError && (err.status === 401 || err.status === 404)) {
            dispatch({ type: 'status', status: 'unauthorized', error: err.status === 401 ? 'Session expired. Sign in again.' : 'Farm not found.' })
            return
          }
        }
        finally {
          clearInterval(watchdog)
          abort.signal.removeEventListener('abort', stop)
        }
        if (abort.signal.aborted) return
        dispatch({ type: 'status', status: 'reconnecting' })
        const delay = Math.min(15_000, (p.retryMs ?? 1_000) * 2 ** attempt++)
        await new Promise((r) => setTimeout(r, delay))
      }
    }
    void run()
    return () => abort.abort()
  }, [farmId, historyHours])

  return farmId == null ? { ...initial, status: 'closed' } : state
}
