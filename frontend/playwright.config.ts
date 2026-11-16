import { readFileSync } from 'node:fs'
import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests against the real local stack: Vite frontend, FastAPI backend, local Supabase Auth and Postgres.
 * Prerequisites: `npm run auth:start` (repo root), the dev database running, and the E2E test account
 * in frontend/.env.local as E2E_TEST_EMAIL / E2E_TEST_PASSWORD (git-ignored; may be written as comments).
 */
for (const line of (() => {
  try {
    return readFileSync('.env.local', 'utf8').split(/\r?\n/)
  } catch {
    return []
  }
})()) {
  const m = /^#?\s*(E2E_TEST_[A-Z_]+)=(.*)$/.exec(line)
  if (m && !process.env[m[1]!]) process.env[m[1]!] = m[2]!.trim()
}

const python = process.platform === 'win32' ? '.venv/Scripts/python' : '.venv/bin/python'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false, // one shared test farm: run flows one after another
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    // E2E_BASE_URL runs the suite against an already-running deployment (e.g. the Docker stack on :8080).
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    { name: 'signed-out', testMatch: /signed-out\.spec\.ts/, use: { ...devices['Desktop Chrome'] } },
    {
      name: 'app',
      testMatch: /(app|journeys)\.spec\.ts/,
      dependencies: ['setup'],
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/user.json' },
    },
  ],
  webServer: process.env.E2E_BASE_URL ? undefined : [
    {
      command: `${python} -m uvicorn app.main:app --port 8000`,
      cwd: '../backend',
      url: 'http://localhost:8000/api/v1/health',
      reuseExistingServer: true,
      timeout: 60_000,
    },
    { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: true, timeout: 60_000 },
  ],
})
