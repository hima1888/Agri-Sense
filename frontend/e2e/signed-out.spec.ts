import { expect, test } from '@playwright/test'

test('protected pages send signed-out visitors to sign in', async ({ page }) => {
  await page.goto('/soil')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
})

test('a wrong password is rejected by the real auth server', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(process.env.E2E_TEST_EMAIL ?? 'nobody@example.com')
  await page.getByLabel('Password', { exact: true }).fill('definitely-not-the-password-1')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
})

test('public pages and the API health check work', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByText('All systems operational')).toBeVisible() // footer status, from the live API
  await page.goto('/status')
  await expect(page.getByText('agri-sense-api')).toBeVisible()
  const health = await request.get('http://localhost:8000/api/v1/health')
  expect(health.ok()).toBe(true)
})
