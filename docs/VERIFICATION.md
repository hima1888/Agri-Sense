# Real functionality verification report

All results below come from the real stack: browser → React → FastAPI → ONNX Runtime models / PostgreSQL →
browser. No mocked responses. Photos are in `backend/tests/fixtures/` (sources and licences in `README.txt`).
Every record created during testing was deleted afterwards (disease-check history: 0 before, 0 after).

## Model checks (`app/vision/disease.py`, run directly)

| Check | crop-leaf-diseases-vit | plantvillage-mobilenet-v2 |
|---|---|---|
| File exists, size | `crop_leaf_vit.onnx`, 22,287,747 B | `plantvillage_mnv2.onnx`, 9,227,018 B |
| SHA-256 matches pinned value | yes | yes |
| Loads in ONNX Runtime (CPU) | yes | yes |
| Input | `pixel_values [batch, 3, 224, 224]` | same |
| Preprocessing output | (1, 3, 224, 224) float32, range −1.00…0.95 | (1, 3, 224, 224) float32, range −1.00…0.99 |
| Output classes = label table | 13 = 13 | 38 = 38 |
| Softmax sums to 1, all finite | 1.000000, yes | 1.000000, yes |
| Same input twice gives the same confidence (no randomness) | 0.8106 = 0.8106 | — |

Both models are **single-label** classifiers. Multi-disease detection is not claimed; see GROWTH_AND_KNOWLEDGE.md
for where a multi-label model would plug in.

## Journey tests

| # | Feature | Exact test | Input | Actual output | Model | Endpoint | Database | Result |
|---|---|---|---|---|---|---|---|---|
| 1 | Upload → model → result → UI | Playwright: upload in the browser, click "Check leaf", read the result card | `potato_late_blight_field.jpg`, crop "tomato" | HTTP 201, `possible_disease`, **Tomato: Late blight**, confidence 0.6235, margin 0.4163; UI shows result, checks, candidates, and the Late blight knowledge panel | plantvillage-mobilenet-v2 | `POST /farms/{id}/vision/disease-checks` | row saved (`disease_detections`, `knowledge_key = late_blight`), then deleted | **PASS** |
| 2a | Non-plant photo rejected | same flow | `banana.jpg`, crop "tomato" | `not_a_leaf` (produce model recognised banana); not saved | produce model + router | same | nothing stored | **PASS** |
| 2b | Unrecognisable leaf rejected | same flow | `wheat_leaf_rust_field.jpg`, crop "wheat" | `cannot_identify`: model's top answer was **Corn: Common rust 65.4 %**, not wheat, so no answer given | crop-leaf-diseases-vit | same | nothing stored | **PASS** |
| 2c | Unsupported crop | API | corn photo, crop "mango" | `unsupported_crop`, lists supported crops | none run | same | nothing stored | **PASS** |
| 2d | Low confidence | API | `potato_late_blight_field.jpg`, crop "potato" | `cannot_identify`: top-1 "Invalid" 36.6 % vs "Potato: Early blight" 36.3 % (margin 0.0033) | crop-leaf-diseases-vit | same | nothing stored | **PASS** (correct refusal) |
| 3 | Healthy leaf | API + regression test | `tomato_healthy_field.jpg` (CC0, Wikimedia Commons), crop "tomato" | HTTP 201, **`not_a_leaf`**: the produce gate read it as "fig" (35.3 %); not saved. Diagnostic with the gate bypassed: the disease model says **Tomato: Late blight 77.0 %** (a false positive that would pass the thresholds) | gate: mobilenetv2-12; disease: plantvillage-mobilenet-v2 | same | nothing stored | **FAIL**: no healthy result. The failure is safe: the leaf is refused, never reported as diseased |
| 4 | Diseased leaf | API | `corn_rust_field.jpg`, crop "corn" | `possible_disease` **Corn: Gray leaf spot**, 0.8106. **This is wrong**: the photo shows common rust | crop-leaf-diseases-vit | same | saved, then deleted | **PASS for the pipeline; the prediction is incorrect** |
| 5 | Crop growth from data | Playwright + API | Tomato (catalogue, 110 days) | 8 stages: Seed 0, Germination 1–10, Seedling 11–24, Vegetative 25–57, Flowering 58–69, Fruiting 70–90, Maturity 91–110, Harvest 110; Mango → HTTP 422 "perennial … Not modelled" | FAO-56 Table 11 | `GET /crops/{id}/growth`, `GET /crop-cycles/{id}/growth` | reads crops, crop cycles | **PASS** |
| 6 | 3D twin reflects state | Playwright: disease check saved to zone "North Field", then twin API and twin page | late-blight photo, crop tomato, zone North Field | twin zone `health = {state: disease, knowledge_key: late_blight, detection_id: <new>}`; other zone unchanged; zone details show "Possible disease: Tomato: Late blight" and open the disease information | plantvillage-mobilenet-v2 | `GET /farms/{id}/twin` | reads `disease_detections` per zone | **PASS** |
| 7 | Existing suites | see below | | | | | | **PASS** |

## Full suites (final run)

| Suite | Result |
|---|---|
| Backend pytest | all passed, coverage **94.35 %** (floor 90 %) |
| Ruff lint / format, mypy, alembic check | clean / clean / clean / no changes |
| Frontend Vitest | **89 passed**, coverage lines 85.7 %, statements 82.0 %, functions 75.9 %, branches 68.1 % (all above floors) |
| ESLint, tsc, production build | clean, clean, built |
| Playwright E2E | **16 passed** (12 earlier flows plus 4 new journey tests) |

## Known limitations

* **Field accuracy is poor and unmeasured.** On the 5 field photos here: 1 correct (late blight), 1 wrong (rust → gray
  leaf spot), 2 correctly refused, and 1 healthy leaf refused (it would otherwise have been called late blight at 77 %).
  The app cannot currently confirm that a field leaf is healthy. Confidence is the uncalibrated softmax probability.
* The produce gate's refusal reason can be wrong ("looks like fig" for a leaf); its decision to refuse was the safe one.
* Correct answers depend on the user choosing the right crop: the late-blight potato photo is answered only when
  screened as tomato, because the potato route uses the ViT model, which refuses it.
* The disease knowledge is general guidance, not reviewed by a local agronomist (shown in the UI).
* Growth stage boundaries inside the FAO-56 initial and mid-season stages are approximations; perennials are not modelled.
* Sensor data is simulated (labelled everywhere); no physical hardware is connected.
* Refused checks return HTTP 201 although nothing is stored (`saved: false` says so).

## Remaining work

1. **What is missing for reliable disease detection:** a disease model trained on *field* photos (including healthy
   field leaves). Both installed models were trained on lab photos and do not generalise. Replacing the model needs no
   app changes (same ONNX interface).
2. A labelled field-photo test set to measure real accuracy; then tune or replace the models.
3. Agronomist review of the knowledge entries.
