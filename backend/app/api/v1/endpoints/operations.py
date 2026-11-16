"""Field operations (irrigation, fertilizer, pesticide) and alerts."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import CurrentUser
from app.api.deps import DbSession, Paging, no_content
from app.api.errors import ConflictError, UnprocessableError
from app.models import (
    Alert,
    DiseaseDetection,
    FertilizerApplication,
    IrrigationEvent,
    PesticideApplication,
    Sensor,
    User,
)
from app.models.enums import AlertSeverity, AlertStatus
from app.schemas.common import Page
from app.schemas.operations import (
    AlertCreate,
    AlertRead,
    FertilizerCreate,
    FertilizerRead,
    IrrigationCreate,
    IrrigationRead,
    IrrigationUpdate,
    PesticideCreate,
    PesticideRead,
)
from app.services import access, crud
from app.services.scoping import require_cycle_in_zone, require_zone_in_farm

router = APIRouter()

DateFrom = Annotated[datetime | None, Query(description="Inclusive lower bound")]
DateTo = Annotated[datetime | None, Query(description="Exclusive upper bound")]


# --- irrigation ------------------------------------------------------------
@router.post(
    "/zones/{zone_id}/irrigation-events", response_model=IrrigationRead, status_code=201, tags=["irrigation"]
)
def create_irrigation(
    zone_id: int, body: IrrigationCreate, user: CurrentUser, db: DbSession
) -> IrrigationEvent:
    zone = access.zone_for(db, user, zone_id)
    return crud.create(
        db, IrrigationEvent, body, zone_id=zone_id, created_by=user.id, audit_farm_id=zone.farm_id
    )


@router.get("/zones/{zone_id}/irrigation-events", response_model=Page[IrrigationRead], tags=["irrigation"])
def list_irrigation(zone_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.zone_for(db, user, zone_id)
    stmt = select(IrrigationEvent).where(IrrigationEvent.zone_id == zone_id)
    return crud.paginate(db, stmt.order_by(IrrigationEvent.id.desc()), page)


@router.get("/irrigation-events/{event_id}", response_model=IrrigationRead, tags=["irrigation"])
def get_irrigation(event_id: int, user: CurrentUser, db: DbSession) -> IrrigationEvent:
    return access.record_for(db, user, IrrigationEvent, event_id, "Irrigation event")[0]


@router.patch("/irrigation-events/{event_id}", response_model=IrrigationRead, tags=["irrigation"])
def update_irrigation(
    event_id: int, body: IrrigationUpdate, user: CurrentUser, db: DbSession
) -> IrrigationEvent:
    event, farm_id = access.record_for(db, user, IrrigationEvent, event_id, "Irrigation event")
    return crud.update(db, event, body, audit_farm_id=farm_id)


# --- fertilizer ------------------------------------------------------------
@router.post(
    "/zones/{zone_id}/fertilizer-applications",
    response_model=FertilizerRead,
    status_code=201,
    tags=["nutrients"],
)
def create_fertilizer(
    zone_id: int, body: FertilizerCreate, user: CurrentUser, db: DbSession
) -> FertilizerApplication:
    zone = access.zone_for(db, user, zone_id)
    require_cycle_in_zone(db, body.crop_cycle_id, zone_id)
    return crud.create(
        db, FertilizerApplication, body, zone_id=zone_id, applied_by=user.id, audit_farm_id=zone.farm_id
    )


@router.get(
    "/zones/{zone_id}/fertilizer-applications", response_model=Page[FertilizerRead], tags=["nutrients"]
)
def list_fertilizer(
    zone_id: int, user: CurrentUser, db: DbSession, page: Paging, start: DateFrom = None, end: DateTo = None
) -> dict[str, object]:
    access.zone_for(db, user, zone_id)
    stmt = select(FertilizerApplication).where(FertilizerApplication.zone_id == zone_id)
    if start:
        stmt = stmt.where(FertilizerApplication.applied_at >= start)
    if end:
        stmt = stmt.where(FertilizerApplication.applied_at < end)
    return crud.paginate(db, stmt.order_by(FertilizerApplication.applied_at.desc()), page)


@router.delete("/fertilizer-applications/{application_id}", status_code=204, tags=["nutrients"])
def delete_fertilizer(application_id: int, user: CurrentUser, db: DbSession) -> Response:
    record, farm_id = access.record_for(
        db, user, FertilizerApplication, application_id, "Fertilizer application"
    )
    crud.delete(db, record, audit_farm_id=farm_id)
    return no_content()


# --- pesticide -------------------------------------------------------------
@router.post(
    "/zones/{zone_id}/pesticide-applications",
    response_model=PesticideRead,
    status_code=201,
    tags=["pesticides"],
)
def create_pesticide(
    zone_id: int, body: PesticideCreate, user: CurrentUser, db: DbSession
) -> PesticideApplication:
    zone = access.zone_for(db, user, zone_id)
    require_cycle_in_zone(db, body.crop_cycle_id, zone_id)
    if body.disease_detection_id is not None:
        det = db.get(DiseaseDetection, body.disease_detection_id)
        if det is None or det.farm_id != zone.farm_id:
            raise UnprocessableError("disease_detection_id is not a disease check on this farm.")
    return crud.create(
        db, PesticideApplication, body, zone_id=zone_id, applied_by=user.id, audit_farm_id=zone.farm_id
    )


@router.get(
    "/zones/{zone_id}/pesticide-applications", response_model=Page[PesticideRead], tags=["pesticides"]
)
def list_pesticide(
    zone_id: int, user: CurrentUser, db: DbSession, page: Paging, start: DateFrom = None, end: DateTo = None
) -> dict[str, object]:
    access.zone_for(db, user, zone_id)
    stmt = select(PesticideApplication).where(PesticideApplication.zone_id == zone_id)
    if start:
        stmt = stmt.where(PesticideApplication.applied_at >= start)
    if end:
        stmt = stmt.where(PesticideApplication.applied_at < end)
    return crud.paginate(db, stmt.order_by(PesticideApplication.applied_at.desc()), page)


@router.delete("/pesticide-applications/{application_id}", status_code=204, tags=["pesticides"])
def delete_pesticide(application_id: int, user: CurrentUser, db: DbSession) -> Response:
    record, farm_id = access.record_for(
        db, user, PesticideApplication, application_id, "Pesticide application"
    )
    crud.delete(db, record, audit_farm_id=farm_id)
    return no_content()


# --- alerts ----------------------------------------------------------------
@router.post("/farms/{farm_id}/alerts", response_model=AlertRead, status_code=201, tags=["alerts"])
def create_alert(farm_id: int, body: AlertCreate, user: CurrentUser, db: DbSession) -> Alert:
    access.farm_for(db, user, farm_id)
    require_zone_in_farm(db, body.zone_id, farm_id)
    if body.sensor_id is not None:
        sensor = db.get(Sensor, body.sensor_id)
        if sensor is None or sensor.farm_id != farm_id:
            raise UnprocessableError(
                f"Sensor {body.sensor_id} does not belong to farm {farm_id}.", {"field": "sensor_id"}
            )
    return crud.create(db, Alert, body, farm_id=farm_id)


@router.get("/farms/{farm_id}/alerts", response_model=Page[AlertRead], tags=["alerts"])
def list_alerts(
    farm_id: int,
    user: CurrentUser,
    db: DbSession,
    page: Paging,
    status: Annotated[AlertStatus | None, Query()] = None,
    severity: Annotated[AlertSeverity | None, Query()] = None,
) -> dict[str, object]:
    access.farm_for(db, user, farm_id)
    stmt = select(Alert).where(Alert.farm_id == farm_id).order_by(Alert.triggered_at.desc())
    if status:
        stmt = stmt.where(Alert.status == status)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    return crud.paginate(db, stmt, page)


@router.get("/alerts/{alert_id}", response_model=AlertRead, tags=["alerts"])
def get_alert(alert_id: int, user: CurrentUser, db: DbSession) -> Alert:
    return access.record_for(db, user, Alert, alert_id, "Alert")[0]


ALERT_TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged", "resolved"},
    "acknowledged": {"resolved"},
    "resolved": set(),
}


def _transition(db: Session, user: User, alert_id: int, target: AlertStatus) -> Alert:
    """open -> acknowledged -> resolved; open -> resolved. Resolved alerts are final."""
    alert, _ = access.record_for(db, user, Alert, alert_id, "Alert")
    if target not in ALERT_TRANSITIONS[alert.status]:
        raise ConflictError(f"Cannot move alert from '{alert.status}' to '{target}'.")
    now = datetime.now(UTC)
    alert.status = target
    if target == "acknowledged":
        alert.acknowledged_at = now
        alert.acknowledged_by = user.id
    else:
        alert.resolved_at = now
    crud.audit(db, "acknowledge" if target == "acknowledged" else "resolve", alert, {"status": target})
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertRead, tags=["alerts"])
def acknowledge_alert(alert_id: int, user: CurrentUser, db: DbSession) -> Alert:
    return _transition(db, user, alert_id, "acknowledged")


@router.post("/alerts/{alert_id}/resolve", response_model=AlertRead, tags=["alerts"])
def resolve_alert(alert_id: int, user: CurrentUser, db: DbSession) -> Alert:
    return _transition(db, user, alert_id, "resolved")
