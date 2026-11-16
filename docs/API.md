# AGRI-SENSE REST API (v1)

Base path `/api/v1`. Interactive docs at `/docs`; OpenAPI schema at `/api/v1/openapi.json`.

> **Authentication:** every route except `/health` and `/system/info` needs
> `Authorization: Bearer <Supabase access token>`. Users only see their own farms (admins see all).
> Full rules: [AUTH.md](AUTH.md).

## Conventions

| Topic | Rule |
|---|---|
| Lists | `?limit=` (1–200, default 50) and `?offset=`; response `{items, total, limit, offset}` |
| Updates | `PATCH` changes only the fields sent; unknown fields are rejected (422) |
| Numbers | Exact `NUMERIC` in the DB, JSON numbers on the wire |
| Times | ISO 8601; readings **must** carry a timezone offset |
| Errors | Always `{"error": {"code", "message", "details"}}` (see below) |
| Audit | Every create/update/delete writes an `audit_logs` row in the same transaction |

| Status | `code` | When |
|---|---|---|
| 401 | `unauthorized` | Missing, expired or untrusted token (`WWW-Authenticate: Bearer`) |
| 403 | `forbidden` | Signed in but the role is not allowed (e.g. editing the crop catalogue) |
| 404 | `not_found` | Record or route does not exist, **or belongs to another user** |
| 409 | `duplicate` | Unique constraint (e.g. zone name already used on this farm) |
| 409 | `in_use` | Delete blocked by a reference (e.g. crop used by a crop cycle) |
| 409 | `conflict` | Invalid state transition (e.g. acknowledging a resolved alert) |
| 422 | `validation_error` | Request body / query failed validation (`details` lists fields) |
| 422 | `invalid` | Cross-record rule broken (e.g. zone belongs to another farm) |
| 422 | `constraint_violation` / `missing_value` / `invalid_reference` | DB-level guard tripped |

## Resources

| Resource | Endpoints |
|---|---|
| System | `GET /health`, `GET /system/info` |
| Account | `GET/PATCH /me` (profile is created on first sign-in) |
| Users *(admin)* | `GET /users`, `GET/PATCH /users/{id}` (role changes) |
| Farms | `POST/GET /farms` (owner = caller), `GET/PATCH/DELETE /farms/{id}` |
| Zones | `POST/GET /farms/{id}/zones`, `GET/PATCH/DELETE /zones/{id}` |
| Crops | `GET /crops` (`?category`, `?q`), `GET /crops/{id}`; admin: `POST /crops`, `PATCH/DELETE /crops/{id}` |
| Crop cycles | `POST/GET /zones/{id}/crop-cycles` (`?status`), `GET/PATCH/DELETE /crop-cycles/{id}` |
| Soil profiles | `POST/GET /zones/{id}/soil-profiles`, `GET/PATCH/DELETE /soil-profiles/{id}` |
| Soil measurements | `POST/GET /zones/{id}/soil-measurements` (`?start&end`), `GET/DELETE /soil-measurements/{id}` |
| Devices | `POST/GET /farms/{id}/devices`, `GET/PATCH/DELETE /devices/{id}` |
| Sensors | `GET /sensor-types`, `POST/GET /farms/{id}/sensors` (`?zone_id&sensor_type&source`), `GET/PATCH/DELETE /sensors/{id}` |
| Readings | `POST /sensors/{id}/readings`, `GET /sensors/{id}/readings` (`?start&end&limit`), `GET /sensors/{id}/readings/latest` |
| Irrigation | `POST/GET /zones/{id}/irrigation-events`, `GET/PATCH /irrigation-events/{id}` |
| Fertilizer | `POST/GET /zones/{id}/fertilizer-applications` (`?start&end`), `DELETE /fertilizer-applications/{id}` |
| Pesticide | `POST/GET /zones/{id}/pesticide-applications` (`?start&end`; optional `disease_detection_id` links the evidence), `DELETE /pesticide-applications/{id}` |
| Dashboard | `GET /farms/{id}/dashboard`, `GET /farms/{id}/series`, `GET /farms/{id}/weather`. See [DASHBOARD.md](DASHBOARD.md) |
| Digital twin | `GET /farms/{id}/twin`: scene built from records; see [TWIN.md](TWIN.md) |
| Soil intelligence | `GET /zones/{id}/soil`, `GET /farms/{id}/soil`, `POST/GET /zones/{id}/soil/assessments`. See [SOIL.md](SOIL.md) |
| Plant recognition | `GET /vision/model`, `POST/GET /farms/{id}/vision/recognitions` (multipart `file`, optional `zone_id`), `GET/DELETE /vision/recognitions/{id}`, `GET /vision/recognitions/{id}/image`. See [VISION.md](VISION.md) |
| Disease screening | `GET /vision/disease/models`, `POST/GET /farms/{id}/vision/disease-checks` (multipart `file`, `crop` and/or `zone_id`), `GET/DELETE /vision/disease-checks/{id}`, `GET /vision/disease-checks/{id}/image`. See [DISEASE_MODELS.md](DISEASE_MODELS.md) |
| Recommendations | `GET /farms/{id}/recommendations/preview`, `POST /farms/{id}/recommendations/generate`, `GET /farms/{id}/recommendations` (`?status`), `POST /recommendations/{id}/respond`. See [RECOMMENDATIONS.md](RECOMMENDATIONS.md) |
| Smart irrigation | `GET /zones/{id}/irrigation/plan`, `GET /farms/{id}/irrigation/plan`, `POST /zones/{id}/irrigation/schedule`, `GET /zones/{id}/irrigation/water-use` (`?days`). See [IRRIGATION.md](IRRIGATION.md) |
| Nutrients & chemicals | `GET /zones/{id}/nutrients/plan`, `PUT/DELETE /crop-cycles/{id}/nutrient-target`, `GET /zones/{id}/chemicals/use`, `GET /zones/{id}/chemicals/spray-check`. See [NUTRIENTS.md](NUTRIENTS.md) |
| Yield | `GET /zones/{id}/yield`, `POST/GET /zones/{id}/yield/predictions`, `GET /farms/{id}/yield/backtest`, `PUT/DELETE /crop-cycles/{id}/yield-reference`, `GET /yield/ky`. See [YIELD.md](YIELD.md) |
| Federated learning | `GET /farms/{id}/federated`, `POST /farms/{id}/federated/enroll`, `POST /farms/{id}/federated/leave`, `POST/GET /federated/runs` (admin), `GET /federated/runs/{id}` (admin), `GET /zones/{id}/federated/forecast`. See [FEDERATED.md](FEDERATED.md) |
| Analytics & reports | `GET /farms/{id}/analytics` (`?start&end`), `POST/GET /farms/{id}/reports`, `GET/DELETE /reports/{id}`, `GET /reports/{id}/csv`. See [ANALYTICS.md](ANALYTICS.md) |
| Automatic alerts | `POST /farms/{id}/alerts/evaluate`, `GET/PUT /farms/{id}/alert-settings`; live `event: alert` on `GET /farms/{id}/stream`. See [ALERTS.md](ALERTS.md) |
| Simulator & stream | `POST /zones/{id}/simulator/provision`, `POST /farms/{id}/simulator/backfill`, `GET /farms/{id}/simulator`, `GET /farms/{id}/stream`. See [SIMULATOR.md](SIMULATOR.md) |
| Alerts | `POST/GET /farms/{id}/alerts` (`?status&severity`), `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve` |



## Sensor data rules

- **Source is never trusted from the client for devices:** a `simulator` device is always `simulated`;
  every other device type is `hardware`. A sensor attached to a device must share its source.
  `is_simulated` is included on every sensor and reading series so the UI can label it.
- **Ingest** `POST /sensors/{id}/readings` with `{"readings": [{"recorded_at", "value"}]}` (1–1000 per batch).
  - Idempotent: a repeated `(sensor, recorded_at)` is counted in `duplicates`, never stored twice.
  - Values outside the sensor's `min_valid`/`max_valid` are stored as `quality: "suspect"`, not dropped.
  - Timestamps more than 5 minutes in the future, naive timestamps, NaN and infinity are rejected.
  - Response: `{received, inserted, duplicates, suspect}`.
- **Query** returns the most recent `limit` points in `[start, end)` (default: the last 24 h), oldest first.
  The window may not exceed 93 days.

## Reference data

```bash
python -m app.cli.seed          # crop catalogue (12 crops, idempotent)
python -m app.cli.seed --demo   # + "Demo Farm" with 4 zones (clearly labelled, no sensor data)
```
