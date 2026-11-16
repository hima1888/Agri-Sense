"""Plant & produce recognition endpoints (Phase 9)."""

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.auth import CurrentUser
from app.api.deps import DbSession, Paging, no_content
from app.api.errors import ApiError, NotFoundError, UnprocessableError
from app.models import PlantDetection
from app.schemas.common import Page
from app.schemas.vision import Detection, ModelInfo, Recognition
from app.services import access, crud
from app.services import vision as svc
from app.vision import recognizer

router = APIRouter(tags=["plant recognition"])


class ModelUnavailableApiError(ApiError):
    status_code = 503
    code = "model_unavailable"


@router.get("/vision/model", response_model=ModelInfo)
def model_info(user: CurrentUser) -> dict[str, Any]:
    """The recognition model, its published metrics and the produce classes it can report."""
    return recognizer.model_info()


@router.post("/farms/{farm_id}/vision/recognitions", response_model=Recognition, status_code=201)
def recognize(
    farm_id: int,
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP photo")],
    zone_id: Annotated[int | None, Form()] = None,
) -> dict[str, Any]:
    """Recognise produce in a photo. Recognised/uncertain results are stored; unsupported ones are not."""
    farm = access.farm_for(db, user, farm_id)
    zone = access.zone_for(db, user, zone_id) if zone_id is not None else None
    if zone is not None and zone.farm_id != farm.id:
        raise UnprocessableError("zone_id belongs to another farm.")
    data = file.file.read()
    try:
        svc.validate_upload(file.content_type, data)
        result = svc.recognize_and_store(db, user, farm.id, zone, data)
    except recognizer.BadImageError as e:
        raise UnprocessableError(str(e)) from e
    except recognizer.ModelUnavailableError as e:
        raise ModelUnavailableApiError(str(e)) from e
    if result["saved"]:
        detection = db.get(PlantDetection, result["detection_id"])
        assert detection is not None
        crud.audit(db, "create", detection, {"label": result["label"], "confidence": result["confidence"]})
    db.commit()
    return result


@router.get("/farms/{farm_id}/vision/recognitions", response_model=Page[Detection])
def list_recognitions(farm_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.farm_for(db, user, farm_id)
    stmt = (
        select(PlantDetection)
        .where(PlantDetection.farm_id == farm_id)
        .order_by(PlantDetection.detected_at.desc(), PlantDetection.id.desc())
    )
    return crud.paginate(db, stmt, page)


def _detection(db: DbSession, user: CurrentUser, detection_id: int) -> PlantDetection:
    det, _ = access.record_for(db, user, PlantDetection, detection_id, "Recognition")
    return det


@router.get("/vision/recognitions/{detection_id}", response_model=Detection)
def get_recognition(detection_id: int, user: CurrentUser, db: DbSession) -> PlantDetection:
    return _detection(db, user, detection_id)


@router.get("/vision/recognitions/{detection_id}/image", response_class=FileResponse)
def recognition_image(detection_id: int, user: CurrentUser, db: DbSession) -> FileResponse:
    path = svc.image_path(_detection(db, user, detection_id).image_uri)
    if path is None:
        raise NotFoundError("Image file not found.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/vision/recognitions/{detection_id}", status_code=204)
def delete_recognition(detection_id: int, user: CurrentUser, db: DbSession) -> Response:
    det = _detection(db, user, detection_id)
    path = svc.image_path(det.image_uri)
    crud.audit(db, "delete", det)
    db.delete(det)
    db.commit()
    if path is not None:
        path.unlink(missing_ok=True)
    return no_content()
