# Testing (Phase 18)

Three layers, each run the same way locally and (where possible) in CI.

| Layer | Tool | Where | What it covers |
|---|---|---|---|
| Backend unit + API | pytest, pytest-cov | `backend/tests` | domain maths, rules, services, every endpoint against a real Postgres (each test in its own rolled-back transaction), runners, CLIs |
| Frontend unit + component | Vitest, Testing Library, v8 coverage | `frontend/src/**/*.test.ts(x)` | pages and components with a mocked API and a fake Supabase client |
| End-to-end | Playwright (Chromium) | `frontend/e2e` | the real app in a real browser against the real local stack: Supabase sign-in, FastAPI, Postgres, the ONNX models, WebGL |

## Running

```bash
# backend (needs the dev Postgres: docker compose up -d)
cd backend && .venv/Scripts/python -m pytest -o addopts="" --cov

# frontend unit tests with coverage
cd frontend && npm run test:coverage

# end-to-end (needs: npm run auth:start in the repo root, the dev database, E2E_TEST_EMAIL / E2E_TEST_PASSWORD
# in frontend/.env.local). Starts the backend and Vite if they are not already running.
cd frontend && npm run test:e2e
```

## Coverage (measured in Phase 18)

| | Lines / statements | Branches | Floor |
|---|---|---|---|
| Backend (`app/`) | 94.3 % (branch-aware total); 93.2 % without the disease models, as in CI | included in total | 90 % locally and in CI |
| Frontend (`src/`) | 85.7 % lines, 82.8 % statements | 69.4 % | lines 80, statements 78, functions 75, branches 65 (`vite.config.ts`) |

Not counted in frontend unit coverage: `src/features/twin/Scene.tsx` (needs WebGL, which jsdom lacks; the E2E
suite renders it in Chromium) and `src/main.tsx` (entry point).

In CI the two disease ONNX models are not available (they are converted locally), so the 3 tests that need
them are skipped; a local run without those files measured 93.2 %, above the same 90 % floor.

## End-to-end suite

12 tests: sign in through the real form; signed-out redirect; a wrong password rejected by Supabase; public pages
and API health; dashboard with live (simulated) data; the 3D twin rendering a WebGL canvas; soil assessment;
irrigation and nutrient plans; produce recognition with the real model on a real photo; advice and alerts
("Check now"); analytics report save, open, CSV download and delete; header navigation through "More" without
horizontal overflow.

Tests that write data clean up after themselves. The recognition test deletes its record in a `finally` block,
so cleanup also happens when an assertion fails. The suite runs serially (one worker) because it shares the test
account's farm.

## CI

`.github/workflows/ci.yml` runs on every push and pull request once the repository is on GitHub:

* **backend:** ruff (lint + format check), mypy, `alembic upgrade head && alembic check`, pytest with coverage,
  against a Postgres 17 service;
* **frontend:** eslint, `tsc`, Vitest with coverage floors, production build.

E2E is not in CI: it needs the Supabase Auth stack and a test account.

## Phase 18 findings fixed

* The weather charts had no text alternative (the trend chart did). They now include the same "View as table".
* Several flaky-test timeouts were already fixed in earlier phases (5 s async waits, 15 s per test).
