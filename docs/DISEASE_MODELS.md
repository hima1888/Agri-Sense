# Disease models: verification record (Phase 10, pre-integration)

Status: **integrated (Phase 10)** with the rules below, as implemented in `backend/app/vision/disease.py`.
Conversion ran once in a throwaway Python env (torch 2.15.0+cpu, transformers 5.23.0, onnx 1.23.2)
outside the repository. The application will need only `onnxruntime`, `numpy` and `pillow` (already installed).

## Summary

| | Crop ViT (primary) | PlantVillage MobileNetV2 (fallback) |
|---|---|---|
| Source | `wambugu71/crop_leaf_diseases_vit` (Hugging Face) | `linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification` |
| Weights used | `model.safetensors`, sha256 `1f91c903…14b2` | `model.safetensors` from HF conversion-bot PR #2, sha256 `5c692c84…be4b0` |
| Licence | MIT (metadata); card text also says Apache 2.0 | "other" (unspecified) |
| Architecture | ViT-tiny (patch 16, hidden 192, 12 layers), 5.53 M params, fine-tuned from ImageNet | MobileNetV2 1.0, 2.27 M params, fine-tuned from `google/mobilenet_v2_1.0_224` |
| Crops | corn (maize), potato, rice, wheat | apple, blueberry, cherry, corn, grape, orange, peach, bell pepper, potato, raspberry, soybean, squash, strawberry, tomato |
| Classes | 13 (12 crop/disease + `Invalid`) | 38 |
| Input | `pixel_values` float32 `[batch, 3, 224, 224]` | `pixel_values` float32 `[batch, 3, 224, 224]` |
| Preprocessing | RGB → resize to 224×224 (bilinear, no crop) → /255 → (x − 0.5) / 0.5 | RGB → resize shortest edge to 256 (bilinear; long side **floored**) → centre-crop 224 → /255 → (x − 0.5) / 0.5 |
| Output | `logits` float32 `[batch, 13]` | `logits` float32 `[batch, 38]` |
| Confidence | softmax over the 13 logits (uncalibrated) | softmax over the 38 logits (uncalibrated) |
| ONNX | opset 17, IR 8, dynamic batch; passes `onnx.checker` | opset 17, IR 8, dynamic batch; passes `onnx.checker` |
| ONNX file | 22,287,747 bytes, sha256 `6a048bf3…0c00` | 9,227,018 bytes, sha256 `c5021fe9…cb5e` |
| CPU latency (this PC, single image) | ~70–310 ms | ~5–120 ms |
| Published accuracy | **98 %** self-reported on a 20 % split of its own training data (public + private images) — unverifiable | **Conflicting:** model card 95.41 %; the repo's own `eval_results.json` 78.58 % (eval loss 1.05). Kaggle "New Plant Diseases" (PlantVillage, lab photos). |

ViT classes: Corn Common Rust, Corn Gray Leaf Spot, Corn Healthy, Potato Early Blight, Potato Healthy,
Potato Late Blight, Rice Brown Spot, Rice Healthy, Rice Leaf Blast, Wheat Brown Rust, Wheat Healthy,
Wheat Yellow Rust, Invalid.

PlantVillage classes: Apple (scab, black rot, cedar apple rust, healthy); Blueberry healthy; Cherry
(powdery mildew, healthy); Corn (Cercospora/gray leaf spot, common rust, northern leaf blight, healthy);
Grape (black rot, esca, Isariopsis leaf spot, healthy); Orange citrus greening; Peach (bacterial spot,
healthy); Bell pepper (bacterial spot, healthy); Potato (early blight, late blight, healthy); Raspberry
healthy; Soybean healthy; Squash powdery mildew; Strawberry (leaf scorch, healthy); Tomato (bacterial spot,
early blight, late blight, leaf mold, Septoria leaf spot, spider mites, target spot, yellow leaf curl
virus, mosaic virus, healthy).

## Verification performed

1. **Downloads:** file hashes match Hugging Face's published LFS hashes.
2. **No pickle in production:** the PlantVillage repo's main weights are a pickle (`pytorch_model.bin`).
   We used HF's official safetensors conversion (PR #2) and confirmed it is **bit-identical** to the
   pickle (314 tensors, same keys, max difference 0.0). The pickle was opened only in the throwaway env,
   with PyTorch's restricted `weights_only=True` loader.
3. **ONNX parity:** on 8 random inputs per model, ONNX Runtime logits match PyTorch within
   9.1e-6 (ViT) and 6.3e-6 (MobileNetV2); top-1 agrees 8/8 for both.
4. **Preprocessing:** a PIL + NumPy implementation (what the app will use) matches the official HF image
   processors **exactly** (max difference 0.0) on all 11 sample images. A first version that *rounded*
   the long side for PlantVillage differed by up to 0.87; HF floors it, which is now documented above.
5. **Labels:** label lists taken from each model's `config.json` (`id2label`), checked equal after export.

## Basic inference test (11 images — a smoke test, not an accuracy measurement)

✓ = correct crop and disease as top-1. "n/a" = crop not in that model.

| Image | Truth | Crop ViT top-1 | PlantVillage top-1 |
|---|---|---|---|
| PlantVillage lab | Corn common rust | ✓ Corn Common Rust 100.0 % | ✓ Corn Common Rust 99.9 % |
| PlantVillage lab | Potato healthy | ✓ Potato Healthy 100.0 % | ✓ Healthy Potato 96.8 % |
| PlantVillage lab | Potato late blight | ✓ Potato Late Blight 99.9 % | ✓ Potato Late Blight 66.8 % |
| PlantVillage lab | Tomato early blight | n/a — said Potato Early Blight 99.9 % | ✓ Tomato Early Blight 83.9 % |
| PlantVillage lab | Tomato healthy | n/a — said Potato Healthy 99.8 % | ✓ Healthy Tomato 100.0 % |
| Field (Wikimedia) | Corn common rust | ✗ Corn Gray Leaf Spot 71.9 % (rust 27.6 %) | ✗ Corn Gray Leaf Spot 100.0 % |
| Field | Potato late blight | ✗ Potato Early Blight 49.2 % | ✗ Tomato Late Blight 59.4 % (right disease, wrong crop) |
| Field | Tomato early blight | n/a — `Invalid` 36.4 % (correct rejection) | ✗ Grape Black Rot 52.0 % |
| Field | Wheat leaf (brown) rust | ✗ Corn Common Rust 72.2 % (wheat brown rust 5.1 %) | n/a — said Corn Common Rust 67.1 % |
| Field | Wheat stripe (yellow) rust | ✗ Rice Leaf Blast 42.6 % (yellow rust 33.4 %) | n/a |
| Non-leaf | Banana (Phase 9 fixture) | ✗ Rice Brown Spot **89.9 %** (`Invalid` only 5.0 %) | ✗ Bell Pepper Bacterial Spot 40.9 % |

Sample sources: PlantVillage-Dataset (GitHub `spMohanty/PlantVillage-Dataset`, `raw/color`), Wikimedia
Commons (public domain / CC BY / CC BY-SA). The PlantVillage images may be in that model's training
set, so its lab results say nothing about accuracy. No rice sample was tested.

## What this shows

- Both models work well on clean, lab-style single-leaf photos of crops they know.
- **Neither model got any of the 5 field photos right** (0/5 each). Field accuracy is unknown and
  likely low; the published accuracy figures do not describe field use.
- **High confidence does not mean correct:** wrong answers at 72–100 % occurred. A confidence threshold
  alone is not a safe gate.
- **Out-of-scope inputs are not reliably rejected:** the ViT gave a banana 89.9 % "Rice Brown Spot", and
  called tomato leaves potato at 99.8–99.9 %. Its `Invalid` class only caught one of the out-of-scope images.
- Models confuse crops (tomato ↔ potato, wheat → corn), so the app should not trust a model's crop guess.

## Integration rules (implemented)

1. **Crop comes from the user/zone, not the model.** Route by the zone's active crop or a crop the user
   picks: ViT for corn/potato/rice/wheat; PlantVillage only for crops the ViT lacks (tomato, apple, grape,
   pepper, …); refuse crops neither model covers.
2. Report the model's top-1 across **all** its classes. If that top-1 is a different crop (or ViT `Invalid`),
   answer "cannot reliably identify" instead of re-scoring within the chosen crop.
3. Only call a result a possible disease when top-1 ≥ 0.60 **and** the gap to the second class is ≥ 0.20;
   otherwise "uncertain", showing the candidates. Run the Phase 9 check too and warn when the photo looks
   like produce rather than a leaf.
4. Every response names the model, its version, its raw softmax confidence and these limitations; it is
   worded as "possible", with advice to confirm with an agronomist or extension officer before any treatment.
5. These rules reduce but do not remove wrong answers. Applied to the samples above they would still
   report the field corn photo as "possible gray leaf spot" (71.9 %, wrong), while turning the banana,
   tomato-as-potato, both wheat photos and the field potato photo into refusals or "uncertain".
6. Thresholds are starting points chosen from this small test, **not** tuned. They should be re-tuned once
   labelled field photos from real farms exist.

## Sensitivity to image size (found during integration)

The same field photos give different answers at different resolutions:

| Photo | 960 px | 480 px | 224 px |
|---|---|---|---|
| Field corn common rust (crop = corn) | possible disease, Gray leaf spot 71.9 % (wrong) | Gray leaf spot 81.1 % (wrong) | Gray leaf spot **97.0 %** (wrong) |
| Field potato late blight (crop = potato) | uncertain (Early blight 49.2 %) | cannot identify | — |

Smaller photos made the wrong corn answer *more* confident. Confidence must not be read as accuracy.

## In the app

* `/vision?tab=disease`: photo + crop (or a zone with a crop cycle). The result shows the outcome, the model
  that answered and its raw confidence and margin, every rule check (passed/failed), the candidates, the
  colour-heuristic affected area (possible-disease only) and the limitations.
* API: `GET /vision/disease/models`, `POST/GET /farms/{id}/vision/disease-checks`,
  `GET/DELETE /vision/disease-checks/{id}`, `GET /vision/disease-checks/{id}/image`.
* `possible_disease`, `possible_healthy` and `uncertain` are stored in `disease_detections` (explanation JSON
  holds the outcome, model, checks and limitations; `model_versions` rows are created with status `staging`).
  Refusals (`cannot_identify`, `not_a_leaf`, `unsupported_crop`) are returned but not stored.
* Models are loaded only from `backend/ml_models/*.onnx` after a SHA-256 check; no pickle and no PyTorch in the app.
  To rebuild them, run `backend/scripts/convert_disease_models.py` in a separate throwaway environment.


## Fruit: orange-fruit model (added later)

* Source: [dima806/orange_fruit_disease_detection](https://huggingface.co/dima806/orange_fruit_disease_detection),
  Apache-2.0, ViT-base/16 (85.8 M parameters), classes: citrus canker, healthy, melanose. Self-reported 97.9 %
  on 3,600 images of its own dataset (not independently verified).
* No openly licensed model covering disease on many fruits was found; this is the only fruit-disease model used.
* Conversion: `backend/scripts/convert_fruit_model.py` exports ONNX opset 17 and quantises weights to int8
  (343 MB to 87 MB) so it fits git and a 512 MB server. On 16 random inputs int8 and PyTorch agree on every
  top class (largest probability difference 0.013), and they agree on every real photo below.
* Rules: the user chooses **Fruit** and the crop (only orange is supported). If the produce model confidently sees a
  different fruit, the photo is refused. Thresholds are the same as for leaves (top-1 >= 60 %, margin >= 20).
  Severity is not estimated for fruit (the leaf colour heuristic does not apply).

Real photos (Wikimedia Commons; public domain or CC BY-SA), int8 model:

| Photo | Truth | Model | App outcome |
|---|---|---|---|
| Citrus Canker (49949888707) | canker on fruit | citrus canker 78.9 % | possible disease, correct |
| Citrus canker on fruit | canker on fruit | citrus canker 61.7 % | possible disease, correct |
| Mandarin Oranges (Citrus Reticulata) | healthy fruit | healthy 75.2 % | possibly healthy, correct |
| Ambersweet oranges (cut) | healthy fruit | healthy 53.0 % | uncertain (below 60 %) |
| Citrus Canker (20190106-APHIS-CHRP-0058) | faint canker, green fruit | healthy 62.4 % | possibly healthy, **wrong** |

Five photos is a smoke test, not an accuracy measurement: 3 right, 1 uncertain, 1 missed. Peak memory with all four
models loaded in one process: 320 MB.
