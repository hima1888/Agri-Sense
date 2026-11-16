# Sensor simulator & live stream (Phase 5)

- Runs inside the API (`SIMULATOR_ENABLED`, `SIMULATOR_INTERVAL_SECONDS`, default 10 s) for sensors with `source='simulated'`.
- Physics (`app/simulator/physics.py`): solar position, diurnal/seasonal temperature, Magnus humidity, cloud/rain Markov chain,
  single-bucket soil water, nutrient uptake. Seeded and deterministic. These are approximations, not agronomic truth.
- Uses real app data: farm coordinates (required), zone area, soil profile and latest soil test. Logged irrigation and
  fertilizer records change soil moisture, nitrogen, phosphorus, potassium and tank level.
- Every value goes through `services/readings.store()`, the same path as hardware, and is labelled `is_simulated`.
- API: `POST /zones/{id}/simulator/provision`, `POST /farms/{id}/simulator/backfill`, `GET /farms/{id}/simulator`,
  `GET /farms/{id}/stream` (Server-Sent Events: `snapshot`, `readings`, `: ping` every 10 s; Bearer auth in a header).
- Web client: fetch-based SSE (no token in the URL), reconnects with backoff, and drops a silent connection after 25 s.

## Hardware path (future)
An ESP32 posts `{"readings":[{"recorded_at","value"}]}` to `POST /sensors/{id}/readings`. That endpoint stores and streams
the readings exactly like simulated ones. Still to build: per-device API keys (devices cannot sign in) and an MQTT bridge
that calls the same `store()`.

## Known limits
- Only one API instance is supported; scaling out needs Postgres LISTEN/NOTIFY or Redis.
- Irrigation that is still being delivered when the API restarts is lost.
