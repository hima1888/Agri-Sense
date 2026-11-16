# Yield prediction (Phase 14)

`/yield` in the app. A **water-limited** yield estimate with a range, from a published method and this
farm's own data. **Not a trained model.** There are no recorded harvests to train or validate one yet, so
the page says that its accuracy is unknown until harvests are back-tested.
Code: `backend/app/domain/yield_model.py`, `backend/app/services/yield_service.py`.

## Method

FAO Irrigation and Drainage Paper 33 (restated in FAO-66):

    1 − Ya/Ym = Ky × (1 − ETa/ETc)

| Term | From |
|---|---|
| **Ym**, attainable (water-unstressed) yield | the farmer, with a source (`PUT /crop-cycles/{id}/yield-reference`), or else the best per-hectare yield of the same crop in this farm's harvested cycles. **Never invented.** Without either, no estimate is made. |
| **Ky**, seasonal yield-response factor | FAO-33 table: maize 1.25, wheat 1.15, tomato 1.05, potato 1.10, onion 1.10, cotton 0.85, soybean 0.85, groundnut 0.70 and others (`GET /yield/ky`). Rice is not in FAO-33, so it gets no estimate. |
| **ETa/ETc** | the FAO-56 water-stress coefficient Ks = (TAW − Dr)/((1 − p)·TAW) when Dr > RAW (else 1), from the daily mean of good soil-moisture readings and lab/field moisture tests, weighted by the growth-stage Kc as a proxy for daily ETc |

Days without a moisture measurement are unknown, which gives three cases:

* **high**: unknown past days and the rest of the season unstressed;
* **central**: unknown past days like the measured days, rest of the season unstressed (if irrigated as planned);
* **low**: unknown past days and the rest of the season like the measured days.

The page shows coverage (measured days and ETc-weighted share of the season). When coverage is under 50 % it
warns that a narrow range means "no stress seen on the few measured days", not a precise forecast.
Confidence = (0.3 + 0.6 × coverage, max 0.9) × (1.0 for own-harvest Ym, 0.85 otherwise) × 0.5 if moisture is simulated.

## Saving and back-testing

`POST /zones/{id}/yield/predictions` stores the estimate as an `ai_predictions` row (type `yield`, linked to
the crop cycle, with factors, limitations and inputs). `GET /farms/{id}/yield/backtest` compares, for each
harvested cycle with a recorded yield, the last estimate saved **on or before harvest day** with the actual
yield: error %, whether it fell inside the range, and the mean absolute error. This is the only real accuracy
measure. It will be empty until harvests are recorded.

## Endpoints

| | |
|---|---|
| `GET /zones/{id}/yield` | estimate, range, factors, coverage, confidence, limitations |
| `POST` / `GET /zones/{id}/yield/predictions` | save / list estimates |
| `GET /farms/{id}/yield/backtest` | saved estimates vs actual yields |
| `PUT` / `DELETE /crop-cycles/{id}/yield-reference` | record / clear the attainable yield and its source |
| `GET /yield/ky` | the Ky values used |

Migration `0005` adds `crop_cycles.yield_reference`.

## Limitations

- Water stress only. Nutrients, pests, diseases, weeds, heat at flowering, lodging and harvest losses are
  not modelled (recent possible-disease checks are mentioned, not used).
- Ky values are seasonal FAO-33 averages. Stress timing within a stage is approximated with Kc weights.
- Uniform soil per zone, and the root-zone limits from Phase 8.
- On the demo farm the moisture history is simulated and covers about 1 % of the season, so estimates there
  only demonstrate the method.
