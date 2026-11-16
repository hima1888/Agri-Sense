# Smart irrigation (Phase 12)

`/irrigation` in the app. A seven-day, rain-aware irrigation plan per zone from the FAO-56 root-zone
water balance. **Not a trained model**: every number follows from published crop and soil values, the
zone's moisture reading and the stored Open-Meteo forecast. Code: `backend/app/domain/irrigation.py`
(engine, pure functions) and `backend/app/services/irrigation_plan.py`.

## Method

Starting point: the Phase 8 water balance (field capacity, wilting point, root depth Zr, depletion
fraction p, Kc for the crop's growth stage, current depletion Dr).

For each forecast day (FAO-56 ch. 8):

    Dr(end) = Dr(start) + Kc × ET0 − effective rain − net irrigation,  bounded to [0, TAW]
    effective rain = 0.8 × rain on days with more than 2 mm, else 0

* **When:** on the day Dr(end) would pass RAW (= p × TAW, the stress threshold). If Dr is already past
  RAW, the first day is marked **now**.
* **Rain-aware deferral:** skip that day if effective rain in the next 2 days brings Dr back under RAW,
  and the soil would not reach the wilting point (TAW) first.
* **How much:** net = refill to field capacity, minus effective rain expected the next day (so the refill
  does not drain away). Gross = net ÷ application efficiency (drip 0.9, pivot 0.85, sprinkler 0.75,
  manual 0.7, furrow/flood 0.6; FAO Training Manual 4 typical values). Litres = gross mm × area m².
* **Time of day:** the calmest forecast hour between 05:00 and 09:00 local. Sprinkler and pivot zones get
  a drift warning above 4 m/s wind.
* **Rain-aware saving:** the same plan computed with forecast rain ignored, minus the real plan. It is an
  estimate over the forecast horizon, not a measured saving.

## Irrigation counted in the water balance (all phases)

Completed irrigation events logged **after** the latest moisture reading are added back to the soil water:
net mm = litres ÷ area m² × efficiency, capped at field capacity. This feeds the soil assessment (Phase 8),
recommendations (Phase 11) and the plan. Events without a volume, or zones without an area, cannot be
converted; the soil assessment says how many were skipped.

## Scheduling

`POST /zones/{id}/irrigation/schedule {"date"}` turns the plan's irrigation for that date into an
`irrigation_events` row (`status=scheduled`, `trigger=scheduled`, planned volume, time from the window).
It refuses (409) a date with no planned irrigation or one already scheduled. "Mark done" in the app sets the
event to `completed` with the planned volume via `PATCH /irrigation-events/{id}`. No valves are controlled:
there is no actuator hardware in this project.

## Water use

`GET /zones/{id}/irrigation/water-use?days=7|30`: litres from completed events, gross and net mm, and an
estimate of crop need (Σ Kc × ET0 − effective rain) from stored hourly weather. The applied ÷ need ratio is
shown **only** when stored weather covers every day in the window; otherwise the page says how many days
are covered. Events without a volume are listed as not counted.

## Endpoints

| | |
|---|---|
| `GET /zones/{id}/irrigation/plan` | plan, daily balance, windows, already-scheduled events, saving estimate, limitations |
| `GET /farms/{id}/irrigation/plan` | one line per zone |
| `POST /zones/{id}/irrigation/schedule` | schedule the plan's irrigation for a date |
| `GET /zones/{id}/irrigation/water-use` | applied vs estimated need |

## Limitations

* Uniform soil per zone; every irrigation assumed to wet the whole root zone.
* Forecast ET0 and rain become unreliable after 2 to 3 days. Re-plan daily.
* Durations need the system's flow rate, which is not recorded, so plans give volumes only.
* With simulated moisture sensors the plan demonstrates the method only, and the page says so.
* Water-use need is an estimate from forecast-model weather, not on-farm measurement.
