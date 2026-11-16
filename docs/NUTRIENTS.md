# Fertilizer & chemical reduction (Phase 13)

`/nutrients` in the app. Rule-based and computed from the farm's own records. **Not a trained model.**
Code: `backend/app/domain/nutrients.py`, `backend/app/domain/chemicals.py`, `backend/app/services/nutrients.py`.

## Fertilizer plan (per zone, current crop cycle)

1. **Recommended dose (RDF)**, kg/ha N : P₂O₅ : K₂O. The farmer records the local value for the crop
   cycle, with its source (`PUT /crop-cycles/{id}/nutrient-target`): from the state Package of Practices
   or the Soil Health Card. Until then an **indicative** national-level general value is used for
   rice, wheat, maize (120:60:40), potato (150:80:100), tomato (120:60:60), onion and cotton (100:50:50),
   soybean (20:60:40) and groundnut (20:40:40). The plan is then marked INDICATIVE and its confidence is
   lower. Other crops need a recorded dose.
2. **Soil-test adjustment** (as used with Soil Health Cards): low ×1.25, medium ×1.00, high ×0.75,
   per nutrient, **only from lab values**. Probe/sensor ratings are shown but never change the dose.
3. **Credit** for fertilizer already logged on this cycle (cycle-linked, or zone records since planting):
   kg × grade % ÷ area. Grades are label N-P₂O₅-K₂O.
4. **Products**: DAP (18-46-0) for all P₂O₅, MOP (0-0-60) for K₂O, urea (46-0-0) for the N still needed
   after DAP's N. Per hectare, per zone and in 50 kg bags.
5. **Reduction shown**: the soil-test saving against the unadjusted dose, and any **surplus** already
   applied above the adjusted dose (advice: no more of that nutrient this season).
6. Notes: split N; fertigation on drip zones.

Confidence: 0.85 with a recorded dose (0.5 indicative) × 1.0 with lab N/P/K (0.75 without).

## Chemical use (per zone, current crop cycle)

From pesticide logs only: number of applications and types; product quantity per hectare by unit;
the share linked to a disease check (evidence-based sprays; `disease_detection_id` is now accepted when
logging); and pre-harvest interval (PHI) status against the expected harvest date, flagging conflicts.
**Reduction** is reported only against the zone's previous crop cycle, per hectare, when one exists.
Nothing is estimated when there is no earlier cycle.

## Pre-spray check

`GET /zones/{id}/chemicals/spray-check?pesticide_type&phi_days`. It is advisory and never blocks logging.

| Check | Warning when |
|---|---|
| Evidence (fungicide, bactericide) | no possible/uncertain disease check in the last 14 days |
| Rain | rain probability ≥ 40 % or ≥ 1 mm in any of the next 6 forecast hours |
| Wind | over 4 m/s (drift) |
| Heat | 30 °C or more |
| PHI | spray date + PHI is after the expected harvest |
| Repeat | the same type was applied in the last 7 days |

## Endpoints

| | |
|---|---|
| `GET /zones/{id}/nutrients/plan` | fertilizer plan with factors, products, surplus, saving, limitations |
| `PUT` / `DELETE /crop-cycles/{id}/nutrient-target` | record or clear the cycle's recommended dose and source |
| `GET /zones/{id}/chemicals/use` | pesticide use, PHI status, evidence share, comparison with the previous cycle |
| `GET /zones/{id}/chemicals/spray-check` | advisory pre-spray check |

Migration `0004` adds `crop_cycles.nutrient_target`.

## Limitations

- The indicative doses are general starting points; local recommendations differ by state, season,
  variety and irrigation.
- The ±25 % adjustment is the general Soil Health Card practice, not a crop-response (STCR) equation.
- Organic manures are credited at their full logged nutrient content. In practice only part is available
  in the season.
- Pesticide quantities are product amounts. Active-ingredient loads need concentrations, which are not
  recorded.
- The spray check uses the stored forecast, not conditions in the field right now, and does not replace
  the product label.
