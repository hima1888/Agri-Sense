"""One-off: convert the ixrbhii ConvNeXt-Small leaf-disease models (CC BY 4.0) to int8 ONNX and verify them.

NOT part of the application. Run it in a separate, throwaway virtual environment:

    python -m venv /tmp/convert
    /tmp/convert/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
    /tmp/convert/bin/pip install timm safetensors onnx onnxruntime huggingface_hub pillow
    /tmp/convert/bin/python scripts/convert_leaf_models.py --out backend/ml_models [--photos DIR]

Each model: https://huggingface.co/ixrbhii/<crop>-disease-convnext (timm convnext_small, 224 x 224, ImageNet
mean/std, half-precision weights). Exported at float32 to ONNX opset 17, then weights dynamically quantised to
int8 (~50 MB each). The script reports, per model, how far int8 drifts from PyTorch on random inputs, and with
--photos DIR (files named <crop>__<anything>.jpg) the PyTorch and int8 answers for each photo.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import timm
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from PIL import Image

CROPS = [
    "mango", "banana", "guava", "papaya", "pomegranate", "citrus",
    "brinjal", "okra", "cucumber", "bitter-gourd", "bottle-gourd", "watermelon",
]  # fmt: skip
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess(img: Image.Image) -> np.ndarray:
    """timm transform (crop_pct 1.0): shortest edge 224 bilinear, centre crop 224, ImageNet norm."""
    img = img.convert("RGB")
    w, h = img.size
    nw, nh = (224, max(224, round(224 * h / w))) if w <= h else (max(224, round(224 * w / h)), 224)
    img = img.resize((nw, nh), Image.Resampling.BILINEAR)
    left, top = (nw - 224) // 2, (nh - 224) // 2
    a = np.asarray(img.crop((left, top, left + 224, top + 224)), dtype=np.float32) / 255.0
    return np.asarray(((a - MEAN) / STD).transpose(2, 0, 1)[None], dtype=np.float32)


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


def convert(crop: str, work: Path, out: Path, photos: Path | None) -> dict[str, object]:
    model = timm.create_model(f"hf-hub:ixrbhii/{crop}-disease-convnext", pretrained=True).float().eval()
    labels = list(model.pretrained_cfg["label_names"])
    fp32 = work / f"{crop}_fp32.onnx"
    torch.onnx.export(
        model, (torch.randn(1, 3, 224, 224),), fp32,
        input_names=["pixel_values"], output_names=["logits"],
        dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17, dynamo=False,
    )  # fmt: skip
    onnx.checker.check_model(onnx.load(fp32))
    int8 = out / f"leaf_{crop.replace('-', '_')}_int8.onnx"
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    sess = ort.InferenceSession(str(int8), providers=["CPUExecutionProvider"])
    xs = torch.randn(16, 3, 224, 224)
    with torch.no_grad():
        ref = softmax(model(xs).numpy())
    got = softmax(sess.run(None, {"pixel_values": xs.numpy()})[0])
    rep: dict[str, object] = {
        "labels": labels,
        "int8_mb": round(int8.stat().st_size / 1e6, 1),
        "random_max_abs_prob_diff": round(float(np.abs(ref - got).max()), 4),
        "random_argmax_agree": f"{int((ref.argmax(1) == got.argmax(1)).sum())}/16",
    }
    if photos:
        rows = []
        for p in sorted(photos.glob(f"{crop}__*.jpg")):
            x = preprocess(Image.open(p))
            with torch.no_grad():
                pt = softmax(model(torch.from_numpy(x)).numpy())[0]
            q = softmax(sess.run(None, {"pixel_values": x})[0])[0]
            pt_s, q_s = (
                f"{labels[int(pt.argmax())]} {pt.max():.3f}",
                f"{labels[int(q.argmax())]} {q.max():.3f}",
            )
            rows.append(f"{p.name}: pytorch {pt_s} | int8 {q_s}")
        rep["photos"] = rows
    fp32.unlink()
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=Path("hf_work"))
    ap.add_argument("--photos", type=Path)
    ap.add_argument("--crops", nargs="*", default=CROPS)
    args = ap.parse_args()
    torch.manual_seed(0)
    args.out.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    report = {c: convert(c, args.work, args.out, args.photos) for c in args.crops}
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
