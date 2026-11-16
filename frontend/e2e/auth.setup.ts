import { expect, test as setup } from '@playwright/test'

/** Sign in once through the real login form (local Supabase Auth) and save the session for the app tests. */
setup('sign in with the local E2E test account', async ({ page }) => {
  const email = process.env.E2E_TEST_EMAIL
  const password = process.env.E2E_TEST_PASSWORD
  if (!email || !password) throw new Error('Set E2E_TEST_EMAIL and E2E_TEST_PASSWORD (frontend/.env.local).')
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login/)
  await page.context().storageState({ path: 'e2e/.auth/user.json' })
})
