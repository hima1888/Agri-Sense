# Federated learning (Phase 15)

`/federated` ("Shared learning") in the app. Farms that opt in train a shared model **without pooling
their data**: each farm trains on its own readings, and only model weights are averaged.
Code: `backend/app/domain/federated.py` (FedAvg, pure NumPy) and `backend/app/services/federated.py`.

## What the model does

It predicts the change in root-zone soil moisture over the next 6 hours (percentage points) from on-farm
sensors at hour *t*: moisture, air temperature, humidity, light, rainfall sensor and time of day. It is a
linear model, so its weights can be read directly. The features use **fixed physical scaling** (for example
(moisture − 25)/10), so no farm has to share means or variances of its data.

Samples are hourly means of `good` readings per zone with all five sensor types present, labelled with the
moisture 6 hours later.

## Protocol (FedAvg, McMahan et al. 2017)

1. An admin starts a run (`POST /federated/runs`: rounds, local steps, learning rate, L2).
2. Each active enrolled farm builds its dataset from **its own** readings only and keeps the most recent 20 %
   aside for testing (a time split).
3. Each round, every client starts from the global weights, takes *E* gradient steps on its own training data,
   and returns only its weights, sample count and training error.
4. The server averages the weights, weighted by sample count, and stores one `federated_client_updates` row
   per client per round (weights + training MSE), never readings or features.
5. The result is stored as a `model_versions` row (`status=staging`, weights in `input_spec`).

A run needs **at least 2 farms with 30+ samples**. Otherwise it is recorded as `failed` with the reason.

## Evaluation

On each farm's held-out recent data, three predictors are compared, overall and per farm:

| Predictor | Meaning |
|---|---|
| Persistence | moisture stays the same (the baseline to beat) |
| Local-only | the same model trained only on that farm's data, same total steps |
| Federated | the final global model |

Each farm owner sees the overall numbers and **only their own farm's** numbers; admins see all farms.
The zone forecast (`GET /zones/{id}/federated/forecast`) shows the model's typical error next to the baseline,
and warns "do not use it for decisions" when the model does not beat the baseline.

**Current finding (dev data):** on the test farm alone (63 simulated samples), a model trained on the older
80 % predicted the newest 20 % worse than "no change" (MAE 0.50 vs 0.44 points). The app reports this rather
than hiding it. More farms and real data are needed before the model is useful.

## Endpoints

| | |
|---|---|
| `GET /farms/{id}/federated` | enrollment, what is shared, local sample count, runs (own metrics only) |
| `POST /farms/{id}/federated/enroll` / `leave` | opt in / out (owner) |
| `POST` / `GET /federated/runs`, `GET /federated/runs/{id}` | start / list / inspect runs (admin) |
| `GET /zones/{id}/federated/forecast` | 6-hour forecast from the latest model, with its error vs the baseline |

## Limitations

- **Simulated federation:** all clients run inside this one backend. The farm boundary is enforced in code (a
  client function only reads its own farm), not by separate devices or networks.
- **Not a formal privacy guarantee:** model updates can leak information about the training data. No differential
  privacy or secure aggregation is applied. Per-round client weights are stored server-side.
- **Simple model:** a linear model that ignores irrigation events and weather forecasts.
- **Admin-run only:** runs are started by an admin, not on a schedule.
- **Dev data is simulated:** the dev database has one farm with (simulated) sensor data, so a real two-farm run
  was exercised in the automated tests only.
