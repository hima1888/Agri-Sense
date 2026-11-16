# Security and performance (Phase 19)

## API hardening (`backend/app/core/hardening.py`)

| Control | Detail |
|---|---|
| Security headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (no camera/mic/geolocation), `Cross-Origin-Resource-Policy: same-site`, CSP `default-src 'none'` on API responses; HSTS in production only |
| Request size | bodies over `MAX_UPLOAD_MB` + 1 MB rejected with 413 from `Content-Length`, before being read |
| Rate limiting | per caller (hashed bearer token, else IP), 60 s sliding window: 300/min general, 20/min for model/aggregation/write-heavy endpoints; 429 with `Retry-After`. `/health` and the SSE stream are exempt |
| Docs | `/docs` and the OpenAPI schema are hidden when `APP_ENV=production` |
| CORS | only origins in `CORS_ORIGINS` |
| AuthZ | every farm/zone query is scoped to the signed-in owner (tested since Phase 3: other users get 404) |

**Limitation:** the rate limiter is in memory and per process. With several API instances, use a shared limiter
(reverse proxy or Redis).

Settings: `RATE_LIMIT_ENABLED`, `RATE_LIMIT_PER_MINUTE` (10–100000), `RATE_LIMIT_EXPENSIVE_PER_MINUTE` (1–10000).

## Frontend

* `frontend/public/_headers`: security headers and long caching for hashed assets (Netlify / Cloudflare Pages format).
* Every page is lazy-loaded: the first visit downloads only the shell; the 3D twin (three.js) loads only on its page.
* Known: the charts library chunk is still preloaded on first load, because the bundler placed the shared React
  JSX runtime in it. About 364 kB gzip on first load.

## Dependency audits

* `npm audit`: 0 vulnerabilities (dev-only `minimatch` advisory fixed with an `overrides` entry, no `--force`).
* `pip-audit -r requirements.txt`: no known vulnerabilities.

## Measured API latency (local, 5 requests each, p50)

Health 9 ms; farm list 45 ms; series/forecast/federated 33–65 ms; twin/soil/irrigation/nutrients 130–170 ms;
dashboard 173 ms; yield 229 ms; recommendations preview 335 ms; analytics 706 ms (aggregates a full season).

## Bug found by this phase

Weather refresh failed with 422 because Open-Meteo returned a slightly negative shortwave radiation value (dusk),
which violated a database check. Values are now clamped to physical ranges in the parser (regression test added).
