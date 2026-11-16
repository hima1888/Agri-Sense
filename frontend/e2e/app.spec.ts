import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

/**
 * Signed-in flows against the real stack and the E2E test account's farm. Tests that write data
 * (a vision recognition, a report) delete what they create.
 */

test('dashboard shows the farm with live sensor data, labelled simulated', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Zones' })).toBeVisible()
  await expect(page.getByText(/simulated/i).first()).toBeVisible()
})

test('3D twin renders a WebGL scene', async ({ page }) => {
  await page.goto('/twin')
  const canvas = page.locator('canvas').first()
  await expect(canvas).toBeVisible({ timeout: 30_000 })
  const webgl = await canvas.evaluate((c: HTMLCanvasElement) => !!(c.getContext('webgl2') ?? c.getContext('webgl')))
  expect(webgl).toBe(true)
  const box = await canvas.boundingBox()
  expect(box && box.width > 300 && box.height > 200).toBe(true)
})

test('soil assessment shows an index, confidence and the water balance', async ({ page }) => {
  await page.goto('/soil')
  await expect(page.getByText('Soil index', { exact: false }).first()).toBeVisible()
  await expect(page.getByRole('region', { name: 'Root-zone water balance (FAO-56)' })).toBeVisible()
  await expect(page.getByText(/Confidence \d+ %/).first()).toBeVisible()
})

test('irrigation plan and nutrient plan load for a zone', async ({ page }) => {
  await page.goto('/irrigation')
  await expect(page.getByRole('region', { name: 'Method and limitations' })).toBeVisible()
  await page.goto('/nutrients')
  await expect(page.getByRole('region', { name: /Fertilizer plan/ })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Chemical use this crop cycle' })).toBeVisible()
})

test('produce recognition runs the real model on a photo, then the record is deleted', async ({ page }) => {
  await page.goto('/vision')
  await page.getByLabel(/Photo of a fruit/).setInputFiles({
    name: 'banana.jpg',
    mimeType: 'image/jpeg',
    buffer: readFileSync('../backend/tests/fixtures/banana.jpg'),
  })
  const created = page.waitForResponse((r) => r.url().endsWith('/vision/recognitions') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Recognise' }).click()
  const body = (await (await created).json()) as { detection_id: number | null; label: string | null }
  try {
    expect(body.label).toBe('banana')
    const result = page.getByRole('region', { name: 'Result' })
    await expect(result.locator('p.font-display', { hasText: 'banana' })).toBeVisible({ timeout: 30_000 })
    await expect(result.getByText(/not trained on farm photos/)).toBeVisible()
  } finally {
    // Always remove what this test created, even if an assertion failed.
    if (body.detection_id != null) {
      const token = await page.evaluate(() => {
        const key = Object.keys(localStorage).find((k) => k.startsWith('sb-') && k.endsWith('-auth-token'))
        return key ? (JSON.parse(localStorage.getItem(key)!) as { access_token: string }).access_token : ''
      })
      const res = await page.request.delete(`http://localhost:8000/api/v1/vision/recognitions/${body.detection_id}`, { headers: { Authorization: `Bearer ${token}` } })
      expect(res.status()).toBe(204)
    }
  }
})

test('advice and alerts pages work, and "Check now" evaluates the rules', async ({ page }) => {
  await page.goto('/advice')
  await expect(page.getByRole('region', { name: 'Decisions' })).toBeVisible({ timeout: 30_000 })
  await page.goto('/alerts')
  await page.getByRole('button', { name: 'Check now' }).click()
  await expect(page.getByText(/Checked: \d+ condition\(s\) true/)).toBeVisible()
})

test('analytics: save a report, open it, download CSV, delete it', async ({ page }) => {
  await page.goto('/analytics')
  await expect(page.getByRole('region', { name: 'Sustainability indicators' })).toBeVisible({ timeout: 30_000 })
  const saved = page.getByRole('region', { name: 'Saved reports' })
  const before = await saved.getByRole('link', { name: 'Open' }).count()
  await page.getByRole('button', { name: 'Save report for this period' }).click()
  await expect(saved.getByRole('link', { name: 'Open' })).toHaveCount(before + 1)

  const download = page.waitForEvent('download')
  await saved.getByRole('button', { name: 'CSV' }).first().click()
  const file = await download
  expect(file.suggestedFilename()).toMatch(/^agri-sense-report-\d+-.*\.csv$/)
  expect(readFileSync(await file.path(), 'utf8').split(/\r?\n/)[0]).toBe('section,metric,value')

  await saved.getByRole('link', { name: 'Open' }).first().click()
  await expect(page.getByRole('button', { name: 'Print / save as PDF' })).toBeVisible()
  await page.goBack()
  await saved.getByRole('button', { name: 'Delete' }).first().click()
  await expect(saved.getByRole('link', { name: 'Open' })).toHaveCount(before)
})

test('header navigation reaches the secondary pages through "More"', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/dashboard')
  await page.getByRole('button', { name: /More/ }).click()
  await page.getByRole('link', { name: 'Shared learning' }).click()
  await expect(page).toHaveURL(/\/federated/)
  const width = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(width).toBeLessThanOrEqual(1280)
})
