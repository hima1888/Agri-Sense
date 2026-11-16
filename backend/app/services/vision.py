"""Plant & produce recognition: run the model, store the image and an explainable result."""

import io
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import FarmZone, ModelVersion, PlantDetection, User
from app.vision import recognizer

ACCEPTED_TYPES = {"image/jpeg", "image/png", "image/webp"}
INPUT_SPEC = {
    "shape": [1, 3, 224, 224],
    "resize": 256,
    "crop": 224,
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
}


def model_version(db: Session) -> ModelVersion:
    mv = db.scalar(
        select(ModelVersion).where(
            ModelVersion.model_name == recognizer.MODEL_NAME, ModelVersion.version == recognizer.MODEL_VERSION
        )
    )
    if mv is None:
        info = recognizer.model_info()
        mv = ModelVersion(
            model_name=recognizer.MODEL_NAME,
            version=recognizer.MODEL_VERSION,
            task="plant_recognition",
            framework="onnx",
            artifact_uri=recognizer.MODEL_SOURCE,
            status="production",
            labels=[s["label"] for s in info["supported"]],
            input_spec=INPUT_SPEC,
            metrics=recognizer.MODEL_METRICS,
            training_dataset=info["training_dataset"],
            known_limitations="General ImageNet classifier; only the listed produce classes are reported; "
            "not trained or evaluated on farm images.",
        )
        db.add(mv)
        db.flush()
    return mv


def store_image(farm_id: int, data: bytes) -> str:
    """Re-encode as JPEG (drops EXIF, including GPS) and store; returns the image_uri."""
    img = recognizer.decode(data)
    img.thumbnail((1600, 1600))
    root: Path = get_settings().upload_dir
    rel = Path(str(farm_id)) / f"{uuid.uuid4().hex}.jpg"
    (root / rel.parent).mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    (root / rel).write_bytes(buf.getvalue())
    return f"local:{rel.as_posix()}"


def image_path(image_uri: str) -> Path | None:
    if not image_uri.startswith("local:"):
        return None
    root = get_settings().upload_dir.resolve()
    path = (root / image_uri.removeprefix("local:")).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None


def recognize_and_store(
    db: Session, user: User, farm_id: int, zone: FarmZone | None, data: bytes
) -> dict[str, Any]:
    result = recognizer.recognize(data)
    mv = model_version(db)
    detection: PlantDetection | None = None
    if result["outcome"] != "unsupported":
        detection = PlantDetection(
            farm_id=farm_id,
            zone_id=zone.id if zone else None,
            model_version_id=mv.id,
            created_by=user.id,
            image_uri=store_image(farm_id, data),
            subject_type=result["subject_type"],
            predicted_label=result["label"],
            confidence=Decimal(str(result["confidence"])),
            top_k=result["candidates"],
            explanation={
                "outcome": result["outcome"],
                "occlusion": result["explanation"],
                "quality": result["quality"],
                "model_sees": result["model_sees"],
                "produce_probability": result["produce_probability"],
                "limitations": result["limitations"],
                "image_sha256": result["image_sha256"],
            },
        )
        db.add(detection)
        db.flush()
    return {
        **result,
        "detection_id": detection.id if detection else None,
        "saved": detection is not None,
        "model": {"name": mv.model_name, "version": mv.version, "id": mv.id},
    }


def validate_upload(content_type: str | None, data: bytes) -> None:
    max_bytes = int(get_settings().max_upload_mb * 1024 * 1024)
    if content_type not in ACCEPTED_TYPES:
        raise recognizer.BadImageError("Upload a JPEG, PNG or WebP image.")
    if not data:
        raise recognizer.BadImageError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise recognizer.BadImageError(f"Images must be at most {get_settings().max_upload_mb:g} MB.")
