"""Smart irrigation endpoints (Phase 12)."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.auth import CurrentUser
from app.api.deps import DbSession
from app.api.errors import ConflictError
from app.models import IrrigationEvent
from app.schemas.common import InputModel
from app.services import access, crud, soil
from app.services import irrigation_plan as svc

router = APIRouter(tags=["smart irrigation"])


class ScheduleInput(InputModel):
    date: date


@router.get("/zones/{zone_id}/irrigation/plan")
def zone_plan(zone_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Multi-day plan: when, how much (net, gross, litres), best window, daily water balance."""
    return soil.json_safe(svc.zone_plan(db, access.zone_for(db, user, zone_id)))  # type: ignore[no-any-return]


@router.get("/farms/{farm_id}/irrigation/plan")
def farm_plan(farm_id: int, user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    """One line per zone: status, next irrigation and volume over the horizon."""
    return soil.json_safe(svc.farm_overview(db, access.farm_for(db, user, farm_id)))  # type: ignore[no-any-return]


@router.post("/zones/{zone_id}/irrigation/schedule", status_code=201)
def schedule(zone_id: int, body: ScheduleInput, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Create a scheduled irrigation event from the plan's irrigation on ``date``."""
    zone = access.zone_for(db, user, zone_id)
    event = svc.schedule(db, user, zone, body.date)
    if event is None:
        raise ConflictError(f"The current plan has no unscheduled irrigation on {body.date}.")
    crud.audit(
        db, "create", event, {"trigger": "scheduled", "date": body.date.isoformat()}, farm_id=zone.farm_id
    )
    db.commit()
    db.refresh(event)
    return _event(event)


@router.get("/zones/{zone_id}/irrigation/water-use")
def water_use(
    zone_id: int, user: CurrentUser, db: DbSession, days: Annotated[int, Query(ge=1, le=90)] = 7
) -> dict[str, Any]:
    """Water applied (completed events) vs an estimate of crop need over the last ``days`` days."""
    return soil.json_safe(svc.water_use(db, access.zone_for(db, user, zone_id), days))  # type: ignore[no-any-return]


def _event(e: IrrigationEvent) -> dict[str, Any]:
    volume = None if e.volume_liters is None else float(e.volume_liters)
    return {
        "id": e.id, "zone_id": e.zone_id, "method": e.method, "trigger": e.trigger, "status": e.status,
        "scheduled_for": e.scheduled_for, "volume_liters": volume, "notes": e.notes,
    }  # fmt: skip
