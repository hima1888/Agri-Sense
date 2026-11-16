# AGRI-SENSE database

PostgreSQL (Supabase in production, Docker `postgres:17` locally). Schema is owned by
SQLAlchemy models in `backend/app/models/` and versioned with Alembic in `backend/migrations/`.

## Tables (26)

| Domain | Table | Purpose |
|---|---|---|
| Identity | `users` | App profile; `id` = Supabase Auth user id (uuid), created on first sign-in; holds the role |
| Farm | `farms` | A farm owned by a user |
| | `farm_zones` | Management units (field, greenhouse, orchard…); GeoJSON boundary |
| Soil | `soil_profiles` | Slow-changing physical properties (texture, field capacity) |
| | `soil_measurements` | Point-in-time chemistry (pH, N, P, K, EC, moisture) |
| Crops | `crops` | Catalogue of species and agronomic requirements |
| | `crop_cycles` | One planting of a crop in a zone, planting → harvest |
| | `plants` | Individually tracked plants (trees, sample plants) |
| IoT | `devices` * | Physical/simulated nodes (ESP32, gateway, simulator) |
| | `sensors` | One measured quantity; `source` = `simulated` \| `hardware` |
| | `sensor_readings` | Time series; unique `(sensor_id, recorded_at)` for idempotent ingest |
| Weather | `weather_data` | Observations + forecasts; upsert key `(farm_id, kind, source, valid_at)` |
| Operations | `irrigation_events` | Water applied, trigger, link to AI recommendation |
| | `fertilizer_applications` | Product, N-P-K %, quantity, method |
| | `pesticide_applications` | Product, active ingredient, pre-harvest interval |
| Vision | `plant_detections` | Plant/leaf/fruit/vegetable recognition results |
| | `disease_detections` | Disease diagnosis, severity, explanation payload |
| AI | `model_versions` | Model registry: metrics, labels, known limitations |
| | `ai_predictions` | Prediction + confidence + factors + limitations (all NOT NULL) |
| | `ai_recommendations` | Actionable advice, expected impact, accept/reject lifecycle |
| Platform | `alerts` | Sensor/soil/weather/disease alerts with ack/resolve lifecycle |
| | `reports` | Generated reports per period |
| | `federated_learning_runs` | A federated training job |
| | `federated_clients` | Farms enrolled in federated learning |
| | `federated_client_updates` * | A client's update for one round (many-to-many run↔client) |
| | `audit_logs` | Append-only change history |

\* Supporting tables beyond the original list, added for correct normalisation:
one ESP32 carries several sensors, and federated participation is per run *and* round.

## Key relationships

```
users 1─* farms 1─* farm_zones 1─* soil_profiles / soil_measurements / crop_cycles 1─* plants
farms 1─* devices 1─* sensors 1─* sensor_readings
crops 1─* crop_cycles            (RESTRICT: a crop in use cannot be deleted)
model_versions 1─* ai_predictions 1─* ai_recommendations ─* irrigation/fertilizer/pesticide/alerts
plant_detections 1─* disease_detections 1─* pesticide_applications
federated_learning_runs *─* federated_clients  (via federated_client_updates)
```

Deletes: owned data cascades (farm → zones → sensors → readings); optional references use
`SET NULL` (deleting a device keeps its sensors; deleting a user keeps audit history).

## Conventions

- **Primary keys:** `bigint generated always as identity`; `users.id` is `uuid` to match Supabase Auth.
- **Timestamps:** always `timestamptz`. Tables with `updated_at` have a `set_updated_at()` trigger,
  so edits made outside the API (e.g. Supabase dashboard) still update it.
- **Enumerations:** `text` + `CHECK` (values in `app/models/enums.py`), easier to evolve than native enums.
- **Indexes:** every foreign key is indexed (enforced by a test); composite indexes for
  time-ordered per-entity queries; BRIN on `sensor_readings.recorded_at`; partial index for open alerts.
- **Constraint names** are deterministic (`ck_sensors_sensor_type_valid`, `uq_…`, `fk_…`).

## Security (RLS)

Row level security is **enabled on every table with no policies**. Supabase's public Data API
(anon / authenticated keys) can therefore read or write nothing. The FastAPI backend connects as the
table owner (bypasses RLS) and enforces per-farm authorization itself in Phase 4.

## Commands (from `backend/`)

```bash
docker compose up -d                       # from repo root: local Postgres on :54329
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m alembic downgrade -1
.venv/Scripts/python -m alembic revision --autogenerate -m "describe change"
.venv/Scripts/python -m alembic check      # fails if models and migrations differ
```

### Applying to Supabase

Set `DATABASE_URL` in `backend/.env` to the **Session pooler** connection string
(Project → Connect → Session pooler, port 5432), then run `alembic upgrade head`.
`postgres://` / `postgresql://` URLs are accepted as copied; the app switches to psycopg 3.
