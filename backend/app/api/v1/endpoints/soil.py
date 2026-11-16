"""Soil intelligence endpoints."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.api.auth import CurrentUser
from app.api.deps import DbSession, Paging
from app.api.errors import UnprocessableError
from app.models import AIPrediction
from app.schemas.common import Page
from app.schemas.soil import SavedAssessment, SoilAssessment, ZoneSoilSummary
from app.services import access, crud, soil

router = APIRouter(tags=["soil intelligence"])


@router.get("/zones/{zone_id}/soil", response_model=SoilAssessment)
def zone_soil(zone_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Explainable soil assessment for a zone, computed now from stored records."""
    return soil.assess(db, access.zone_for(db, user, zone_id))


@router.get("/farms/{farm_id}/soil", response_model=list[ZoneSoilSummary])
def farm_soil(farm_id: int, user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    """One-line soil summary per zone."""
    return soil.summarize_for_farm(db, access.farm_for(db, user, farm_id))


@router.post("/zones/{zone_id}/soil/assessments", response_model=SavedAssessment, status_code=201)
def save_assessment(zone_id: int, user: CurrentUser, db: DbSession) -> AIPrediction:
    """Store the current assessment (as an ai_predictions row of type soil_health) for history."""
    zone = access.zone_for(db, user, zone_id)
    a = soil.assess(db, zone)
    if a["index"] is None:
        raise UnprocessableError("Nothing to save: no soil component could be assessed for this zone.")
    record = AIPrediction(
        farm_id=zone.farm_id,
        zone_id=zone.id,
        prediction_type="soil_health",
        predicted_value=soil.json_safe(soil.snapshot_values(a)),
        confidence=Decimal(str(a["confidence"])),
        factors=soil.json_safe(a["factors"]),
        limitations=" ".join(a["limitations"]),
        input_snapshot=soil.json_safe(
            {"method": a["method"], "inputs": a["inputs"], "guidance": a["guidance"]}
        ),
        valid_from=a["assessed_at"],
    )
    db.add(record)
    db.flush()
    crud.audit(db, "create", record, {"prediction_type": "soil_health", "index": a["index"]})
    db.commit()
    db.refresh(record)
    return record


@router.get("/zones/{zone_id}/soil/assessments", response_model=Page[SavedAssessment])
def list_assessments(zone_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.zone_for(db, user, zone_id)
    stmt = (
        select(AIPrediction)
        .where(AIPrediction.zone_id == zone_id, AIPrediction.prediction_type == "soil_health")
        .order_by(AIPrediction.created_at.desc(), AIPrediction.id.desc())
    )
    return crud.paginate(db, stmt, page)
