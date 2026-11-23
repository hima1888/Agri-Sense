import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

/**
 * Real user journeys (functionality verification): real photos, real ONNX models, real API and database,
 * real browser. Everything created is deleted in `finally`, even when an assertion fails.
 */

const API = 'http://localhost:8000/api/v1'
const FIX = '../backend/tests/fixtures'
const photo = (name: string) => ({ name, mimeType: 'image/jpeg', buffer: readFileSync(`${FIX}/${name}`) })

async function token(page: Page) {
  return page.evaluate(() => {
    const key = Object.keys(localStorage).find((k) => k.startsWith('sb-') && k.endsWith('-auth-token'))
    return key ? (JSON.parse(localStorage.getItem(key)!) as { access_token: string }).access_token : ''
  })
}

async function checkLeaf(page: Page, file: string, crop: string, zoneLabel?: string) {
  await page.goto('/vision?tab=disease')
  await page.getByLabel('Photo of one leaf').setInputFiles(photo(file))
  const selects = page.getByRole('form', { name: 'Check a leaf for disease' }).locator('select')
  await selects.nth(0).selectOption(crop) // Crop
  if (zoneLabel) await selects.nth(1).selectOption({ label: zoneLabel }) // Zone
  const res = page.waitForResponse((r) => r.url().endsWith('/vision/disease-checks') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Check leaf' }).click()
  const response = await res
  return { status: response.status(), body: (await response.json()) as Record<string, unknown> }
}

test('TEST 1+4: a diseased leaf photo goes through the real model; the result and its guidance are shown and saved', async ({ page }) => {
  // potato_late_blight_field.jpg (Howard F. Schwartz, CSU, Bugwood.org, CC BY 3.0 US), screened as tomato:
  // the PlantVillage model answers "Tomato: Late blight" (late blight affects both crops).
  const { status, body } = await checkLeaf(page, 'potato_late_blight_field.jpg', 'tomato')
  const id = body.detection_id as number | null
  try {
    expect(status).toBe(201)
    expect(body.outcome).toBe('possible_disease')
    expect((body.model as { key: string }).key).toBe('plantvillage')
    expect(body.label).toBe('Tomato: Late blight')
    expect(body.knowledge_key).toBe('late_blight')
    const result = page.getByRole('region', { name: 'Disease result' })
    await expect(result.getByText('Possible disease')).toBeVisible()
    await expect(result.getByText(/model confidence \d+(\.\d)? %/)).toBeVisible()
    const about = result.getByRole('region', { name: 'About Late blight' })
    await expect(about.getByText('Phytophthora infestans')).toBeVisible()
    await expect(about.getByText('When to seek expert advice')).toBeVisible()
    await expect(result.getByText('Saved to disease-check history.')).toBeVisible()

    // The downloadable report, built from the saved record and the knowledge base.
    await result.getByRole('link', { name: 'Open full report (PDF)' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Tomato: Late blight' })).toBeVisible()
    await expect(page.getByRole('heading', { name: /How to overcome it: action plan/ })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Download PDF' })).toBeVisible()
    const pdf = await page.pdf({ format: 'A4' }) // what "Save as PDF" produces
    expect(pdf.byteLength).toBeGreaterThan(20_000)
  } finally {
    if (id != null) expect((await page.request.delete(`${API}/vision/disease-checks/${id}`, { headers: { Authorization: `Bearer ${await token(page)}` } })).status()).toBe(204)
  }
})

test('TEST 2: non-leaf and unsupported photos are refused, not guessed, and not saved', async ({ page }) => {
  const banana = await checkLeaf(page, 'banana.jpg', 'tomato')
  expect(banana.body.outcome).toBe('not_a_leaf')
  expect(banana.body.saved).toBe(false)
  await expect(page.getByRole('region', { name: 'Disease result' }).getByText('Not a leaf photo', { exact: true })).toBeVisible()

  const wheat = await checkLeaf(page, 'wheat_leaf_rust_field.jpg', 'wheat')
  expect(wheat.body.outcome).toBe('cannot_identify') // the model's top answer is a corn class, so no answer is given
  expect(wheat.body.knowledge).toBeNull()
  await expect(page.getByRole('region', { name: 'Disease result' }).getByText('Cannot reliably identify', { exact: true })).toBeVisible()
})

test('TEST 5: the crop-growth page draws stages from the API and plays through them', async ({ page }) => {
  await page.goto('/growth')
  const stages = page.getByRole('list', { name: 'Growth stages' })
  await expect(stages.getByRole('button')).toHaveCount(8, { timeout: 30_000 })
  await stages.getByRole('button', { name: /Flowering/ }).click()
  await expect(page.getByRole('img', { name: /at the flowering stage/ })).toBeVisible()
  await expect(page.getByText(/FAO-56 Table 11/).first()).toBeVisible()
})

test('TEST 6: a disease check saved for a zone changes that zone in the 3D twin and its details', async ({ page }) => {
  const t = await (async () => (await page.goto('/twin'), token(page)))()
  const farms = (await (await page.request.get(`${API}/farms?limit=100`, { headers: { Authorization: `Bearer ${t}` } })).json()) as { items: { id: number }[] }
  const farmId = farms.items[0]!.id
  const twin = (await (await page.request.get(`${API}/farms/${farmId}/twin`, { headers: { Authorization: `Bearer ${t}` } })).json()) as {
    zones: { id: number; name: string; health: unknown }[]
  }
  const zone = twin.zones[0]!
  const { body } = await checkLeaf(page, 'potato_late_blight_field.jpg', 'tomato', zone.name)
  const id = body.detection_id as number
  try {
    expect(body.outcome).toBe('possible_disease')
    const after = (await (await page.request.get(`${API}/farms/${farmId}/twin`, { headers: { Authorization: `Bearer ${t}` } })).json()) as {
      zones: { id: number; health: { state: string; detection_id: number; knowledge_key: string } | null }[]
    }
    const z = after.zones.find((x) => x.id === zone.id)!
    expect(z.health?.state).toBe('disease')
    expect(z.health?.detection_id).toBe(id)
    expect(z.health?.knowledge_key).toBe('late_blight')

    // In the browser: open the twin, pick the zone from the accessible zone list, and read its details.
    await page.goto('/twin')
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30_000 })
    await page.getByRole('navigation', { name: 'Twin objects' }).getByRole('button', { name: zone.name, exact: false }).first().click()
    const details = page.getByRole('region', { name: 'Zone' })
    await expect(details.getByText(/Possible disease: Tomato: Late blight/)).toBeVisible()
    await details.getByRole('button', { name: 'Disease information' }).click()
    await expect(details.getByRole('region', { name: 'About Late blight' })).toBeVisible()
  } finally {
    expect((await page.request.delete(`${API}/vision/disease-checks/${id}`, { headers: { Authorization: `Bearer ${t}` } })).status()).toBe(204)
  }
})

test('TEST 7: a new user sets up the demo farm in one click and live sensor readings arrive', async ({ page }) => {
  // Show this account as having no farms (as a brand-new user sees it); every request after the click is real.
  let empty = true
  await page.route(/\/api\/v1\/farms\?limit=100$/, async (route) => {
    const res = await route.fetch()
    const body = (await res.json()) as { items: unknown[]; total?: number }
    await route.fulfill({ response: res, json: empty ? { ...body, items: [], total: 0 } : body })
  })
  await page.goto('/dashboard')
  const create = page.waitForResponse((r) => r.url().endsWith('/api/v1/farms') && r.request().method() === 'POST')
  const backfill = page.waitForResponse((r) => r.url().endsWith('/simulator/backfill'), { timeout: 60_000 })
  await page.getByRole('button', { name: 'Set up a demo farm' }).click()
  const farmId = ((await (await create).json()) as { id: number }).id
  try {
    expect((await backfill).status()).toBe(200)
    empty = false
    await page.goto(`/dashboard?farm=${farmId}`)
    await expect(page.getByRole('heading', { level: 1, name: 'Demo farm' })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole('region', { name: 'Zones' }).getByText('Corn field')).toBeVisible()
    await expect(page.getByText(/Simulated sensor data\./)).toBeVisible()
    await expect(page.getByText(/[1-9][\d,]* readings in the last 24 h/)).toBeVisible()
    await expect(page.getByText('Live', { exact: true }).first()).toBeVisible({ timeout: 30_000 })
  } finally {
    expect((await page.request.delete(`${API}/farms/${farmId}`, { headers: { Authorization: `Bearer ${await token(page)}` } })).status()).toBe(204)
  }
})

test('TEST 8: picking a crop offers a new zone for it; the zone is created with live sensors and selected', async ({ page }) => {
  await page.goto('/vision?tab=disease')
  const form = page.getByRole('form', { name: 'Check a leaf for disease' })
  const [crop, zone] = [form.locator('select').nth(0), form.locator('select').nth(1)]
  await crop.selectOption('squash')
  await expect(zone.locator('option', { hasText: '+ New zone: Squash field' })).toHaveCount(1)
  const created = page.waitForResponse((r) => /\/farms\/\d+\/zones$/.test(r.url()) && r.request().method() === 'POST')
  const sensors = page.waitForResponse((r) => r.url().endsWith('/simulator/provision'))
  await zone.selectOption('new')
  const zoneId = ((await (await created).json()) as { id: number }).id
  try {
    expect((await sensors).status()).toBe(201)
    await expect(zone).toHaveValue(String(zoneId))
    await expect(zone.locator('option:checked')).toHaveText('Squash field')
    await expect(zone.locator('option', { hasText: '+ New zone' })).toHaveCount(0) // the crop has its zone now
  } finally {
    expect((await page.request.delete(`${API}/zones/${zoneId}`, { headers: { Authorization: `Bearer ${await token(page)}` } })).status()).toBe(204)
  }
})

test('TEST 9: a fruit photo goes through the orange-fruit model; canker is found and the report says fruit', async ({ page }) => {
  await page.goto('/vision?tab=disease')
  await page.getByRole('radio', { name: 'Fruit' }).click()
  await page.getByLabel('Photo of one fruit').setInputFiles(photo('orange_citrus_canker_fruit.jpg'))
  await page.getByRole('form', { name: 'Check a leaf for disease' }).locator('select').nth(0).selectOption('orange')
  const res = page.waitForResponse((r) => r.url().endsWith('/vision/disease-checks') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Check fruit' }).click()
  const body = (await (await res).json()) as Record<string, unknown>
  const id = body.detection_id as number | null
  try {
    expect(body.part).toBe('fruit')
    expect(body.outcome).toBe('possible_disease')
    expect((body.model as { key: string }).key).toBe('orange_fruit')
    expect(body.label).toBe('Orange: Citrus canker')
    const result = page.getByRole('region', { name: 'Disease result' })
    await expect(result.getByRole('region', { name: 'About Citrus canker' })).toBeVisible()
    await expect(result.getByText('Severity is not estimated for fruit photos.')).toBeVisible()
    await result.getByRole('link', { name: 'Open full report (PDF)' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Orange: Citrus canker' })).toBeVisible()
    await expect(page.getByText('not estimated for fruit photos', { exact: true })).toBeVisible()
  } finally {
    if (id != null) expect((await page.request.delete(`${API}/vision/disease-checks/${id}`, { headers: { Authorization: `Bearer ${await token(page)}` } })).status()).toBe(204)
  }
})
