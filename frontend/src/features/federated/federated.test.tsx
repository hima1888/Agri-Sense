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
const ZONE = { id: 1, farm_id: 7, name: 'North Field', zone_type: 'field', area_hectares: 2, irrigation_method: 'drip' }
const RUN = {
  id: 4, status: 'completed', rounds: 20, started_at: NOW, completed_at: NOW, clients: 2, participated: true, uses_simulated_data: true,
  overall: { mae_persistence: 0.444, mae_local_only: 0.47, mae_federated: 0.497, test_samples: 24 },
  your_metrics: { train_samples: 50, test_samples: 12, mae_persistence: 0.4, mae_local_only: 0.45, mae_federated: 0.48 },
  history: [{ round: 1, test_mse: 0.4 }], explanation: [{ feature: 'hour_sin', weight: -0.83 }, { feature: 'moisture', weight: -0.45 }],
}
const VIEW = (enrolled: boolean, runs = [RUN]) => ({
  farm_id: 7, local_samples: 63, min_samples: 30, uses_simulated_data: true,
  enrollment: enrolled ? { status: 'active', client_key: 'fc_x', enrolled_at: NOW, last_seen_at: NOW } : null,
  shared: 'model weights, sample count and local error metrics only', not_shared: 'sensor readings, features, zone names, locations',
  runs, limitations: ['Plain FedAvg is not a formal privacy guarantee.'],
})
const FORECAST = {
  status: 'forecast', model_version: 'run-4', moisture_now_pct: 24.1, predicted_change_6h_pct_points: -0.6, predicted_moisture_6h_pct: 23.5,
  expected_error_pct_points: 0.497, persistence_error_pct_points: 0.444, beats_baseline: false, uses_simulated_data: true,
  advice: 'On held-out data this model is NOT more accurate than assuming moisture stays the same. Do not use it for decisions.',
}

function mockApi(view: object) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/zones')) return jsonResponse({ total: 1, items: [ZONE] })
    if (url.endsWith('/farms/7/federated')) return jsonResponse(view)
    if (url.endsWith('/federated/enroll') && init?.method === 'POST') return jsonResponse({ farm_id: 7, status: 'active' })
    if (url.endsWith('/federated/forecast')) return jsonResponse(FORECAST)
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})

describe('federated learning page', () => {
  it('states what is shared, and that the model does not beat the baseline', async () => {
    mockApi(VIEW(true))
    renderRoute('/federated')
    const part = await screen.findByRole('region', { name: 'Participation' })
    expect(within(part).getByText(/model weights, sample count and local error metrics only/)).toBeInTheDocument()
    expect(within(part).getByText(/sensor readings, features, zone names, locations/)).toBeInTheDocument()
    expect(within(part).getByText('SIMULATED')).toBeInTheDocument()
    const latest = screen.getByRole('region', { name: 'Latest model · run 4' })
    expect(within(latest).getByText(/NOT more accurate than assuming no change/)).toBeInTheDocument()
    expect(within(latest).getByText(/Time of day \(sin\): -0.83/)).toBeInTheDocument()
    const fc = screen.getByRole('region', { name: '6-hour moisture forecast' })
    expect(await within(fc).findByText(/24.1 % now → 23.5 % in 6 h/)).toBeInTheDocument()
    expect(within(fc).getByText(/Do not use it for decisions/)).toBeInTheDocument()
  })

  it('joins the federation', async () => {
    const fetchSpy = mockApi(VIEW(false, []))
    const user = userEvent.setup()
    renderRoute('/federated')
    expect(await screen.findByText('not enrolled')).toBeInTheDocument()
    expect(screen.getByText(/No federated run has completed yet/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Join federation' }))
    await waitFor(() => expect(fetchSpy.mock.calls.some(([u, i]) => String(u).endsWith('/farms/7/federated/enroll') && i?.method === 'POST')).toBe(true))
  })
})
