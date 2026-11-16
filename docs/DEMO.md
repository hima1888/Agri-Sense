# Demo guide (Phase 21)

A 7–8 minute walkthrough for a presentation or recording. Each step says what to click, what to say, and what
to be honest about. Photos for the vision steps are in `backend/tests/fixtures/` (sources and licences in
`README.txt` there).

## Before you start (5 minutes)

```bash
docker compose up -d                      # app database
npm run auth:start                        # local Supabase Auth (repo root)
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
cd frontend && npm run dev                # http://localhost:5173
```

Or the production containers instead of the last two lines: `docker compose -f docker-compose.prod.yml
--env-file .env.production up -d` and open http://localhost:8080 (see DEPLOYMENT.md).

Sign in once, open the dashboard, and leave it for a minute so the simulator has produced fresh readings.
Check **System status** (`/status`): every service should be green.

## Script

| # | Page | Show | Say |
|---|---|---|---|
| 1 | Landing | the loop *See → Sense → Analyze → Predict → Recommend → Act → Learn* | "One platform from sensing to action, and every AI output explains itself." |
| 2 | Dashboard | KPIs, weather, zones, the **Simulated** label | "Readings stream live over SSE. There is no hardware attached, so the data is simulated, and the app says so wherever it appears." |
| 3 | Twin | rotate, click a zone | "The 3D twin is built from the farm's real zones and colours them from live moisture." |
| 4 | Soil | index, confidence, factors, limitations | "FAO-56 water balance plus the soil test. It shows its confidence, the factors behind it, and what it can't know." |
| 5 | Vision → produce | upload `banana.jpg` | "An ONNX model running on the server; the heat-map shows what it looked at. Unsupported photos are refused, not guessed." |
| 6 | Vision → disease | upload `potato_late_blight_field.jpg` | "Two leaf-disease models with crop routing. They were trained on lab photos. In our own test they got none of five real field photos right, so the result may be wrong, and the page shows its confidence and limits rather than hiding that." |
| 7 | Advice | a recommendation with evidence | "Rule-based, so every recommendation traces back to the data that triggered it." |
| 8 | Irrigation | 7-day plan, rain skip, water saved | "Plans skip irrigation when rain is forecast. The saving is an estimate: the same plan with the forecast rain ignored, minus this plan." |
| 9 | Nutrients | fertilizer plan, pre-spray check | "Doses adjusted by the soil test (Soil Health Card ±25 % rule); the spray check blocks spraying before rain or in wind." |
| 10 | Yield | range, not a single number | "FAO-33 water-limited yield, given as a range. It back-tests against real harvests once they are entered." |
| 11 | Federated | rounds, participating farms | "FedAvg: each farm trains locally, only weights are shared. On today's data the model does worse than simply assuming 'no change', and the page warns not to use it for decisions; that is the honest result." |
| 12 | Alerts | **Check now**, live alert | "Rules run every five minutes and push alerts live; duplicates are merged and alerts resolve themselves." |
| 13 | Analytics | period comparison, save report, CSV | "Sustainability indicators against the previous period, saved as a printable report." |

## Honest answers to likely questions

* **Is the sensor data real?** No: there is no hardware attached, so a simulator generates it, and it is labelled
  everywhere. The ingest path takes real sensors without UI changes.
* **How accurate are the models?** The produce model is MobileNetV2 (ImageNet); the disease models report their
  published accuracy (self-reported, from lab images). In our own test both got 0 of 5 field photos right, so no field
  accuracy is claimed. See VISION.md and DISEASE_MODELS.md.
* **Is it secure?** Supabase sign-in, every query scoped to the owner, security headers, rate limits, upload size
  limits; see SECURITY.md.
* **Is it tested?** 229 backend tests (94.5 % coverage), 86 frontend tests, 12 end-to-end browser tests, CI
  workflow; see TESTING.md.

## If something goes wrong during the demo

* Blank dashboard: the backend is not running, so check `/status`.
* "Weather unavailable": Open-Meteo is unreachable (no internet). Everything else still works.
* Sign-in fails: `npm run auth:start` in the repo root, then reload.
