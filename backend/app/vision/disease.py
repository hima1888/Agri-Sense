"""Leaf-disease screening with two community models, converted to ONNX (see docs/DISEASE_MODELS.md).

Rules (agreed in Phase 10; thresholds are untuned starting points from an 11-image smoke test):
1. The crop comes from the user or the zone, never from the model. Corn/potato/rice/wheat use the
   Crop ViT; crops the ViT lacks use PlantVillage MobileNetV2; anything else is refused.
2. If the model's top-1 over ALL its classes is another crop (or the ViT's "Invalid"), the answer
   is "cannot reliably identify". We never re-score within the chosen crop to force an answer.
3. A disease/healthy call needs top-1 >= 0.60 and a margin >= 0.20 over the second class;
   otherwise the result is "uncertain" with the candidates.
4. If the Phase 9 produce model recognises the photo as fruit/vegetable, it is refused as "not a leaf".
5. Results are "possible", with the model, its raw softmax confidence and limitations.
"""

# ruff: noqa: E501  (label tables and user-facing messages read better unwrapped)
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.vision import recognizer
from app.vision.recognizer import MODEL_DIR, BadImageError, ModelUnavailableError, decode, quality

MIN_TOP1 = 0.60
MIN_MARGIN = 0.20

# Each label: (crop key or None for "Invalid", disease name or None when healthy)
Label = tuple[str | None, str | None]


@dataclass(frozen=True)
class DiseaseModel:
    key: str
    name: str
    version: str
    file: str
    sha256: str
    source: str
    weights_source: str
    licence: str
    architecture: str
    preprocessing: str
    labels: list[Label]
    published_accuracy: str
    limitations: list[str] = field(default_factory=list)
    part: str = "leaf"  # what the photo must show: "leaf" or "fruit"
    square_resize: bool = True  # straight to 224x224 (ViT); False: shortest edge 256 + centre crop

    @property
    def path(self) -> Path:
        return MODEL_DIR / self.file

    @property
    def crops(self) -> list[str]:
        return sorted({c for c, _ in self.labels if c})


VIT = DiseaseModel(
    key="crop_vit",
    name="crop-leaf-diseases-vit",
    version="hf-wambugu71-onnx17",
    file="crop_leaf_vit.onnx",
    sha256="6a048bf3c18575aa5c844f9cd34624d308c024470480d120081196f6a7a60c00",
    source="https://huggingface.co/wambugu71/crop_leaf_diseases_vit",
    weights_source="model.safetensors (main)",
    licence="MIT per metadata (card text also says Apache 2.0)",
    architecture="ViT-tiny (patch 16, hidden 192, 12 layers), 5.53 M parameters",
    preprocessing="resize to 224x224 bilinear, /255, (x - 0.5) / 0.5",
    labels=[
        ("corn", "Common rust"),
        ("corn", "Gray leaf spot"),
        ("corn", None),
        (None, None),
        ("potato", "Early blight"),
        ("potato", None),
        ("potato", "Late blight"),
        ("rice", "Brown spot"),
        ("rice", None),
        ("rice", "Leaf blast"),
        ("wheat", "Brown rust"),
        ("wheat", None),
        ("wheat", "Yellow (stripe) rust"),
    ],
    published_accuracy="98 % self-reported on a 20 % split of its own (partly private) data; unverified",
    limitations=[
        "Its 'Invalid' class does not reliably reject non-leaf or other-crop photos.",
    ],
)

PLANTVILLAGE = DiseaseModel(
    key="plantvillage",
    name="plantvillage-mobilenet-v2",
    version="hf-linkanjarad-onnx17",
    file="plantvillage_mnv2.onnx",
    sha256="c5021fe9b56a4bde2b7c2feab0816c2ce9e576f6b210bb2df216dd7ec247cb5e",
    source="https://huggingface.co/linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification",
    weights_source="model.safetensors from HF conversion-bot PR #2 (bit-identical to the pickle)",
    licence="'other' (unspecified)",
    architecture="MobileNetV2 1.0, 2.27 M parameters",
    preprocessing="shortest edge 256 bilinear (long side floored), centre crop 224, /255, (x - 0.5) / 0.5",
    square_resize=False,
    labels=[
        ("apple", "Apple scab"),
        ("apple", "Black rot"),
        ("apple", "Cedar apple rust"),
        ("apple", None),
        ("blueberry", None),
        ("cherry", "Powdery mildew"),
        ("cherry", None),
        ("corn", "Cercospora / gray leaf spot"),
        ("corn", "Common rust"),
        ("corn", "Northern leaf blight"),
        ("corn", None),
        ("grape", "Black rot"),
        ("grape", "Esca (black measles)"),
        ("grape", "Isariopsis leaf spot"),
        ("grape", None),
        ("orange", "Citrus greening (HLB)"),
        ("peach", "Bacterial spot"),
        ("peach", None),
        ("bell pepper", "Bacterial spot"),
        ("bell pepper", None),
        ("potato", "Early blight"),
        ("potato", "Late blight"),
        ("potato", None),
        ("raspberry", None),
        ("soybean", None),
        ("squash", "Powdery mildew"),
        ("strawberry", "Leaf scorch"),
        ("strawberry", None),
        ("tomato", "Bacterial spot"),
        ("tomato", "Early blight"),
        ("tomato", "Late blight"),
        ("tomato", "Leaf mold"),
        ("tomato", "Septoria leaf spot"),
        ("tomato", "Spider mites"),
        ("tomato", "Target spot"),
        ("tomato", "Yellow leaf curl virus"),
        ("tomato", "Mosaic virus"),
        ("tomato", None),
    ],
    published_accuracy="Conflicting: 95.41 % (model card) vs 78.58 % (repo eval_results.json), "
    "on PlantVillage lab photos",
    limitations=[
        "Trained on PlantVillage lab photos (single leaf, plain background); transfers poorly to field photos.",
    ],
)

ORANGE_FRUIT = DiseaseModel(
    key="orange_fruit",
    name="orange-fruit-disease-vit",
    version="hf-dima806-onnx17-int8",
    file="orange_fruit_vit_int8.onnx",
    sha256="6be1fcb22f55eec8ef6b0a62c8fbf75366671d9b2cb09175108478c564985ec7",
    source="https://huggingface.co/dima806/orange_fruit_disease_detection",
    weights_source="model.safetensors (main), ONNX opset 17, weights dynamically quantised to int8",
    licence="Apache-2.0",
    architecture="ViT-base (patch 16, hidden 768, 12 layers), 85.8 M parameters",
    preprocessing="resize to 224x224 bilinear, /255, (x - 0.5) / 0.5",
    labels=[("orange", "Citrus canker"), ("orange", None), ("orange", "Melanose")],
    published_accuracy="97.9 % self-reported on 3,600 images of its own dataset; unverified",
    limitations=[
        "Orange fruit photos only. It knows three answers (citrus canker, melanose, healthy) and has no "
        "'not an orange' class, so every photo gets one of the three.",
        "Weights compressed to int8 to fit the server; see docs/DISEASE_MODELS.md for the measured drift.",
    ],
    part="fruit",
)

MODELS = {m.key: m for m in (VIT, PLANTVILLAGE, ORANGE_FRUIT)}
FRUIT_MODELS = {c: m for m in (ORANGE_FRUIT,) for c in m.crops}
PARTS = ("leaf", "fruit")
CROP_ALIASES = {"maize": "corn", "capsicum": "bell pepper", "sweet pepper": "bell pepper", "paddy": "rice"}

COMMON_LIMITATIONS = [
    "Screening aid only, not a diagnosis. Confirm with an agronomist or extension officer before any treatment.",
    "Community fine-tuned model; accuracy on field photos has not been measured. In our 11-image smoke "
    "test neither model identified any of 5 field photos correctly.",
    "Confidence is the model's uncalibrated softmax probability; wrong answers at 70 to 100 % were observed.",
    "Thresholds (top-1 >= 60 %, margin >= 20 points) are untuned starting points.",
]


def normalise_crop(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().lower()
    return CROP_ALIASES.get(n, n)


def model_for_crop(crop: str, part: str = "leaf") -> DiseaseModel | None:
    """Fruit: the fruit model for that crop. Leaf: ViT for the crops it covers; PlantVillage for the rest."""
    if part == "fruit":
        return FRUIT_MODELS.get(crop)
    if crop in VIT.crops:
        return VIT
    if crop in PLANTVILLAGE.crops:
        return PLANTVILLAGE
    return None


def supported_fruits() -> dict[str, str]:
    return {c: m.key for c, m in sorted(FRUIT_MODELS.items())}


def supported_crops() -> dict[str, str]:
    return {
        c: (m.key if (m := model_for_crop(c)) else "")
        for c in sorted(set(VIT.crops) | set(PLANTVILLAGE.crops))
    }


# ------------------------------------------------------------------ inference
_lock = threading.Lock()
_sessions: dict[str, Any] = {}


def model_available(m: DiseaseModel) -> bool:
    return m.path.is_file()


def _session(m: DiseaseModel) -> Any:
    with _lock:
        if m.key not in _sessions:
            if not model_available(m):
                raise ModelUnavailableError(
                    f"Disease model {m.name} is not installed. See docs/DISEASE_MODELS.md (scripts/convert_disease_models.py)."
                )
            if hashlib.sha256(m.path.read_bytes()).hexdigest() != m.sha256:
                raise ModelUnavailableError(f"Disease model {m.name} failed its checksum; reinstall it.")
            import onnxruntime as ort  # type: ignore[import-untyped]

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            _sessions[m.key] = ort.InferenceSession(str(m.path), opts, providers=["CPUExecutionProvider"])
        return _sessions[m.key]


def preprocess(m: DiseaseModel, img: Image.Image) -> np.ndarray:
    """Matches the models' Hugging Face image processors exactly (verified: max difference 0)."""
    if m.square_resize:
        img = img.resize((224, 224), Image.Resampling.BILINEAR)
    else:
        w, h = img.size
        nw, nh = (256, int(256 * h / w)) if w <= h else (int(256 * w / h), 256)
        img = img.resize((nw, nh), Image.Resampling.BILINEAR)
        left, top = (nw - 224) // 2, (nh - 224) // 2
        img = img.crop((left, top, left + 224, top + 224))
    a = np.asarray(img, dtype=np.float32) / 255.0
    return np.asarray(((a - 0.5) / 0.5).transpose(2, 0, 1)[None], dtype=np.float32)


def run(m: DiseaseModel, img: Image.Image) -> np.ndarray:
    logits = _session(m).run(None, {"pixel_values": preprocess(m, img)})[0][0]
    e = np.exp(logits - np.max(logits))
    return np.asarray(e / e.sum())


def label_text(m: DiseaseModel, i: int) -> str:
    crop, disease = m.labels[i]
    if crop is None:
        return "Not a recognisable crop leaf (model's 'Invalid' class)"
    return f"{crop.capitalize()}: {disease or 'healthy'}"


def lesion_area(img: Image.Image) -> float | None:
    """HEURISTIC share of leaf-coloured pixels that are discoloured (brown/yellow), in %.

    Leaf pixels: not near-white/near-black background and reasonably saturated. Discoloured: hue
    outside the green band. Not a measured severity; fails on busy backgrounds and non-green leaves.
    """
    hsv = np.asarray(img.convert("RGB").resize((224, 224)).convert("HSV"), dtype=np.float32)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    leaf = (s > 0.18) & (v > 0.15) & (v < 0.97)
    n_leaf = int(leaf.sum())
    if n_leaf < 224 * 224 * 0.05:
        return None
    green = (h >= 65) & (h <= 170)
    return round(int((leaf & ~green).sum()) / n_leaf * 100, 1)


def severity_from_area(area: float | None) -> str:
    if area is None:
        return "low"
    return "low" if area < 10 else "moderate" if area < 30 else "high"


# ------------------------------------------------------------------ screening
def screen(data: bytes, crop_name: str | None, part: str = "leaf") -> dict[str, Any]:
    if part not in PARTS:
        raise ValueError(f"part must be one of {PARTS}")
    crop = normalise_crop(crop_name)
    img = decode(data)
    checks: list[dict[str, Any]] = []
    base: dict[str, Any] = {
        "part": part,
        "crop": crop,
        "model": None,
        "outcome": "cannot_identify",
        "label": None,
        "disease": None,
        "is_healthy": None,
        "confidence": None,
        "margin": None,
        "candidates": [],
        "checks": checks,
        "quality": quality(img, recognizer.preprocess(img)),
        "affected_area_pct": None,
        "severity": None,
        "image_sha256": hashlib.sha256(data).hexdigest(),
        "image_size": list(img.size),
    }

    def done(reason: str, limitations: list[str] | None = None) -> dict[str, Any]:
        base["reason"] = reason
        base["limitations"] = (limitations or []) + COMMON_LIMITATIONS
        return base

    # Rule 1: route by the supplied crop.
    if crop is None:
        checks.append(
            {
                "rule": "crop_known",
                "passed": False,
                "detail": "No crop given and the zone has no active crop.",
            }
        )
        return done("Choose the crop in the photo; the models cannot be trusted to tell crops apart.")
    m = model_for_crop(crop, part)
    checks.append({"rule": "crop_supported", "passed": m is not None,
                   "detail": f"{crop} {part} -> {m.name if m else 'no model covers this'}"})  # fmt: skip
    if m is None:
        base["outcome"] = "unsupported_crop"
        listed = ", ".join(supported_fruits() if part == "fruit" else supported_crops())
        plural = "leaves" if part == "leaf" else "fruits"
        return done(f"No installed model checks {crop} {plural}. Supported for {plural}: {listed}.")
    base["model"] = {"key": m.key, "name": m.name, "version": m.version}

    produce = recognizer.recognize(data, explain=False)
    is_produce = produce["outcome"] == "recognized"
    seen = f"produce model: {produce['label']} {produce['confidence']:.0%}" if is_produce else ""
    if part == "leaf":
        # Rule 4: produce photos are not leaves.
        checks.append({"rule": "looks_like_leaf", "passed": not is_produce,
                       "detail": seen or "produce model did not recognise fruit/vegetable"})  # fmt: skip
        if is_produce:
            base["outcome"] = "not_a_leaf"
            return done(
                f"The photo looks like {produce['label']} (produce), not a leaf. Photograph a single affected leaf."
            )
    else:
        # Rule 4 (fruit): refuse when the produce model confidently sees a different fruit or vegetable.
        other = is_produce and produce["label"] != crop
        checks.append({"rule": "looks_like_chosen_fruit", "passed": not other,
                       "detail": seen or "produce model named no fruit (diseased fruit often is not recognised)"})  # fmt: skip
        if other:
            base["outcome"] = "not_a_leaf"
            return done(f"The photo looks like {produce['label']}, not {crop}. Photograph one {crop} fruit.")

    probs = run(m, img)
    order = [int(i) for i in np.argsort(probs)[::-1]]
    top, second = order[0], order[1]
    base["candidates"] = [
        {"label": label_text(m, i), "crop": m.labels[i][0], "disease": m.labels[i][1],
         "is_healthy": m.labels[i][0] is not None and m.labels[i][1] is None, "confidence": round(float(probs[i]), 4)}
        for i in order[:5]
    ]  # fmt: skip
    top_crop, top_disease = m.labels[top]
    p1, margin = float(probs[top]), float(probs[top] - probs[second])
    base["confidence"], base["margin"] = round(p1, 4), round(margin, 4)

    # Rule 2: the model's own top-1 must be the chosen crop.
    same_crop = top_crop == crop
    checks.append({"rule": "model_agrees_on_crop", "passed": same_crop,
                   "detail": f"model top-1: {label_text(m, top)} {p1:.1%}"})  # fmt: skip
    if not same_crop:
        why = "the model's 'Invalid' class" if top_crop is None else f"a {top_crop} class"
        return done(f"Cannot reliably identify: the model's top answer is {why}, not {crop}.")

    # Rule 3: confidence and margin.
    ok_conf, ok_margin = p1 >= MIN_TOP1, margin >= MIN_MARGIN
    checks.append({"rule": "confidence", "passed": ok_conf, "detail": f"{p1:.1%} (need >= {MIN_TOP1:.0%})"})
    checks.append({"rule": "margin", "passed": ok_margin,
                   "detail": f"{margin * 100:.1f} points over the 2nd class (need >= {MIN_MARGIN * 100:.0f})"})  # fmt: skip
    base["label"] = label_text(m, top)
    base["disease"] = top_disease
    base["is_healthy"] = top_disease is None
    if not (ok_conf and ok_margin):
        base["outcome"] = "uncertain"
        return done("Uncertain: confidence or margin too low. See the candidates.", m.limitations)

    base["outcome"] = "possible_healthy" if top_disease is None else "possible_disease"
    if top_disease is not None and part == "leaf":
        base["affected_area_pct"] = lesion_area(img)
        base["severity"] = severity_from_area(base["affected_area_pct"])
    elif top_disease is not None:
        base["severity"] = "low"  # not estimated: the leaf colour heuristic does not apply to fruit
    else:
        base["severity"] = "none"
    extra = list(m.limitations)
    if top_disease is not None and part == "fruit":
        extra.append("Severity is not estimated for fruit photos; 'low' is stored only as a placeholder.")
    elif top_disease is not None:
        extra.append(
            "Affected area is a colour heuristic (non-green share of leaf pixels), not a measured severity."
        )
    return done("Passed all checks. Treat as a possible finding to confirm, not a diagnosis.", extra)


def models_info() -> list[dict[str, Any]]:
    return [
        {
            "key": m.key, "name": m.name, "version": m.version, "available": model_available(m),
            "source": m.source, "weights_source": m.weights_source, "licence": m.licence,
            "architecture": m.architecture, "preprocessing": m.preprocessing, "input": [1, 3, 224, 224],
            "crops": m.crops, "classes": [label_text(m, i) for i in range(len(m.labels))],
            "used_for": [c for c, k in (supported_fruits() if m.part == "fruit" else supported_crops()).items() if k == m.key],
            "part": m.part,
            "published_accuracy": m.published_accuracy, "limitations": m.limitations,
        }
        for m in (VIT, PLANTVILLAGE, ORANGE_FRUIT)
    ]  # fmt: skip


__all__ = [
    "BadImageError",
    "ModelUnavailableError",
    "models_info",
    "screen",
    "supported_crops",
    "supported_fruits",
]
