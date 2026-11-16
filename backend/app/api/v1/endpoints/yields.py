"""Yield estimate endpoints (Phase 14)."""

from typing import Annotated, Any

from fastapi import APIRouter, Response
from pydantic import Field
from sqlalchemy import select

from app.api.auth import CurrentUser
from app.api.deps import DbSession, Paging, no_content
from app.api.errors import UnprocessableError
from app.domain.yield_model import KY, KY_SOURCE
from app.models import AIPrediction, CropCycle
from app.schemas.common import InputModel
from app.schemas.soil import SavedAssessment
from app.services import access, crud, soil
from app.services import yield_service as svc

router = APIRouter(tags=["yield"])


class YieldReference(InputModel):
    kg_ha: Annotated[float, Field(gt=0, le=200_000)]
    source: Annotated[str, Field(min_length=3, max_length=200)]


@router.get("/yield/ky")
def ky_table(user: CurrentUser) -> dict[str, Any]:
    """The FAO-33 yield-response factors used, and their source."""
    return {"source": KY_SOURCE, "ky": KY}


@router.get("/zones/{zone_id}/yield")
def zone_yield(zone_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Water-limited yield range for the zone's current crop cycle, with factors and limitations."""
    return soil.json_safe(svc.zone_estimate(db, access.zone_for(db, user, zone_id)))  # type: ignore[no-any-return]


@router.post("/zones/{zone_id}/yield/predictions", response_model=SavedAssessment, status_code=201)
def save_prediction(zone_id: int, user: CurrentUser, db: DbSession) -> AIPrediction:
    """Store the current estimate (ai_predictions, type yield) so it can be back-tested after harvest."""
    zone = access.zone_for(db, user, zone_id)
    rec = svc.save(db, zone)
    if rec is None:
        raise UnprocessableError("Nothing to save: this zone has no yield estimate yet.")
    crud.audit(db, "create", rec, {"prediction_type": "yield"})
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/zones/{zone_id}/yield/predictions")
def list_predictions(zone_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.zone_for(db, user, zone_id)
    stmt = (
        select(AIPrediction)
        .where(AIPrediction.zone_id == zone_id, AIPrediction.prediction_type == "yield")
        .order_by(AIPrediction.created_at.desc(), AIPrediction.id.desc())
    )
    page_ = crud.paginate(db, stmt, page)
    page_["items"] = [
        {
            "id": p.id,
            "crop_cycle_id": p.crop_cycle_id,
            "created_at": p.created_at,
            "confidence": float(p.confidence),
            "predicted_value": p.predicted_value,
        }
        for p in page_["items"]
    ]
    return page_


@router.get("/farms/{farm_id}/yield/backtest")
def backtest(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Saved estimates vs recorded yields of harvested cycles (the only real accuracy measure)."""
    return soil.json_safe(svc.backtest(db, access.farm_for(db, user, farm_id)))  # type: ignore[no-any-return]


@router.put("/crop-cycles/{cycle_id}/yield-reference")
def set_reference(cycle_id: int, body: YieldReference, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Record the attainable (water-unstressed) yield for this cycle and where it came from."""
    cycle, farm_id = access.record_for(db, user, CropCycle, cycle_id, "Crop cycle")
    before = cycle.yield_reference
    cycle.yield_reference = body.model_dump()
    crud.audit(db, "update", cycle, {"yield_reference": [before, cycle.yield_reference]}, farm_id=farm_id)
    db.commit()
    return {"cycle_id": cycle.id, "yield_reference": cycle.yield_reference}


@router.delete("/crop-cycles/{cycle_id}/yield-reference", status_code=204)
def clear_reference(cycle_id: int, user: CurrentUser, db: DbSession) -> Response:
    cycle, farm_id = access.record_for(db, user, CropCycle, cycle_id, "Crop cycle")
    crud.audit(db, "update", cycle, {"yield_reference": [cycle.yield_reference, None]}, farm_id=farm_id)
    cycle.yield_reference = None
    db.commit()
    return no_content()
