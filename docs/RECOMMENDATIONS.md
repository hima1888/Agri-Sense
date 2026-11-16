# Recommendations (Phase 11)

`/advice` in the app. **Rule-based, not a trained model.** Each recommendation is a transparent IF-THEN
over data the app already holds, and carries what to do, why (factors with values and sources), a
confidence, and limitations. Code: `backend/app/domain/recommend_rules.py` (rules, pure functions) and
`backend/app/services/recommend.py` (data gathering and storage).

## Inputs

| Input | From |
|---|---|
| Root-zone water balance, pH, N/P/K, organic carbon, EC, crop | Phase 8 soil assessment per zone (lab tests win over sensors) |
| Next 72 h hourly forecast: rain, temperature, humidity, wind | Stored Open-Meteo forecast (refresh it from the dashboard) |
| Possible diseases in the last 14 days | Phase 10 disease checks with outcome `possible_disease` |
| Silent sensors | Active sensors with no reading for 2 h or more |

## Rules

| Rule | Fires when | Advice | Priority | Rule certainty |
|---|---|---|---|---|
| `irrigate_now` | water status stress / severe, no big rain coming | refill to field capacity: net mm, gross mm (÷ application efficiency), litres if zone area known | high / critical | 0.95 |
| `hold_irrigation_rain` | stressed, but ≥ 10 mm rain in 48 h and 80 % of it covers the deficit | hold, re-check in 24 h | medium | 0.70 |
| `irrigation_soon` | stress projected within 2 days | plan irrigation | medium | 0.85 |
| `skip_irrigation_wet` | moisture above field capacity | skip | low | 0.90 |
| `nutrient_low:{n,p,k}` | N/P/K rated low (Soil Health Card) | lab value: apply per SHC/extension recommendation; probe value: get a lab test first. **No dose** (Phase 13) | medium (lab) / low (probe) | 0.80 |
| `organic_matter_low` | organic carbon < 0.5 % | compost/FYM, residue retention, green manure | medium / low | 0.80 |
| `ph_out_of_range` | pH outside crop (or 6.0–7.5) range | ask the lab for lime / gypsum requirement; no rate | medium / low | 0.80 |
| `salinity` | EC ≥ 1 dS/m | test irrigation-water EC, leaching where drainage allows | medium / high | 0.80 |
| `soil_test_needed` | no lab test within 365 days | get a lab test | low | 1.00 |
| `confirm_suspected_disease` | a possible disease was flagged in the last 14 days | scout to confirm; lists suitable spray windows **only for if treatment is confirmed** | medium | 0.90 |
| `humid_weather_scouting` | ≥ 12 of the next 72 h at RH ≥ 90 % and 15–30 °C | scout after the humid spell (generic proxy, not a disease model) | low | 0.50 |
| `heat_stress` | forecast max ≥ 35 °C in the next 3 days | early-morning irrigation, avoid spraying in heat | medium | 0.75 |
| `sensors_silent` | active sensors silent ≥ 2 h | check sensors | medium | 1.00 |

Spray window: daylight hour (06–18 local) with wind < 4 m/s, temperature < 30 °C and rain probability
< 40 % for that hour and the next 5.

Application efficiencies (FAO Irrigation Water Management, Training Manual 4, typical values): drip 0.9,
sprinkler 0.75, furrow/flood 0.6, manual 0.7, unknown 0.7. 1 mm over 1 m² = 1 L.

## Confidence

`confidence = data confidence × rule certainty`. Data confidence comes from the inputs (for example the
water balance confidence from Phase 8, × 0.85 when no forecast is stored); rule certainty is the fixed,
documented value above. Both numbers are shown with each recommendation. They are judgements, not fitted
probabilities.

## Storage and lifecycle

`POST /farms/{id}/recommendations/generate` stores advice in `ai_recommendations` (new columns `rule`
and `factors`, migration `0003`). One pending row per (zone, rule): re-generating refreshes it instead of
duplicating, and pending advice whose rule no longer fires, or that has passed `expires_at`, becomes
`expired`. The farmer can accept, reject or mark advice applied (`POST /recommendations/{id}/respond`;
pending → accepted/rejected/applied, accepted → applied/rejected). Decided advice is kept as history.
`GET /farms/{id}/recommendations/preview` computes without storing.

## Limitations

- Advice is only as good as its inputs; simulated sensor data is flagged on every affected recommendation.
- No fertilizer, lime or pesticide doses: those need lab requirement tests and Phase 13.
- Thresholds are general published values, not tuned to this farm or its varieties.
- The irrigation amount assumes the whole zone has the same soil. Completed irrigation logged since the last moisture reading is counted (Phase 12).
- Disease follow-up depends on Phase 10 models that were wrong on most field photos in testing; the advice is
  to scout and confirm, never to treat on the model's word.
