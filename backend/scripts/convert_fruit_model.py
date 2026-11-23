"""One-off: convert the orange-fruit disease model to ONNX, compress it to int8 and verify it.

NOT part of the application. Run it in a separate, throwaway virtual environment:

    python -m venv /tmp/convert
    /tmp/convert/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
    /tmp/convert/bin/pip install transformers safetensors onnx onnxruntime huggingface_hub pillow
    /tmp/convert/bin/python scripts/convert_fruit_model.py --out backend/ml_models [--photos DIR]

Source: https://huggingface.co/dima806/orange_fruit_disease_detection (Apache-2.0),
ViT-base/16, 85.8 M parameters.
The fp32 ONNX (~343 MB) is too big for git and a 512 MB server, so it is dynamically quantised to int8
(weights only, ~87 MB). The script reports how far int8 drifts from PyTorch on random inputs and, if
--photos is given, prints PyTorch vs int8 predictions per photo, to judge the drift on real images.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from huggingface_hub import hf_hub_download
from onnxruntime.quantization import QuantType, quantize_dynamic
from PIL import Image
from transformers import ViTForImageClassification

REPO = "dima806/orange_fruit_disease_detection"


def preprocess(img: Image.Image) -> np.ndarray:
    """ViTImageProcessor for this model: resize 224x224 bilinear, /255, (x - 0.5) / 0.5."""
    a = np.asarray(img.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
    return np.asarray(((a - 0.5) / 0.5).transpose(2, 0, 1)[None], dtype=np.float32)


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=Path("hf_download/orange"))
    ap.add_argument("--photos", type=Path)
    args = ap.parse_args()
    torch.manual_seed(0)
    for f in ("config.json", "preprocessor_config.json", "model.safetensors"):
        hf_hub_download(REPO, f, local_dir=args.work)
    model = ViTForImageClassification.from_pretrained(args.work, use_safetensors=True).eval()
    print("labels:", model.config.id2label)

    fp32 = args.work / "orange_fp32.onnx"
    torch.onnx.export(
        model, (torch.randn(1, 3, 224, 224),), fp32,
        input_names=["pixel_values"], output_names=["logits"],
        dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17, dynamo=False,
    )  # fmt: skip
    onnx.checker.check_model(onnx.load(fp32))
    args.out.mkdir(parents=True, exist_ok=True)
    int8 = args.out / "orange_fruit_vit_int8.onnx"
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)

    sess = ort.InferenceSession(str(int8), providers=["CPUExecutionProvider"])
    xs = torch.randn(16, 3, 224, 224) * 1.2
    with torch.no_grad():
        ref = softmax(model(pixel_values=xs).logits.numpy())
    got = softmax(sess.run(None, {"pixel_values": xs.numpy()})[0])
    report: dict[str, object] = {
        "int8_bytes": int8.stat().st_size,
        "random_max_abs_prob_diff": float(np.abs(ref - got).max()),
        "random_argmax_agree": f"{int((ref.argmax(1) == got.argmax(1)).sum())}/16",
    }
    if args.photos:
        rows = []
        for p in sorted(args.photos.glob("*.jpg")):
            x = preprocess(Image.open(p))
            with torch.no_grad():
                pt = softmax(model(pixel_values=torch.from_numpy(x)).logits.numpy())[0]
            q = softmax(sess.run(None, {"pixel_values": x})[0])[0]
            lab = model.config.id2label
            rows.append({
                "photo": p.name,
                "pytorch": f"{lab[int(pt.argmax())]} {pt.max():.3f}",
                "int8": f"{lab[int(q.argmax())]} {q.max():.3f}",
                "int8_probs": {lab[i]: round(float(v), 3) for i, v in enumerate(q)},
            })  # fmt: skip
        report["photos"] = rows
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
