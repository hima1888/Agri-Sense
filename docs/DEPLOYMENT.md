# Deployment (Phase 20)

Two supported ways to run AGRI-SENSE in production. Both use **Supabase for sign-in only**; the app's data is in
its own Postgres, and every request is checked by the API (owner-scoped queries).

## Option A: Docker Compose on any server (verified)

```bash
cp .env.production.example .env.production      # fill in; the file is git-ignored
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

Open `http://<server>:8080`. Three containers:

| Service | Image | What it does |
|---|---|---|
| `db` | postgres:17-alpine | app data (volume `db-data`), not exposed outside the stack |
| `api` | `backend/Dockerfile` (python 3.13-slim, non-root) | runs `alembic upgrade head`, then uvicorn; health check on `/api/v1/health`; photos in volume `uploads` |
| `web` | `frontend/Dockerfile` (nginx) | the built SPA with security headers; proxies `/api` to the API (one origin, so no CORS; live stream unbuffered) |

Put HTTPS in front (Caddy, Traefik, or the cloud provider's load balancer) and set `PUBLIC_WEB_ORIGIN` to the
HTTPS address. HSTS is sent by the API in production; the proxy should redirect HTTP to HTTPS.

**Verified in Phase 20** on this machine against the local Supabase stack: all three containers healthy;
migrations applied (schema 0006); Supabase signing keys loaded; API docs and OpenAPI hidden; Playwright sign-in
and signed-out tests 4/4 against `:8080`; through nginx: create farm and zone, dashboard, twin, weather,
analytics, live stream (`text/event-stream`), photo recognition with the real model (banana, 0.9995), delete.
Image sizes: API 658 MB (ONNX Runtime and the three models), web 78 MB.

## Option B: Render (Blueprint, not yet run)

`render.yaml` defines a Postgres database, the API (Docker) and the web app (static site with SPA rewrite and
headers). In Render: **New + → Blueprint**, select the repository, then enter `SUPABASE_URL`, `CORS_ORIGINS`
(the web URL), `VITE_API_BASE_URL` (the API URL), `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.
Requires pushing the repository to GitHub first. This blueprint has not been deployed from here, so treat the
first deploy as its test.

## Supabase (hosted) setup

1. Create a project at supabase.com. Only **Auth** is used.
2. Authentication → URL configuration: set the Site URL to the web app's address.
3. Copy the project URL and the **publishable** key (never the secret/service key) into the settings above.
4. Create accounts through the app's sign-up page.

## Limitations

* **Disease models are not in git** (converted locally, ~31 MB, see docs/DISEASE_MODELS.md). A Docker build from
  this working copy includes them; a build from git (Render) does not, and disease checks then report the model
  as unavailable. The produce model is downloaded and checksum-verified during the image build.
* Rate limiting is per process (one uvicorn worker by design; the simulator and alert loops run in-process).
  Run one API instance, or move limits to the proxy before scaling out.
* Uploaded photos are on a local volume. Render's free plan has no persistent disk: photos are lost on redeploy
  (recognition results stay in the database).
* Render free services sleep when idle; the first request after a pause takes ~30–60 s.
* The sensor simulator is on by default and its data is labelled "simulated" everywhere in the UI.

## Local dry run against the local Supabase

The API container cannot reach `127.0.0.1` on the host, so set
`SUPABASE_JWKS_URL=http://host.docker.internal:54321/auth/v1/.well-known/jwks.json` (keys are fetched there,
while tokens are still checked against the issuer in `SUPABASE_URL`).

Run the browser tests against a running deployment:
`cd frontend && E2E_BASE_URL=http://localhost:8080 npx playwright test --project=setup --project=signed-out`
