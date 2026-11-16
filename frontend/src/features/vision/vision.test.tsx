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
const grid = Array.from({ length: 7 }, (_, i) => Array.from({ length: 7 }, (_, j) => (i === 3 && j === 3 ? 1 : 0.1)))
const RESULT = {
  outcome: 'recognized', label: 'banana', subject_type: 'fruit', confidence: 0.9987, produce_probability: 0.999,
  candidates: [{ label: 'banana', subject_type: 'fruit', confidence: 0.9987 }, { label: 'lemon', subject_type: 'fruit', confidence: 0.0008 }],
  model_sees: [{ label: 'banana', confidence: 0.9987 }],
  quality: [{ key: 'sharpness', value: 40, status: 'ok', note: 'n' }, { key: 'brightness', value: 0.05, status: 'poor', note: 'too dark' }],
  explanation: { method: 'occlusion sensitivity', grid, crop: 'centre' },
  limitations: ['General ImageNet model (MobileNetV2), not trained on farm photos.'],
  image_size: [320, 280], detection_id: 5, saved: true, model: { id: 1, name: 'mobilenetv2-imagenet', version: 'onnx-zoo-12' },
}
const UNSUPPORTED = { ...RESULT, outcome: 'unsupported', label: null, subject_type: null, confidence: 0, explanation: { ...RESULT.explanation, grid: null }, model_sees: [{ label: 'Samoyed', confidence: 0.9 }], detection_id: null, saved: false }
const MODEL = {
  name: 'mobilenetv2-imagenet', version: 'onnx-zoo-12', available: true, framework: 'onnx', source: 'x', training_dataset: 'ImageNet-1k (ILSVRC 2012)',
  metrics: { top1_accuracy: 0.6948, top5_accuracy: 0.8926, dataset: 'ImageNet' }, supported: [{ label: 'banana', subject_type: 'fruit' }], min_confidence: 0.3,
}

function mockApi(result: object = RESULT) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/farms?limit=100')) return jsonResponse({ total: 1, items: [FARM] })
    if (url.includes('/farms/7/zones')) return jsonResponse({ total: 1, items: [ZONE] })
    if (url.endsWith('/vision/model')) return jsonResponse(MODEL)
    if (url.includes('/vision/recognitions') && method === 'POST') return jsonResponse(result, 201)
    if (url.includes('/vision/recognitions?')) return jsonResponse({ total: 0, items: [] })
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

const photo = () => new File([new Uint8Array([0xff, 0xd8, 0xff])], 'banana.jpg', { type: 'image/jpeg' })

describe('plant vision page', () => {
  it('uploads a photo as multipart with the zone and explains the result', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup()
    renderRoute('/vision')
    await user.upload(await screen.findByLabelText(/Photo of a fruit/), photo())
    await user.selectOptions(screen.getByLabelText(/Zone/), '1')
    await user.click(screen.getByRole('button', { name: 'Recognise' }))

    const result = await screen.findByRole('region', { name: 'Result' })
    expect(await within(result).findByText('banana', { selector: 'p' })).toBeInTheDocument()
    expect(within(result).getByText(/confidence 99.8 %/)).toBeInTheDocument()
    expect(within(result).getByText('poor')).toBeInTheDocument() // dark-image quality flag
    expect(within(result).getByText(/not trained on farm photos/)).toBeInTheDocument()
    expect(screen.getByText(/regions the prediction relied on most/)).toBeInTheDocument()

    const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/farms/7/vision/recognitions') && i?.method === 'POST')!
    const body = call[1]?.body as FormData
    expect(body).toBeInstanceOf(FormData)
    expect((body.get('file') as File).name).toBe('banana.jpg')
    expect(body.get('zone_id')).toBe('1')
    expect((call[1]?.headers as Record<string, string>)['Content-Type']).toBeUndefined()
  })

  it('says plainly when the photo is not a supported class', async () => {
    mockApi(UNSUPPORTED)
    const user = userEvent.setup()
    renderRoute('/vision')
    await user.upload(await screen.findByLabelText(/Photo of a fruit/), photo())
    await user.click(screen.getByRole('button', { name: 'Recognise' }))
    expect(await screen.findByText('Not a supported produce class')).toBeInTheDocument()
    expect(screen.getByText(/Samoyed/)).toBeInTheDocument()
    expect(screen.getByText('Not saved (nothing recognised).')).toBeInTheDocument()
  })

  it('rejects non-image files before uploading and shows the model card', async () => {
    const fetchSpy = mockApi()
    const user = userEvent.setup({ applyAccept: false })
    renderRoute('/vision')
    await user.upload(await screen.findByLabelText(/Photo of a fruit/), new File(['x'], 'notes.txt', { type: 'text/plain' }))
    expect(screen.getByText('Choose a JPEG, PNG or WebP image.')).toBeInTheDocument()
    expect(await screen.findByText(/69.5 % top-1/)).toBeInTheDocument()
    await waitFor(() => expect(fetchSpy.mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false))
  })
})
