# Model files

| File | Source | Licence | Notes |
|---|---|---|---|
| `crop_leaf_vit.onnx` | [wambugu71/crop_leaf_diseases_vit](https://huggingface.co/wambugu71/crop_leaf_diseases_vit) | MIT per model metadata (card text also says Apache 2.0) | Converted to ONNX (opset 17) by `backend/scripts/convert_disease_models.py`. Unmodified weights. |
| `plantvillage_mnv2.onnx` | [linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification](https://huggingface.co/linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification) | "other" (not specified by the author) | Converted the same way. Included for non-commercial, educational use; ask the author before any commercial use. |
| `mobilenetv2-12.onnx` | [ONNX Model Zoo](https://github.com/onnx/models) | Apache 2.0 | Not stored in git; downloaded at build time by `python -m app.cli.fetch_models`. |

All credit for the trained weights goes to the original authors. The app verifies each file against the SHA-256 in `app/vision/disease.py` before use.
