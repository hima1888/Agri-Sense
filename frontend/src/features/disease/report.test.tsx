import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase } from '@/test/fake-supabase'
import { jsonResponse, renderRoute } from '@/test/render'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof createFakeSupabase> | null }))
vi.mock('@/lib/supabase', async () => {
  const { createFakeSupabase } = await import('@/test/fake-supabase')
  fake.current = createFakeSupabase()
  return { supabase: fake.current.supabase }
})

const RECORD = {
  id: 12, farm_id: 7, zone_id: 1, disease_label: 'Tomato: Late blight', is_healthy: false, confidence: 0.6235, severity: 'moderate',
  affected_area_pct: 18.2, model_version_id: 2, detected_at: '2026-11-16T10:00:00Z', knowledge_key: 'late_blight',
  top_k: [{ label: 'Tomato: Late blight', confidence: 0.6235 }, { label: 'Potato: Late blight', confidence: 0.2073 }],
  explanation: {
    outcome: 'possible_disease', crop: 'tomato', crop_source: 'request', margin: 0.4163,
    model: { key: 'plantvillage', name: 'plantvillage-mobilenet-v2', version: 'hf-onnx17' },
    checks: [{ rule: 'confidence', passed: true, detail: '62.4 % (need >= 60 %)' }],
    reason: 'Passed all checks.', limitations: ['Screening aid only, not a diagnosis.'],
  },
}
const KNOWLEDGE = {
  key: 'late_blight', name: 'Late blight', pathogen: 'Phytophthora infestans', pathogen_type: 'oomycete', crops: ['potato', 'tomato'],
  what: 'A fast, destructive disease.', symptoms: ['Dark water-soaked lesions'], causes: 'Infected tubers.', conditions: 'Cool and humid.',
  spread: 'Wind and rain.', management: ['Destroy infected plants'], prevention: ['Certified seed'], sustainable: ['Forecast-based spraying'],
  monitor: ['Blight weather'], seek_advice: 'Immediately.', source: 'Compiled from references. Not reviewed.', reviewed: false,
}

beforeEach(() => {
  fake.current!.reset()
  fake.current!.signInAs('grower@example.com')
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/vision/disease-checks/12')) return jsonResponse(RECORD)
    if (url.endsWith('/knowledge/diseases/late_blight')) return jsonResponse(KNOWLEDGE)
    if (url.endsWith('/image')) return new Response(new Blob([new Uint8Array([0xff, 0xd8])], { type: 'image/jpeg' }))
    return jsonResponse({ status: 'ok' })
  })
  URL.createObjectURL = vi.fn(() => 'blob:img')
  URL.revokeObjectURL = vi.fn()
})

describe('disease check report', () => {
  it('builds every section from the saved check and the knowledge base, with a PDF download', async () => {
    renderRoute('/vision/disease-checks/12/report')
    expect(await screen.findByRole('heading', { level: 1, name: 'Tomato: Late blight' })).toBeInTheDocument()
    for (const t of ['Result summary', 'How the prediction was made', 'About Late blight', 'Symptoms to look for', 'Why it occurs and how it spreads', 'How to overcome it: action plan', 'When to seek expert advice', 'Limitations']) {
      expect(await screen.findByRole('heading', { name: new RegExp(t) })).toBeInTheDocument()
    }
    expect(screen.getByText('Destroy infected plants')).toBeInTheDocument()
    expect(screen.getByText(/plantvillage-mobilenet-v2/, { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Potato: Late blight: 20.7 %')).toBeInTheDocument()
    const print = vi.fn()
    window.print = print
    screen.getByRole('button', { name: 'Download PDF' }).click()
    expect(print).toHaveBeenCalled()
  })
})
