# Plant & produce recognition (Phase 9)

`/vision` in the app. A real pretrained model runs locally on the API server (CPU, ONNX Runtime).

## Model

| | |
|---|---|
| Model | MobileNetV2 1.0, fp32 (`mobilenetv2-12.onnx`, 13.3 MB) |
| Source | ONNX Model Zoo (`onnx/models` on GitHub), SHA-256 checked |
| Trained on | ImageNet-1k (ILSVRC 2012), 1000 general classes |
| Published accuracy | 69.48 % top-1, 89.26 % top-5 on ImageNet validation (all classes) |
| Farm-photo accuracy | **Not measured.** No labelled farm images exist in this project yet. |

Install: `python -m app.cli.fetch_models` (downloads into `backend/ml_models/`, git-ignored, and verifies
the checksum). Without it, recognition returns `503 model_unavailable` and the page says so.

Only **25 produce classes** that exist in ImageNet are reported: cabbage, broccoli, cauliflower, zucchini,
spaghetti/acorn/butternut squash, cucumber, artichoke, bell pepper, cardoon, mushroom, apple (Granny Smith),
strawberry, orange, lemon, fig, pineapple, banana, jackfruit, custard apple, pomegranate, rapeseed plant,
maize, cereal ear. Tomato, rice, wheat plants, leaves and most Indian crops are **not** supported by this model.

## Outcome rules

- `recognized`: the overall top-1 class is a produce class with probability ≥ 0.30.
- `uncertain`: top-1 is produce but < 0.30, or produce classes together hold ≥ 25 % probability.
- `unsupported`: anything else. No label is forced; the response shows what the model sees instead
  (e.g. "Samoyed") and **nothing is stored**.

## Explainability

Every response has: top-5 produce candidates with raw softmax probabilities; the top-3 of all 1000
classes; image-quality checks (resolution, brightness, contrast, sharpness heuristics); an
**occlusion-sensitivity map** (7×7 grid; each cell is greyed out and the drop in the predicted class's
probability is measured, normalised 0–1), drawn as a heat-map over the centre crop; and limitations.

## Storage and privacy

Recognised/uncertain results are stored in `plant_detections` (with `top_k`, the new `explanation`
JSONB column — migration `0002` — and a `model_versions` row). The photo is re-encoded as JPEG
(≤ 1600 px), which strips EXIF metadata including GPS, and kept under `backend/uploads/` (git-ignored).
Images are served only to the farm owner through `GET /vision/recognitions/{id}/image`; deleting a
recognition deletes the file. Uploads: JPEG/PNG/WebP, ≤ 8 MB, decompression-bomb guarded.

## Limitations

- Not trained on farm photos; no varieties, ripeness, disease (Phase 10) or counting.
- Softmax confidence is not calibrated; values near 100 % can still be wrong on unusual photos.
- Image-quality checks are simple heuristics; sharpness can flag clean studio photos on plain backgrounds.
- Uploads are stored on the API server's disk, not Supabase Storage; a multi-server deployment (Phase 20) needs shared storage.
