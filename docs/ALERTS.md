# Alerts (Phase 17)

`/alerts` in the app. Alerts are now raised **automatically** from the farm's data, as well as created by
hand (Phase 3). Code: `backend/app/domain/alert_rules.py` (rules, pure functions),
`backend/app/services/alerting.py` (snapshot and reconciliation), `backend/app/services/alert_runner.py`
(background loop).

## Rules

| Rule | True when | Severity | Category |
|---|---|---|---|
| `soil_dry` | zone water status is stress / severe (Phase 8 FAO-56 balance) | warning / critical | irrigation |
| `soil_saturated` | moisture above field capacity | info | soil |
| `sensor_silent` | active sensor with no reading for `silent_hours` (2 h) | warning | device |
| `sensor_bad_quality` | ≥ `bad_quality_share` (20 %) of the last hour's readings flagged (min. 3 readings) | warning | sensor |
| `heat_forecast` | forecast max ≥ `heat_c` (35 °C) in the next 48 h; critical at +5 °C | warning / critical | weather |
| `frost_forecast` | forecast min ≤ `frost_c` (2 °C); critical at ≤ 0 °C | warning / critical | weather |
| `heavy_rain_forecast` | ≥ `heavy_rain_mm` (50 mm) forecast in a day | warning | weather |
| `wind_forecast` | forecast wind ≥ `wind_ms` (12 m/s) in any hour | warning | weather |
| `disease_suspected` | a Phase 10 check flagged a possible disease within `disease_days` (3) | warning | disease |

Each farm can switch rules off and override thresholds (`GET`/`PUT /farms/{id}/alert-settings`, stored in
`farms.alert_settings`, migration `0006`).

## Lifecycle

Every evaluation reconciles the true conditions with the farm's open automatic alerts (context `source: rule`,
identified by a condition key such as `soil_dry:zone:5`):

* new condition → **raise** one alert (never a duplicate while it stays open or acknowledged);
* still true → keep it, updating severity and message if they changed (an escalation is pushed live);
* no longer true → **resolve automatically** (`context.auto_resolved`).

Acknowledged alerts stay acknowledged while the condition persists. Manual alerts are never changed
automatically. When a condition returns after being resolved, a new alert is raised.

## When it runs and how it reaches people

* A background evaluator runs for every farm with zones or sensors every `ALERT_INTERVAL_SECONDS` (300 s
  default; `ALERTS_ENABLED=false` turns it off). Each farm is evaluated in its own transaction.
* `POST /farms/{id}/alerts/evaluate` runs it now (the "Check now" button).
* Changes are pushed on the farm's existing live stream as `event: alert` (`raised`, `escalated`,
  `resolved`), after the database commit. The Alerts page shows them instantly and refreshes its list.
* **In-app only.** No e-mail, SMS or push-notification provider is configured, so none is sent.

## Limitations

- Rules use general thresholds; adjust them per farm and crop.
- Forecast rules depend on the stored Open-Meteo forecast, which is refreshed when the dashboard loads weather.
- Soil rules inherit Phase 8's assumptions, and simulated sensors are named in the message.
- No notifications leave the app (no e-mail/SMS/push provider).
- The background loop runs inside the API process. With several API instances each would evaluate, which is
  safe (keys de-duplicate) but redundant. Deployment (Phase 20) should run a single evaluator.
