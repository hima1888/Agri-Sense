"""Leaf-disease screening endpoints (Phase 10)."""

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.auth import CurrentUser
from app.api.deps import DbSession, Paging, no_content
from app.api.errors import NotFoundError, UnprocessableError
from app.api.v1.endpoints.vision import ModelUnavailableApiError
from app.knowledge import diseases as knowledge
from app.models import DiseaseDetection
from app.schemas.common import Page
from app.schemas.vision import DiseaseKnowledge, DiseaseModels, DiseaseRecord, DiseaseScreening
from app.services import access, crud
from app.services import disease as svc
from app.services.vision import image_path, validate_upload
from app.vision import disease, recognizer

router = APIRouter(tags=["disease detection"])


@router.get("/vision/disease/models", response_model=DiseaseModels)
def models(user: CurrentUser) -> dict[str, Any]:
    """Both disease models, the crop each is used for, the decision thresholds and limitations."""
    return {
        "models": disease.models_info(),
        "supported_crops": disease.supported_crops(),
        "thresholds": {"min_top1": disease.MIN_TOP1, "min_margin": disease.MIN_MARGIN},
        "limitations": disease.COMMON_LIMITATIONS,
    }


@router.post("/farms/{farm_id}/vision/disease-checks", response_model=DiseaseScreening, status_code=201)
def screen(
    farm_id: int,
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP photo of one leaf")],
    crop: Annotated[str | None, Form(description="Crop in the photo; defaults to the zone crop")] = None,
    zone_id: Annotated[int | None, Form()] = None,
) -> dict[str, Any]:
    """Screen a leaf photo. Possible/uncertain results are stored; refusals are returned but not stored."""
    farm = access.farm_for(db, user, farm_id)
    zone = access.zone_for(db, user, zone_id) if zone_id is not None else None
    if zone is not None and zone.farm_id != farm.id:
        raise UnprocessableError("zone_id belongs to another farm.")
    data = file.file.read()
    try:
        validate_upload(file.content_type, data)
        result = svc.screen_and_store(db, user, farm.id, zone, crop, data)
    except recognizer.BadImageError as e:
        raise UnprocessableError(str(e)) from e
    except recognizer.ModelUnavailableError as e:
        raise ModelUnavailableApiError(str(e)) from e
    if result["saved"]:
        det = db.get(DiseaseDetection, result["detection_id"])
        assert det is not None
        crud.audit(db, "create", det, {"outcome": result["outcome"], "label": result["label"]})
    db.commit()
    return attach_knowledge(result)


def attach_knowledge(result: dict[str, Any]) -> dict[str, Any]:
    """Guidance comes from the structured knowledge layer, and only for a result that passed every check."""
    if result["outcome"] == "possible_disease":
        result["knowledge_key"] = knowledge.key_for(result["crop"], result["disease"])
        result["knowledge"] = knowledge.info(result["knowledge_key"])
    elif result["outcome"] == "possible_healthy":
        result["healthy_guidance"] = knowledge.HEALTHY_GUIDANCE
    return result


@router.get("/knowledge/diseases", response_model=list[DiseaseKnowledge], tags=["knowledge"])
def list_knowledge(user: CurrentUser) -> list[dict[str, Any]]:
    """Every disease the installed models can report, with structured guidance."""
    return [e.to_dict() for e in knowledge.ENTRIES]


@router.get("/knowledge/diseases/{key}", response_model=DiseaseKnowledge, tags=["knowledge"])
def get_knowledge(key: str, user: CurrentUser) -> dict[str, Any]:
    found = knowledge.info(key)
    if found is None:
        raise NotFoundError("No knowledge entry with that key.")
    return found


@router.get("/farms/{farm_id}/vision/disease-checks", response_model=Page[DiseaseRecord])
def list_checks(farm_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.farm_for(db, user, farm_id)
    stmt = (
        select(DiseaseDetection)
        .where(DiseaseDetection.farm_id == farm_id)
        .order_by(DiseaseDetection.detected_at.desc(), DiseaseDetection.id.desc())
    )
    return crud.paginate(db, stmt, page)


def _record(db: DbSession, user: CurrentUser, record_id: int) -> DiseaseDetection:
    rec, _ = access.record_for(db, user, DiseaseDetection, record_id, "Disease check")
    return rec


@router.get("/vision/disease-checks/{record_id}", response_model=DiseaseRecord)
def get_check(record_id: int, user: CurrentUser, db: DbSession) -> DiseaseDetection:
    return _record(db, user, record_id)


@router.get("/vision/disease-checks/{record_id}/image", response_class=FileResponse)
def check_image(record_id: int, user: CurrentUser, db: DbSession) -> FileResponse:
    path = image_path(_record(db, user, record_id).image_uri)
    if path is None:
        raise NotFoundError("Image file not found.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/vision/disease-checks/{record_id}", status_code=204)
def delete_check(record_id: int, user: CurrentUser, db: DbSession) -> Response:
    rec = _record(db, user, record_id)
    path = image_path(rec.image_uri)
    crud.audit(db, "delete", rec)
    db.delete(rec)
    db.commit()
    if path is not None:
        path.unlink(missing_ok=True)
    return no_content()
