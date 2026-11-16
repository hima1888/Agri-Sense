import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderRoute } from '@/test/render'

const HEALTH = { status: 'ok', service: 'agri-sense-api', version: '1.0.0', timestamp: '2026-11-13T10:00:00Z' }
const INFO = {
  name: 'AGRI-SENSE',
  version: '1.0.0',
  environment: 'development',
  api_prefix: '/api/v1',
  data_mode: { sensors: 'none', note: 'No sensors are connected yet.' },
  services: [
    { key: 'api', label: 'REST API', state: 'ok', detail: 'FastAPI is serving requests.' },
    { key: 'database', label: 'PostgreSQL (Supabase)', state: 'not_configured', detail: 'Phase 2.' },
  ],
}

function mockBackend(online: boolean) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (!online) throw new TypeError('Failed to fetch')
    const url = String(input)
    if (url.endsWith('/health')) return jsonResponse(HEALTH)
    if (url.endsWith('/system/info')) return jsonResponse(INFO)
    return jsonResponse({}, 404)
  })
}

describe('routing', () => {
  beforeEach(() => mockBackend(true))

  it('renders the landing page', async () => {
    renderRoute('/')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/sees/i)
    expect(screen.getByText('Recommend')).toBeInTheDocument()
  })

  it('has no developer roadmap pages', async () => {
    renderRoute('/modules')
    expect(await screen.findByText(/nothing grows here/i)).toBeInTheDocument()
  })

  it('renders 404 for unknown routes and unknown modules', async () => {
    renderRoute('/nope')
    expect(await screen.findByText(/nothing grows here/i)).toBeInTheDocument()
  })
})

describe('status page', () => {
  it('shows live backend data when the API is online', async () => {
    mockBackend(true)
    renderRoute('/status')
    expect(await screen.findByText('agri-sense-api')).toBeInTheDocument()
    expect(await screen.findByText('PostgreSQL (Supabase)')).toBeInTheDocument()
    expect(screen.getAllByText(/all systems operational/i).length).toBeGreaterThan(0)
  })

  it('shows a clear error when the API is unreachable', async () => {
    mockBackend(false)
    renderRoute('/status')
    expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent(/backend unreachable/i)
  })
})
