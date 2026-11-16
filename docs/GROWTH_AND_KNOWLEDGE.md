# Crop growth, disease knowledge and twin health

## Disease knowledge layer (`backend/app/knowledge/diseases.py`)

One structured entry per pathogen for **every disease class the two installed models can output**: 27 entries
covering 31 model labels (some labels share an entry, e.g. early blight on potato and tomato). Each entry has
what it is, symptoms, why it occurs, environmental conditions, how it spreads, management, prevention,
sustainable practices, what to monitor, and when to seek expert advice.

* A test fails if any model label has no entry, or if any entry has an empty field or names a dose.
* Content is general guidance compiled from standard plant-pathology references. It names no products or doses
  and is marked **not agronomist-reviewed** in the API and the UI.
* It is attached **only** to a `possible_disease` result (one that passed every check). `uncertain` and refused
  results get no disease guidance; `possible_healthy` gets monitoring guidance.
* Saved disease checks expose `knowledge_key`, so history and the 3D twin open the same entry.

| Endpoint | |
|---|---|
| `GET /knowledge/diseases` | all entries |
| `GET /knowledge/diseases/{key}` | one entry (404 if unknown) |

**Multi-disease:** both models are single-label classifiers (softmax over classes). The app shows one prediction
and the top-5 candidates; it does not claim several simultaneous diseases. A multi-label model would plug in at
`app/vision/disease.py` (`run` / `screen`) with a list of labels mapped through the same `LABEL_MAP`.

## Crop growth stages (`backend/app/domain/growth.py`)

FAO-56 Table 11 stage lengths (initial, development, mid-season, late season) for 10 annual crops, scaled to the
crop cycle (its own sowing and expected harvest dates, else the catalogue cycle length, else the FAO total). The
8 user-facing stages map onto the FAO stages:

| Stage | FAO-56 stage | Boundary |
|---|---|---|
| Seed | sowing day | exact |
| Germination, Seedling | initial | split at 40 % of the initial stage: **approximation** |
| Vegetative | development | FAO |
| Flowering, Fruiting / Grain formation / Tuber bulking / Bulb formation / Pod filling / Boll formation | mid-season | split at 35 %: **approximation** |
| Maturity | late season | FAO |
| Harvest | last day | exact |

Perennials (banana, mango) and crops without FAO-56 lengths are refused with a 422 that lists the supported
crops. Nothing is drawn for them.

| Endpoint | |
|---|---|
| `GET /crops/{id}/growth` | stages for a crop |
| `GET /crop-cycles/{id}/growth` | stages for a zone's crop cycle, plus today's day and stage |

The **Crop growth** page (`/growth`) draws the stage returned by the API. The timeline widths are the real stage
lengths. *Play* holds each stage on screen in proportion to its length (60 ms per day). *Show today* jumps to the
cycle's current stage.

The current stage is also an input to recommendations: an `irrigation_soon` recommendation is raised to
**high** priority during flowering or yield formation (FAO-33: the most water-sensitive stages), with the stage
listed as a factor.

## 3D twin health

`GET /farms/{id}/twin` now returns, per zone, `health`: the latest saved disease check in that zone within 30
days (`disease` / `healthy` / `uncertain`, label, confidence, detection id, knowledge key), and the crop's
`stage_key` / `stage_name`. In the scene, a zone with a possible disease gets a yellow-brown crop tint, an orange
outline and a "possible disease" label. Clicking the zone shows the check and opens the disease information. An
uncertain check gets an amber outline only.
