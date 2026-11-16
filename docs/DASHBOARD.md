# Dashboard & weather (Phase 6)

## Pages
- `/dashboard?farm=<id>`: KPIs, per-zone trend chart, weather (48 h + 7 days), zone cards with live values,
  alerts (acknowledge / resolve), field activity and an irrigation log form.
- `/farms`, `/farms/<id>`: create, edit and delete farms (location, area, time zone); add and remove zones.
- Signing in now lands on the dashboard.

## API
| Endpoint | Purpose |
|---|---|
| `GET /farms/{id}/dashboard` | One-request summary: zones (active crop, latest moisture, temperature, humidity, pH), sensor counts, open alerts by severity, recent activity, water used in 7 days, 24 h reading counts and per-type stats |
| `GET /farms/{id}/series?sensor_type=&hours=&bucket_minutes=` | Per-zone `date_bin` averages with a min/max range, good-quality readings only. Automatic bucket size: 5 min (≤6 h), 15 min (≤48 h), 60 min (≤7 d), 180 min. At most 2,000 buckets |
| `GET /farms/{id}/weather[?refresh=true]` | Open-Meteo current conditions, next 48 h and a 7-day outlook in the farm's local days. Stored in `weather_data`, refreshed at most every 30 min |

## Weather rules
- Only coordinates are sent to Open-Meteo (no API key, no identifiers). Data is CC BY 4.0; the attribution is shown.
- `past_days=1` is requested so the farm's whole local "today" is present for time zones ahead of UTC.
- If Open-Meteo fails, the last stored forecast is shown and flagged stale, with the error. Nothing is invented.

## Charts
- Zone colours are a categorical palette checked with the dataviz validator against both dark surfaces
  (lightness, chroma, colour-blind separation, normal-vision separation and contrast all pass). Colours are assigned
  by zone id order, so a zone keeps its colour.
- No dual axes: temperature and rain chance are separate, synced charts. There is a legend for 2+ series,
  hover tooltips, a "View as table" option, and animation follows the reduced-motion setting.
- Severity is shown as icon + label + colour, never colour alone.
