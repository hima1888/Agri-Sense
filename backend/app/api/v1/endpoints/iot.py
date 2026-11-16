"""Devices, sensors and sensor readings."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.api.auth import CurrentUser
from app.api.deps import DbSession, Paging, no_content
from app.api.errors import NotFoundError
from app.api.v1.endpoints.realtime import BroadcasterDep
from app.domain.sensors import SENSOR_SPECS
from app.models import Device, Sensor, SensorReading
from app.models.enums import DataSource, SensorType
from app.schemas.common import Page
from app.schemas.iot import (
    DeviceCreate,
    DeviceRead,
    DeviceUpdate,
    IngestResult,
    ReadingBatch,
    ReadingRead,
    ReadingSeries,
    SensorCreate,
    SensorRead,
    SensorUpdate,
)
from app.services import access, crud, readings
from app.services.scoping import require_device_compatible, require_zone_in_farm

router = APIRouter()


# --- devices ---------------------------------------------------------------
@router.post("/farms/{farm_id}/devices", response_model=DeviceRead, status_code=201, tags=["devices"])
def create_device(farm_id: int, body: DeviceCreate, user: CurrentUser, db: DbSession) -> Device:
    access.farm_for(db, user, farm_id)
    require_zone_in_farm(db, body.zone_id, farm_id)
    # Source is derived, not chosen: only the simulator produces simulated data.
    source = "simulated" if body.device_type == "simulator" else "hardware"
    return crud.create(db, Device, body, farm_id=farm_id, source=source)


@router.get("/farms/{farm_id}/devices", response_model=Page[DeviceRead], tags=["devices"])
def list_devices(farm_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.farm_for(db, user, farm_id)
    return crud.paginate(db, select(Device).where(Device.farm_id == farm_id).order_by(Device.id), page)


@router.get("/devices/{device_id}", response_model=DeviceRead, tags=["devices"])
def get_device(device_id: int, user: CurrentUser, db: DbSession) -> Device:
    return access.record_for(db, user, Device, device_id, "Device")[0]


@router.patch("/devices/{device_id}", response_model=DeviceRead, tags=["devices"])
def update_device(device_id: int, body: DeviceUpdate, user: CurrentUser, db: DbSession) -> Device:
    device, farm_id = access.record_for(db, user, Device, device_id, "Device")
    if "zone_id" in body.model_fields_set:
        require_zone_in_farm(db, body.zone_id, farm_id)
    return crud.update(db, device, body)


@router.delete("/devices/{device_id}", status_code=204, tags=["devices"])
def delete_device(device_id: int, user: CurrentUser, db: DbSession) -> Response:
    """Sensors attached to the device are kept (their device_id becomes null)."""
    crud.delete(db, access.record_for(db, user, Device, device_id, "Device")[0])
    return no_content()


# --- sensors ---------------------------------------------------------------
@router.get("/sensor-types", tags=["sensors"])
def list_sensor_types(_: CurrentUser) -> list[dict[str, Any]]:
    """Supported sensor types with their canonical unit and plausible range."""
    return [
        {
            "sensor_type": t,
            "label": s.label,
            "unit": s.unit,
            "min_valid": s.min_valid,
            "max_valid": s.max_valid,
        }
        for t, s in SENSOR_SPECS.items()
    ]


@router.post("/farms/{farm_id}/sensors", response_model=SensorRead, status_code=201, tags=["sensors"])
def create_sensor(farm_id: int, body: SensorCreate, user: CurrentUser, db: DbSession) -> Sensor:
    access.farm_for(db, user, farm_id)
    require_zone_in_farm(db, body.zone_id, farm_id)
    require_device_compatible(db, body.device_id, farm_id, body.source)
    spec = SENSOR_SPECS[body.sensor_type]
    defaults = {
        "unit": body.unit or spec.unit,
        "min_valid": spec.min_valid if body.min_valid is None else body.min_valid,
        "max_valid": spec.max_valid if body.max_valid is None else body.max_valid,
    }
    return crud.create(db, Sensor, body.model_copy(update=defaults), farm_id=farm_id)


@router.get("/farms/{farm_id}/sensors", response_model=Page[SensorRead], tags=["sensors"])
def list_sensors(
    farm_id: int,
    user: CurrentUser,
    db: DbSession,
    page: Paging,
    zone_id: Annotated[int | None, Query()] = None,
    sensor_type: Annotated[SensorType | None, Query()] = None,
    source: Annotated[DataSource | None, Query()] = None,
) -> dict[str, object]:
    access.farm_for(db, user, farm_id)
    stmt = select(Sensor).where(Sensor.farm_id == farm_id).order_by(Sensor.id)
    if zone_id is not None:
        stmt = stmt.where(Sensor.zone_id == zone_id)
    if sensor_type:
        stmt = stmt.where(Sensor.sensor_type == sensor_type)
    if source:
        stmt = stmt.where(Sensor.source == source)
    return crud.paginate(db, stmt, page)


@router.get("/sensors/{sensor_id}", response_model=SensorRead, tags=["sensors"])
def get_sensor(sensor_id: int, user: CurrentUser, db: DbSession) -> Sensor:
    return access.record_for(db, user, Sensor, sensor_id, "Sensor")[0]


@router.patch("/sensors/{sensor_id}", response_model=SensorRead, tags=["sensors"])
def update_sensor(sensor_id: int, body: SensorUpdate, user: CurrentUser, db: DbSession) -> Sensor:
    sensor, farm_id = access.record_for(db, user, Sensor, sensor_id, "Sensor")
    if "zone_id" in body.model_fields_set:
        require_zone_in_farm(db, body.zone_id, farm_id)
    if "device_id" in body.model_fields_set:
        require_device_compatible(db, body.device_id, farm_id, sensor.source)
    return crud.update(db, sensor, body)


@router.delete("/sensors/{sensor_id}", status_code=204, tags=["sensors"])
def delete_sensor(sensor_id: int, user: CurrentUser, db: DbSession) -> Response:
    """Also deletes the sensor's readings."""
    crud.delete(db, access.record_for(db, user, Sensor, sensor_id, "Sensor")[0])
    return no_content()


# --- readings --------------------------------------------------------------
@router.post("/sensors/{sensor_id}/readings", response_model=IngestResult, tags=["readings"])
def ingest_readings(
    sensor_id: int, body: ReadingBatch, user: CurrentUser, db: DbSession, broadcaster: BroadcasterDep
) -> IngestResult:
    """Batch-ingest up to 1000 readings. Idempotent per (sensor, recorded_at)."""
    sensor, _ = access.record_for(db, user, Sensor, sensor_id, "Sensor")
    result, stored = readings.ingest(db, sensor, body.readings)
    for farm_id, payload in readings.events_by_farm(stored).items():  # after commit
        broadcaster.publish_threadsafe(farm_id, readings.READINGS_EVENT, payload)
    return result


@router.get("/sensors/{sensor_id}/readings", response_model=ReadingSeries, tags=["readings"])
def get_readings(
    sensor_id: int,
    user: CurrentUser,
    db: DbSession,
    start: Annotated[datetime | None, Query(description="Inclusive. Default: end - 24h")] = None,
    end: Annotated[datetime | None, Query(description="Exclusive. Default: now")] = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 2_000,
) -> ReadingSeries:
    """Readings in a time window, oldest first. If more than `limit` exist, the most recent are returned."""
    sensor, _ = access.record_for(db, user, Sensor, sensor_id, "Sensor")
    window_start, window_end, rows = readings.query(db, sensor, start, end, limit)
    return ReadingSeries(
        sensor_id=sensor.id,
        sensor_type=sensor.sensor_type,
        unit=sensor.unit,
        source=sensor.source,
        is_simulated=sensor.is_simulated,
        start=window_start,
        end=window_end,
        count=len(rows),
        readings=[ReadingRead.model_validate(r) for r in rows],
    )


@router.get("/sensors/{sensor_id}/readings/latest", response_model=ReadingRead, tags=["readings"])
def latest_reading(sensor_id: int, user: CurrentUser, db: DbSession) -> SensorReading:
    access.record_for(db, user, Sensor, sensor_id, "Sensor")
    row = db.scalars(
        select(SensorReading)
        .where(SensorReading.sensor_id == sensor_id)
        .order_by(SensorReading.recorded_at.desc())
        .limit(1)
    ).first()
    if row is None:
        raise NotFoundError(f"Sensor {sensor_id} has no readings yet.")
    return row
