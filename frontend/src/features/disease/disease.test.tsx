import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
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
const ZONE = { id: 1, farm_id: 7, name: 'North Field', zone_type: 'field', area_hectares: 4, irrigation_method: 'drip' }
const MODELS = {
  models: [
    { key: 'crop_vit', name: 'crop-leaf-diseases-vit', available: true, architecture: 'ViT-tiny', used_for: ['corn', 'potato', 'rice', 'wheat'], published_accuracy: '98 % self-reported', licence: 'MIT', source: 's', limitations: [] },
    { key: 'plantvillage', name: 'plantvillage-mobilenet-v2', available: true, architecture: 'MobileNetV2', used_for: ['tomato'], published_accuracy: 'Conflicting', licence: 'other', source: 's', limitations: [] },
  ],
  supported_crops: { corn: 'crop_vit', tomato: 'plantvillage' },
  thresholds: { min_top1: 0.6, min_margin: 0.2 },
  limitations: [],
}
const base = {
  crop: 'tomato', crop_source: 'request', model: { key: 'plantvillage', name: 'plantvillage-mobilenet-v2', version: 'hf-onnx17', id: 2 },
  disease: 'Early blight', is_healthy: false, margin: 0.78, quality: [], image_size: [256, 256],
  checks: [{ rule: 'crop_supported', passed: true, detail: 'tomato -> plantvillage-mobilenet-v2' }, { rule: 'confidence', passed: true, detail: '83.9 %' }],
  candidates: [{ label: 'Tomato: Early blight', crop: 'tomato', disease: 'Early blight', is_healthy: false, confidence: 0.8394 }],
  limitations: ['Screening aid only, not a diagnosis.'],
}
const KNOWLEDGE = {
  key: 'early_blight', name: 'Early blight', pathogen: 'Alternaria solani', pathogen_type: 'fungus', crops: ['potato', 'tomato'],
  what: 'A common fungal disease.', symptoms: ['Target-pattern spots'], causes: 'Survives on residue.', conditions: 'Warm, wet then dry.',
  spread: 'Wind and rain splash.', management: ['Remove infected lower leaves'], prevention: ['Rotate crops'], sustainable: ['Mulching'],
  monitor: ['Lower leaves weekly'], seek_advice: 'If lesions reach the upper canopy.', source: 'Compiled from references. Not reviewed.', reviewed: false,
}
const POSSIBLE = { ...base, outcome: 'possible_disease', label: 'Tomato: Early blight', confidence: 0.8394, affected_area_pct: 16.7, severity: 'moderate', reason: 'Passed all checks.', detection_id: 4, saved: true, knowledge_key: 'early_blight', knowledge: KNOWLEDGE, healthy_guidance: null }
const UNCERTAIN = { ...POSSIBLE, outcome: 'uncertain', reason: 'Uncertain: confidence or margin too low.', knowledge: null, knowledge_key: null }
const REFUSED = {
  ...base, outcome: 'cannot_identify', label: null, disease: null, is_healthy: null, confidence: 0.99, affected_area_pct: null, severity: null,
  reason: 'Cannot reliably identify: the model\'s top answer is a potato class, not tomato.', detection_id: null, saved: false,
  checks: [{ rule: 'model_agrees_on_crop', passed: false, detail: 'model top-1: Potato: Early blight 99.9%' }],
}

function mockApi(result: object) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/zones')) return jsonResponse({ total: 1, items: [ZONE] })
    if (url.endsWith('/vision/disease/models')) return jsonResponse(MODELS)
    if (url.includes('/disease-checks') && init?.method === 'POST') return jsonResponse(result, 201)
    if (url.includes('/disease-checks?')) return jsonResponse({ total: 0, items: [] })
    return jsonResponse({ status: 'ok' })
  })
}

beforeAll(() => {
  URL.createObjectURL = vi.fn(() => 'blob:preview')
  URL.revokeObjectURL = vi.fn()
})
beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
})
const leaf = () => new File([new Uint8Array([0xff, 0xd8, 0xff])], 'leaf.jpg', { type: 'image/jpeg' })

describe('leaf disease check', () => {
  it('requires a crop or zone, sends crop and zone, and explains a possible disease', async () => {
    const fetchSpy = mockApi(POSSIBLE)
    const user = userEvent.setup()
    renderRoute('/vision?tab=disease')
    expect(await screen.findByText(/not a diagnosis/)).toBeInTheDocument()
    await user.upload(screen.getByLabelText('Photo of one leaf'), leaf())
    await user.click(screen.getByRole('button', { name: 'Check leaf' }))
    expect(screen.getByText('Choose the crop, or a zone with a crop planted.')).toBeInTheDocument()

    await user.selectOptions(await screen.findByLabelText('Crop'), 'tomato')
    await user.selectOptions(screen.getByLabelText('Zone'), '1')
    await user.click(screen.getByRole('button', { name: 'Check leaf' }))
    const result = await screen.findByRole('region', { name: 'Disease result' })
    expect(within(result).getByText('Possible disease')).toBeInTheDocument()
    expect(within(result).getByText('Tomato: Early blight', { selector: 'p' })).toBeInTheDocument()
    expect(within(result).getByText(/Model: plantvillage-mobilenet-v2/)).toBeInTheDocument()
    expect(within(result).getByText(/model confidence 83.9 %/)).toBeInTheDocument()
    expect(within(result).getByText(/colour heuristic/)).toBeInTheDocument()
    // Guidance comes from the API's structured knowledge entry, section by section.
    const about = within(result).getByRole('region', { name: 'About Early blight' })
    for (const h of ['What is this?', 'Symptoms', 'Why it occurs', 'Environmental conditions', 'How it spreads', 'How to manage it', 'Prevention', 'Sustainable practices', 'What to monitor', 'When to seek expert advice']) {
      expect(within(about).getByText(h)).toBeInTheDocument()
    }
    expect(within(about).getByText('Remove infected lower leaves')).toBeInTheDocument()
    expect(within(about).getByText('not agronomist-reviewed')).toBeInTheDocument()

    const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/farms/7/vision/disease-checks') && i?.method === 'POST')!
    const body = call[1]?.body as FormData
    expect(body.get('crop')).toBe('tomato')
    expect(body.get('zone_id')).toBe('1')
  })

  it('shows a refusal with the failed check and no diagnosis', async () => {
    mockApi(REFUSED)
    const user = userEvent.setup()
    renderRoute('/vision?tab=disease')
    await user.upload(await screen.findByLabelText('Photo of one leaf'), leaf())
    await user.selectOptions(await screen.findByLabelText('Crop'), 'tomato')
    await user.click(screen.getByRole('button', { name: 'Check leaf' }))
    const result = await screen.findByRole('region', { name: 'Disease result' })
    expect(within(result).getByText('Cannot reliably identify')).toBeInTheDocument()
    expect(within(result).getByText(/top answer is a potato class/)).toBeInTheDocument()
    expect(within(result).getByText('failed:', { exact: false })).toBeInTheDocument()
    expect(within(result).getByText('Not saved.')).toBeInTheDocument()
    expect(within(result).queryByText('Possible disease')).not.toBeInTheDocument()
  })

  it('shows no disease guidance for an uncertain result', async () => {
    mockApi(UNCERTAIN)
    const user = userEvent.setup()
    renderRoute('/vision?tab=disease')
    await user.upload(await screen.findByLabelText('Photo of one leaf'), leaf())
    await user.selectOptions(await screen.findByLabelText('Crop'), 'tomato')
    await user.click(screen.getByRole('button', { name: 'Check leaf' }))
    const result = await screen.findByRole('region', { name: 'Disease result' })
    expect(within(result).getByText(/No disease guidance is shown because the result is uncertain/)).toBeInTheDocument()
    expect(within(result).queryByRole('region', { name: /About/ })).not.toBeInTheDocument()
  })

  it('switches between the produce and disease tabs', async () => {
    mockApi(POSSIBLE)
    const user = userEvent.setup()
    renderRoute('/vision')
    expect(await screen.findByLabelText(/Photo of a fruit/)).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Leaf disease check' }))
    await waitFor(() => expect(screen.getByLabelText('Photo of one leaf')).toBeInTheDocument())
    expect(await screen.findByText(/Conflicting/)).toBeInTheDocument()
  })
})
