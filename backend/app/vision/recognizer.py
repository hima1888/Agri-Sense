"""Produce recognition with an ImageNet-pretrained MobileNetV2 (ONNX Model Zoo, mobilenetv2-12).

The model is a general 1000-class ImageNet classifier. It was NOT trained on farm images.
We only report the classes listed in PRODUCE_CLASSES; anything else is answered honestly as
"not a supported produce class", together with what the model thinks it sees.

Explainability:
* top-k candidates with raw softmax probabilities;
* image-quality factors (resolution, brightness, contrast, sharpness) that limit confidence;
* an occlusion-sensitivity map: the image is re-classified with each grid cell greyed out,
  and the drop in the predicted class's probability shows which regions the decision used.
"""

from __future__ import annotations

import hashlib
import io
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MODEL_DIR = Path(__file__).resolve().parents[2] / "ml_models"
MODEL_FILE = MODEL_DIR / "mobilenetv2-12.onnx"
LABEL_FILE = MODEL_DIR / "synset.txt"
MODEL_SHA256 = "c0c3f76d93fa3fd6580652a45618618a220fced18babf65774ed169de0432ad5"
MODEL_SOURCE = "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx"
LABEL_SOURCE = "https://raw.githubusercontent.com/onnx/models/main/validated/vision/classification/synset.txt"
MODEL_NAME = "mobilenetv2-imagenet"
MODEL_VERSION = "onnx-zoo-12"
# Published ImageNet-1k validation accuracy for this ONNX export (ONNX Model Zoo README).
MODEL_METRICS = {
    "top1_accuracy": 0.6948,
    "top5_accuracy": 0.8926,
    "dataset": "ImageNet-1k validation (all classes)",
}

SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
MAX_PIXELS = 40_000_000  # decompression-bomb guard
GRID = 7

# ImageNet class index -> (label shown to users, subject type).
PRODUCE_CLASSES: dict[int, tuple[str, str]] = {
    936: ("cabbage", "vegetable"),
    937: ("broccoli", "vegetable"),
    938: ("cauliflower", "vegetable"),
    939: ("zucchini", "vegetable"),
    940: ("spaghetti squash", "vegetable"),
    941: ("acorn squash", "vegetable"),
    942: ("butternut squash", "vegetable"),
    943: ("cucumber", "vegetable"),
    944: ("artichoke", "vegetable"),
    945: ("bell pepper", "vegetable"),
    946: ("cardoon", "vegetable"),
    947: ("mushroom", "vegetable"),
    948: ("apple (Granny Smith)", "fruit"),
    949: ("strawberry", "fruit"),
    950: ("orange", "fruit"),
    951: ("lemon", "fruit"),
    952: ("fig", "fruit"),
    953: ("pineapple", "fruit"),
    954: ("banana", "fruit"),
    955: ("jackfruit", "fruit"),
    956: ("custard apple", "fruit"),
    957: ("pomegranate", "fruit"),
    984: ("rapeseed (mustard) plant", "plant"),
    987: ("maize (corn kernels/cob)", "vegetable"),
    998: ("cereal ear (spike)", "plant"),
}

MIN_CONFIDENCE = 0.30  # below this the top produce class is reported as uncertain


class ModelUnavailableError(RuntimeError):
    pass


class BadImageError(ValueError):
    pass


@dataclass
class _Model:
    session: Any
    input_name: str
    labels: list[str]


_lock = threading.Lock()
_model: _Model | None = None


def model_available() -> bool:
    return MODEL_FILE.is_file() and LABEL_FILE.is_file()


def _load() -> _Model:
    global _model
    with _lock:
        if _model is None:
            if not model_available():
                raise ModelUnavailableError(
                    "Recognition model is not installed. Run: python -m app.cli.fetch_models"
                )
            import onnxruntime as ort  # type: ignore[import-untyped]

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            session = ort.InferenceSession(str(MODEL_FILE), opts, providers=["CPUExecutionProvider"])
            labels = [
                line.split(" ", 1)[1].split(",")[0].strip() for line in LABEL_FILE.read_text().splitlines()
            ]
            _model = _Model(session, session.get_inputs()[0].name, labels)
        return _model


def decode(data: bytes) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        Image.open(io.BytesIO(data)).verify()
        with Image.open(io.BytesIO(data)) as raw:
            return ImageOps.exif_transpose(raw).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise BadImageError("The file is not a readable JPEG, PNG or WebP image.") from e


def preprocess(img: Image.Image) -> np.ndarray:
    """Resize the shorter side to 256 and centre-crop 224; returns HWC float32 in [0, 1]."""
    w, h = img.size
    scale = 256 / min(w, h)
    img = img.resize((max(SIZE, round(w * scale)), max(SIZE, round(h * scale))), Image.Resampling.BILINEAR)
    w, h = img.size
    left, top = (w - SIZE) // 2, (h - SIZE) // 2
    img = img.crop((left, top, left + SIZE, top + SIZE))
    return np.asarray(img, dtype=np.float32) / 255.0


def _to_batch(images: np.ndarray) -> np.ndarray:
    return ((images - MEAN) / STD).transpose(0, 3, 1, 2).astype(np.float32)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x, axis=1, keepdims=True))
    return np.asarray(e / e.sum(axis=1, keepdims=True))


def quality(img: Image.Image, arr: np.ndarray) -> list[dict[str, Any]]:
    gray = arr.mean(axis=2)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    lap = gray[1:-1, 1:-1] * 4 - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    sharpness = float(lap.var() * 1e4)
    w, h = img.size
    checks = [
        ("resolution", f"{w}x{h}px", "ok" if min(w, h) >= 224 else "low",
         "At least 224 px on the short side."),
        ("brightness", round(brightness, 2), "ok" if 0.15 <= brightness <= 0.9 else "poor",
         "Mean brightness 0.15 to 0.9; very dark or blown-out images lose detail."),
        ("contrast", round(contrast, 3), "ok" if contrast >= 0.06 else "poor",
         "Flat, low-contrast images are hard to classify."),
        ("sharpness", round(sharpness, 1), "ok" if sharpness >= 15 else "poor",
         "Blurry images (low Laplacian variance) lower accuracy."),
    ]  # fmt: skip
    return [{"key": k, "value": v, "status": s, "note": n} for k, v, s, n in checks]


def occlusion_map(model: _Model, arr: np.ndarray, class_idx: int, base_prob: float) -> list[list[float]]:
    """Probability drop for the predicted class when each GRID x GRID cell is greyed out (0..1)."""
    cell = SIZE // GRID
    batch = np.repeat(arr[None], GRID * GRID, axis=0)
    for i in range(GRID):
        for j in range(GRID):
            batch[i * GRID + j, i * cell : (i + 1) * cell, j * cell : (j + 1) * cell] = MEAN
    probs = _softmax(model.session.run(None, {model.input_name: _to_batch(batch)})[0])[:, class_idx]
    drop = np.clip(base_prob - probs, 0, None)
    peak = float(np.max(drop))
    norm = drop / peak if peak > 0 else drop
    return [[round(float(v), 3) for v in norm[i * GRID : (i + 1) * GRID]] for i in range(GRID)]


def recognize(data: bytes, explain: bool = True) -> dict[str, Any]:
    model = _load()
    img = decode(data)
    arr = preprocess(img)
    probs = _softmax(model.session.run(None, {model.input_name: _to_batch(arr[None])})[0])[0]

    order = np.argsort(probs)[::-1]
    overall = [{"label": model.labels[i], "confidence": round(float(probs[i]), 4)} for i in order[:3]]
    produce = sorted(PRODUCE_CLASSES, key=lambda i: -probs[i])
    candidates = [
        {
            "label": PRODUCE_CLASSES[i][0],
            "subject_type": PRODUCE_CLASSES[i][1],
            "confidence": round(float(probs[i]), 4),
        }
        for i in produce[:5]
    ]
    produce_mass = float(sum(probs[i] for i in PRODUCE_CLASSES))
    best = produce[0]
    best_p = float(probs[best])
    top_is_produce = int(order[0]) in PRODUCE_CLASSES
    q = quality(img, arr)

    if top_is_produce and best_p >= MIN_CONFIDENCE:
        outcome = "recognized"
    elif top_is_produce or produce_mass >= 0.25:
        outcome = "uncertain"
    else:
        outcome = "unsupported"

    poor = [c["key"] for c in q if c["status"] != "ok"]
    limitations = [
        "General ImageNet model (MobileNetV2), not trained on farm photos; it recognises only "
        f"{len(PRODUCE_CLASSES)} produce classes and cannot tell varieties apart.",
        "Confidence is the model's softmax probability; it is not calibrated on farm images.",
        "Published accuracy (69.5 % top-1 over all 1000 ImageNet classes) "
        "has not been measured on this farm's images.",
        "It does not diagnose disease or ripeness (Phase 10).",
    ]
    if poor:
        limitations.append(f"Image quality issues ({', '.join(poor)}) may reduce accuracy.")
    if outcome == "unsupported":
        limitations.append(
            "The image does not look like any supported produce class; the result is not a recognition."
        )

    return {
        "outcome": outcome,
        "label": PRODUCE_CLASSES[best][0] if outcome != "unsupported" else None,
        "subject_type": PRODUCE_CLASSES[best][1] if outcome != "unsupported" else None,
        "confidence": round(best_p, 4),
        "produce_probability": round(produce_mass, 4),
        "candidates": candidates,
        "model_sees": overall,
        "quality": q,
        "explanation": {
            "method": "occlusion sensitivity: 7x7 grid cells greyed out; drop in predicted-class probability",
            "grid": occlusion_map(model, arr, best, best_p) if explain and outcome != "unsupported" else None,
            "crop": "centre square crop of the image (shorter side), as the model sees it",
        },
        "limitations": limitations,
        "image_sha256": hashlib.sha256(data).hexdigest(),
        "image_size": list(img.size),
    }


def model_info() -> dict[str, Any]:
    return {
        "name": MODEL_NAME,
        "version": MODEL_VERSION,
        "available": model_available(),
        "framework": "onnx",
        "source": MODEL_SOURCE,
        "training_dataset": "ImageNet-1k (ILSVRC 2012)",
        "metrics": MODEL_METRICS,
        "supported": [{"label": lbl, "subject_type": st} for lbl, st in PRODUCE_CLASSES.values()],
        "min_confidence": MIN_CONFIDENCE,
    }
