import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase } from '@/test/fake-supabase'
import { jsonResponse, renderRoute } from '@/test/render'
import { healthStyle } from '@/features/twin/layout'
import type { TwinZone } from '@/features/twin/schemas'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof createFakeSupabase> | null }))
vi.mock('@/lib/supabase', async () => {
  const { createFakeSupabase } = await import('@/test/fake-supabase')
  fake.current = createFakeSupabase()
  return { supabase: fake.current.supabase }
})

const NOW = new Date().toISOString()
const FARM = { id: 7, owner_id: 'u', name: 'Kaveri Farm', description: null, latitude: 17.4, longitude: 78.5, area_hectares: 12, timezone: 'Asia/Kolkata', created_at: NOW, updated_at: NOW }
const st = (key: string, name: string, a: number, b: number, fao: string, approx = false) => ({ key, name, start_day: a, end_day: b, fao_stage: fao, approximate_boundary: approx, description: `${name} description` })
const GROWTH = {
  crop: 'Tomato', crop_key: 'tomato', crop_id: 4, cycle_id: 9, planted_on: '2026-09-27', cycle_days: 110, cycle_days_source: 'crop catalogue',
  fao56: { initial: 30, development: 40, mid_season: 40, late_season: 25, region: 'California, USA' },
  stages: [
    st('seed', 'Seed', 0, 0, 'sowing'), st('germination', 'Germination', 1, 10, 'initial', true), st('seedling', 'Seedling', 11, 24, 'initial', true),
    st('vegetative', 'Vegetative', 25, 57, 'development'), st('flowering', 'Flowering', 58, 68, 'mid-season', true), st('formation', 'Fruiting', 69, 89, 'mid-season', true),
    st('maturity', 'Maturity', 90, 110, 'late season'), st('harvest', 'Harvest', 110, 110, 'end of season'),
  ],
  current: { day: 50, stage_key: 'vegetative', progress: 0.455, note: null },
  method: 'FAO-56 Table 11 stage proportions scaled to the cycle length.',
  limitations: ['Calendar estimates.'],
}
const CROPS = { total: 2, items: [{ id: 4, common_name: 'Tomato', category: 'vegetable', typical_cycle_days: 110 }, { id: 5, common_name: 'Mango', category: 'fruit', typical_cycle_days: null }] }

function mockApi(growth: object | { error: string }) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/crops?limit=100')) return jsonResponse(CROPS)
    if (url.includes('/twin')) return jsonResponse({ error: { code: 'not_found', message: 'n/a', details: null } }, 404)
    if (url.includes('/growth')) {
      return 'error' in growth ? jsonResponse({ error: { code: 'invalid', message: growth.error, details: null } }, 422) : jsonResponse(growth)
    }
    return jsonResponse({ status: 'ok' })
  })
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})
afterEach(() => vi.useRealTimers())

describe('crop growth', () => {
  it('shows the stages from the API, starts at today, and plays through them', async () => {
    const spy = mockApi(GROWTH)
    renderRoute('/growth?pick=cycle:9')
    const stages = await screen.findByRole('list', { name: 'Growth stages' })
    expect(within(stages).getAllByRole('button')).toHaveLength(8)
    expect(within(stages).getByText('today')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Tomato at the vegetative stage' })).toBeInTheDocument()
    expect(screen.getByText(/Days 25–57/)).toBeInTheDocument()
    expect(screen.getByText(/today is day 50/)).toBeInTheDocument()
    expect(spy.mock.calls.some(([u]) => String(u).includes('/crop-cycles/9/growth'))).toBe(true)

    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await user.click(screen.getByRole('button', { name: 'Play growth' }))
    await act(async () => {
      vi.advanceTimersByTime(33 * 60 + 50) // vegetative lasts 33 days -> 1.98 s on screen
    })
    expect(screen.getByRole('img', { name: 'Tomato at the flowering stage' })).toBeInTheDocument()
    await user.click(within(stages).getByRole('button', { name: /Harvest/ }))
    expect(screen.getByRole('img', { name: 'Tomato at the harvest stage' })).toBeInTheDocument()
  })

  it('explains an unsupported crop instead of drawing anything', async () => {
    mockApi({ error: 'Mango is perennial; the FAO-56 annual stage model does not apply. Not modelled.' })
    renderRoute('/growth?pick=crop:5')
    expect(await screen.findByText(/Mango is perennial/)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Growth stages' })).not.toBeInTheDocument()
  })
})

describe('twin health style', () => {
  const zone = (health: TwinZone['health']) => ({ health }) as TwinZone
  it('tints a zone only from its saved disease check', () => {
    expect(healthStyle(zone(null))).toEqual({ leaf: null, outline: null, label: '' })
    const h = { detection_id: 1, label: 'Tomato: Late blight', confidence: 0.9, severity: 'high', knowledge_key: 'late_blight', detected_at: NOW }
    expect(healthStyle(zone({ ...h, state: 'disease' })).label).toBe(' · possible disease')
    expect(healthStyle(zone({ ...h, state: 'uncertain' })).leaf).toBeNull()
    expect(healthStyle(zone({ ...h, state: 'healthy' })).outline).toBeNull()
  })
})
