# Soil intelligence (Phase 8)

`/soil` in the app; `GET /api/v1/zones/{id}/soil` in the API. Every assessment is computed on request
from stored records (lab tests, soil profile, sensor readings, crop cycle, stored weather forecast).

**This is rule-based scoring against published references, not a trained model.** Every response
carries its method, per-value sources, a confidence with reasons, and a list of limitations.

## Method

| Part | Method | Reference |
|---|---|---|
| Soil water limits | Measured FC/WP from the soil profile, else the texture midpoint, else an assumed loam | FAO-56 Table 19 |
| Crop parameters | Kc (initial / mid / end), root depth Zr, depletion fraction p, per crop → category → default | FAO-56 Tables 12, 22 |
| Water balance | TAW = (FC − WP)·Zr; RAW = p·TAW; Dr = (FC − θ)·Zr | FAO-56 ch. 8 |
| Projection | Dr(t+1) = Dr + Kc·ET0 − 0.8·rain (rain counted only above 2 mm/day), up to the stored forecast | FAO-56; Open-Meteo ET0 |
| N, P, K | mg/kg × 2.24 → kg/ha, rated low/medium/high | Soil Health Card limits (N 280/560, P 10/25, K 110/280) |
| Organic carbon | low < 0.5 %, high > 0.75 % | Soil Health Card |
| pH | Crop optimum if recorded, else 6.0–7.5 | — |
| Salinity | EC classes 1 / 2 / 4 dS/m | general classes |

Water status: `above_field_capacity` (θ > FC + 1 %), `adequate` (Dr ≤ RAW), `stress` (RAW < Dr < TAW), `severe` (Dr ≥ TAW, i.e. at wilting point).

**Index** = weighted mean of the component scores actually assessed (pH 0.20; N, P, K, OC 0.15 each;
salinity 0.10; water 0.10), renormalised. Rated good ≥ 75, fair ≥ 50, poor < 50. `factors` are
sorted by impact = index points lost = (weight / assessed weight) × (100 − score).

**Confidence** per value: lab test ≤ 180 days 0.9 (older lower), simulated sensors low. Overall
confidence is scaled by coverage, and `confidence_reasons` says why.

## Data sources and priority

A lab / field-kit test from the last 365 days wins over sensors for every value it contains. Otherwise
24 h means of `good` sensor readings are used. Anything from a simulated sensor is suffixed
`(simulated)`, sets `uses_simulated_data`, and adds a SIMULATED limitation; the UI shows a banner.

## Endpoints

- `GET /zones/{id}/soil` — full assessment.
- `GET /farms/{id}/soil` — one-line summary per zone.
- `POST /zones/{id}/soil/assessments` — save the current assessment to history (an `ai_predictions` row,
  `prediction_type = soil_health`, with factors, limitations and an input snapshot; audited). 422 if nothing
  could be assessed.
- `GET /zones/{id}/soil/assessments` — saved history, newest first, paged.

Inputs come from the existing `POST /zones/{id}/soil-measurements` and `POST /zones/{id}/soil-profiles`,
both of which the soil page has forms for.

## Limitations

- Reference values are general; local extension guidance and varieties differ.
- Low-cost NPK probes estimate from conductivity; they do not measure plant-available nutrients.
- kg/ha conversion assumes a 0–15 cm layer at ≈ 1.49 g/cm³.
- The projection ignores irrigation, capillary rise and deep percolation, and is only as long as the stored forecast.
- No fertilizer or irrigation recommendations here: those are Phases 12–13.
