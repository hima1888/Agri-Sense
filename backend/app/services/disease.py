"""Disease screening: route by crop, run the engine, store non-refused results with their explanation."""

from decimal import Decimal
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import Crop, CropCycle, DiseaseDetection, FarmZone, ModelVersion, User
from app.services.vision import store_image
from app.vision import disease

STORED_OUTCOMES = {"possible_disease", "possible_healthy", "uncertain"}
EXPLANATION_KEYS = (
    "outcome", "part", "crop", "crop_source", "model", "margin", "checks",
    "quality", "reason", "limitations", "image_sha256",
)  # fmt: skip


def zone_crop(db: Session, zone: FarmZone) -> str | None:
    """Common name of the zone's growing (else planned) crop cycle."""
    order = case((CropCycle.status == "growing", 0), else_=1)
    return db.scalar(
        select(Crop.common_name)
        .join(CropCycle, CropCycle.crop_id == Crop.id)
        .where(CropCycle.zone_id == zone.id, CropCycle.status.in_(("growing", "planned")))
        .order_by(order, CropCycle.id.desc())
        .limit(1)
    )


def model_version(db: Session, m: disease.DiseaseModel) -> ModelVersion:
    mv = db.scalar(
        select(ModelVersion).where(ModelVersion.model_name == m.name, ModelVersion.version == m.version)
    )
    if mv is None:
        mv = ModelVersion(
            model_name=m.name,
            version=m.version,
            task="disease_detection",
            framework="onnx",
            artifact_uri=m.source,
            status="staging",  # not validated on field photos
            labels=[disease.label_text(m, i) for i in range(len(m.labels))],
            input_spec={"shape": [1, 3, 224, 224], "preprocessing": m.preprocessing, "sha256": m.sha256},
            metrics={"published": m.published_accuracy, "field_smoke_test": "0/5 field photos correct"},
            training_dataset="see source model card",
            known_limitations=" ".join(m.limitations + disease.COMMON_LIMITATIONS),
        )
        db.add(mv)
        db.flush()
    return mv


def screen_and_store(
    db: Session,
    user: User,
    farm_id: int,
    zone: FarmZone | None,
    crop: str | None,
    data: bytes,
    part: str = "leaf",
) -> dict[str, Any]:
    crop_source = "request"
    if not crop and zone is not None:
        crop, crop_source = zone_crop(db, zone), "zone crop cycle"
    result = disease.screen(data, crop, part)
    result["crop_source"] = crop_source if crop else None
    det: DiseaseDetection | None = None
    if result["outcome"] in STORED_OUTCOMES:
        m = disease.MODELS[result["model"]["key"]]
        mv = model_version(db, m)
        result["model"]["id"] = mv.id
        area = result["affected_area_pct"]
        det = DiseaseDetection(
            farm_id=farm_id,
            zone_id=zone.id if zone else None,
            model_version_id=mv.id,
            created_by=user.id,
            image_uri=store_image(farm_id, data),
            disease_label=result["label"],
            is_healthy=bool(result["is_healthy"]),
            confidence=Decimal(str(result["confidence"])),
            severity=result["severity"] or "none",
            affected_area_pct=None if area is None else Decimal(str(area)),
            top_k=result["candidates"],
            explanation={k: result[k] for k in EXPLANATION_KEYS},
        )
        db.add(det)
        db.flush()
    result["detection_id"] = det.id if det else None
    result["saved"] = det is not None
    return result
