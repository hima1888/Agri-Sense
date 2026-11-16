# AGRI-SENSE

An AI, IoT and 3D digital-twin platform for sustainable farming.
**See → Sense → Analyze → Predict → Recommend → Act → Learn.**

> **Version 1.0.0. All 21 build phases complete.** Every AI output shows its prediction, confidence, the factors
> behind it, a recommendation, and its limitations. Simulated data is labelled wherever it appears.

## Features

| Area | What it does | Method | Docs |
|---|---|---|---|
| Sign-in and farms | accounts, farms, zones, crops; every query scoped to the owner | Supabase Auth (JWKS), FastAPI | [AUTH](docs/AUTH.md), [API](docs/API.md) |
| Live sensors | soil moisture, temperature, humidity, pH, EC… streamed live | simulator + SSE (labelled *simulated*) | [SIMULATOR](docs/SIMULATOR.md) |
| Dashboard | KPIs, weather, zones, alerts | Open-Meteo forecast | [DASHBOARD](docs/DASHBOARD.md) |
| 3D digital twin | interactive farm model coloured by live data | React Three Fiber | [TWIN](docs/TWIN.md) |
| Soil intelligence | root-zone water balance and soil score | FAO-56 | [SOIL](docs/SOIL.md) |
| Plant vision | produce recognition with heat-map; leaf-disease screening | ONNX Runtime (3 models) | [VISION](docs/VISION.md), [DISEASE_MODELS](docs/DISEASE_MODELS.md) |
| Disease knowledge | what it is, symptoms, causes, spread, management, prevention, monitoring, when to get advice, for every disease the models output | structured knowledge layer | [GROWTH_AND_KNOWLEDGE](docs/GROWTH_AND_KNOWLEDGE.md) |
| Crop growth | seed → harvest in 8 stages with today's stage per zone, animated from the data | FAO-56 Table 11 | [GROWTH_AND_KNOWLEDGE](docs/GROWTH_AND_KNOWLEDGE.md) |
| Recommendations | explainable advice with evidence | rules over soil, weather, sensors, disease | [RECOMMENDATIONS](docs/RECOMMENDATIONS.md) |
| Smart irrigation | 7-day rain-aware plans, water tracking | FAO-56 | [IRRIGATION](docs/IRRIGATION.md) |
| Nutrients and chemicals | soil-test-adjusted fertilizer, pre-spray check | Soil Health Card practice | [NUTRIENTS](docs/NUTRIENTS.md) |
| Yield | water-limited yield range, back-testing | FAO-33 (Ky) | [YIELD](docs/YIELD.md) |
| Federated learning | opt-in model training across farms | FedAvg (numpy) | [FEDERATED](docs/FEDERATED.md) |
| Analytics and reports | period comparison, saved printable reports, CSV | SQL aggregation | [ANALYTICS](docs/ANALYTICS.md) |
| Alerts | automatic, deduplicated, auto-resolving, live | rule evaluator every 5 min | [ALERTS](docs/ALERTS.md) |

Engineering: [ARCHITECTURE](docs/ARCHITECTURE.md) · [DATABASE](docs/DATABASE.md) · [TESTING](docs/TESTING.md)
(backend 94.4 % coverage, 89 frontend tests, 16 end-to-end) · [SECURITY](docs/SECURITY.md) ·
[DEPLOYMENT](docs/DEPLOYMENT.md) · **[DEMO guide](docs/DEMO.md)** · **[Verification report](docs/VERIFICATION.md)**.

## Known limitations

* No physical sensors are attached: readings come from the simulator and are labelled *simulated*.
* The disease models were trained on lab photos and got 0 of 5 real field photos right in testing; field
  accuracy is unknown. The two disease model files are converted locally and are not in git.
* The federated model does not yet beat a "no change" baseline on the available data; the app says so.
* Yield, irrigation savings and fertilizer doses are rule-based estimates, not field-validated predictions.
* Not deployed to a public URL yet. The production Docker stack is verified locally, and a Render blueprint is included.

## Repository layout

```
frontend/   React 19 + Vite + TypeScript + Tailwind v4 + React Three Fiber
backend/    FastAPI + SQLAlchemy + Alembic + ONNX Runtime
docs/       Architecture and phase notes
```

## Run locally

Database and local auth (Docker):

```bash
docker compose up -d     # app database (Postgres 17) on :54329
npm install              # repo root: Supabase CLI
npm run auth:start       # local Supabase Auth on :54321 (see docs/AUTH.md)
```

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/python
cp .env.example .env
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m app.cli.seed --demo     # crop catalogue + clearly labelled demo farm
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20+):

```bash
cd frontend
cp .env.example .env.local   # fill VITE_SUPABASE_* from: npx supabase status
npm install
npm run dev     # http://localhost:5173 — /api is proxied to :8000
```

## Quality checks

| | Tests | Lint | Types | Build |
|---|---|---|---|---|
| frontend | `npm test` | `npm run lint` | `npm run typecheck` | `npm run build` |
| backend (needs `docker compose up -d`) | `python -m pytest` | `python -m ruff check .` | `python -m mypy app tests` | — |

Schema consistency: `python -m alembic check` (backend) fails if models and migrations differ.

## Run as production containers

```bash
cp .env.production.example .env.production   # fill in
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build   # http://localhost:8080
```
