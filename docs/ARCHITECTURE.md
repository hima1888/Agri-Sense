# AGRI-SENSE architecture

## System overview

```
            ┌──────────── web (nginx / static host) ──────────┐
 Browser ──▶│ React SPA (Vite, R3F digital twin, Recharts)    │
            └───────────────┬─────────────────────────────────┘
                            │ REST /api/v1  +  SSE streams
            ┌───────────────▼──────────── api (Docker) ───────┐
            │ FastAPI  + security headers, rate limits         │
            │  ├─ api/v1/*         routers (thin)              │
            │  ├─ services/*       domain logic                │
            │  ├─ domain/          FAO-56, FAO-33, rules       │
            │  ├─ simulator/       sensor simulator + alerts   │
            │  ├─ vision/          ONNX Runtime (3 models)     │
            │  └─ integrations/    Open-Meteo                  │
            └──────┬──────────────────────────────┬───────────┘
                   │ SQLAlchemy + Alembic          │ JWT verify (JWKS)
            ┌──────▼──────────┐          ┌─────────▼──────────┐
            │ PostgreSQL 17   │          │ Supabase Auth      │
            └─────────────────┘          └────────────────────┘
```

Deployment: `docker-compose.prod.yml` (verified) or `render.yaml`; see DEPLOYMENT.md.

## Principles

1. **No fake data paths.** UI only shows data that came from the API. Simulated sensor data is flagged at the
   row level (`sensors.source = 'simulated'`) and labelled in the UI.
2. **Contracts on both sides.** Pydantic models on the backend; matching Zod schemas on the frontend.
3. **Explainable AI.** Every prediction returns prediction, confidence, key factors, recommendation and limitations.
4. **Hardware-ready.** Sensors are an abstraction; simulator and future ESP32 (DHT22, soil moisture, pH, NPK, rain,
   light, water-level) write through the same ingestion path.

## Data model (Phase 2 — implemented)

Full reference: [DATABASE.md](DATABASE.md).

Normalized tables: `users`, `farms`, `farm_zones`, `soil_profiles`, `soil_measurements`, `crops`, `crop_cycles`,
`plants`, `sensors`, `sensor_readings`, `weather_data`, `irrigation_events`, `fertilizer_applications`,
`pesticide_applications`, `plant_detections`, `disease_detections`, `ai_predictions`, `ai_recommendations`,
`alerts`, `reports`, `federated_learning_runs`, `federated_clients`, `model_versions`, `audit_logs`.

## Authentication (Phase 4)

See [AUTH.md](AUTH.md): Supabase email/password, ES256 JWT verification via JWKS, farm-scoped authorization.

## API (Phase 3)

See [API.md](API.md): 64 endpoints, one error format, audit logging, idempotent sensor ingest.

## Phase 1 deliverables

- Monorepo with `frontend/` and `backend/`, each with tests, lint, type checking.
- FastAPI app factory, typed settings, CORS, versioned router, `GET /api/v1/health`, `GET /api/v1/system/info`.
- React shell: routing, page transitions, design tokens, ambient background, reduced-motion support,
  TanStack Query + Zod-validated API client, live API status page.
