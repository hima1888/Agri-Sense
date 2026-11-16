"""Create a simulated sensor kit for a zone: one `simulator` device plus its sensors."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ConflictError, UnprocessableError
from app.domain.sensors import SENSOR_SPECS
from app.models import Device, Farm, FarmZone, Sensor
from app.models.enums import SENSOR_TYPES, SensorType
from app.services import crud


def provision_zone(
    db: Session, zone: FarmZone, sensor_types: list[SensorType] | None = None
) -> tuple[Device, list[Sensor]]:
    farm = db.get(Farm, zone.farm_id)
    assert farm is not None
    if farm.latitude is None or farm.longitude is None:
        raise UnprocessableError(
            "Set the farm's latitude and longitude first: "
            "the simulator uses them for daylight and temperature.",
            {"field": "farm.latitude"},
        )
    existing = db.scalar(
        select(Device).where(Device.zone_id == zone.id, Device.device_type == "simulator").limit(1)
    )
    if existing is not None:
        raise ConflictError(f"Zone {zone.id} already has a simulator kit (device {existing.id}).")

    types: list[SensorType] = list(dict.fromkeys(sensor_types or SENSOR_TYPES))
    now = datetime.now(UTC)
    device = Device(
        farm_id=farm.id,
        zone_id=zone.id,
        name=f"Simulator · {zone.name}",
        device_type="simulator",
        source="simulated",
        protocol="simulator",
        firmware_version="agri-sense-sim/1",
        status="active",
    )
    db.add(device)
    db.flush()
    crud.audit(db, "create", device, {"name": device.name, "device_type": "simulator"})

    sensors: list[Sensor] = []
    for i, sensor_type in enumerate(types):
        spec = SENSOR_SPECS[sensor_type]
        sensor = Sensor(
            farm_id=farm.id,
            zone_id=zone.id,
            device_id=device.id,
            name=f"{spec.label} · {zone.name}",
            sensor_type=sensor_type,
            unit=spec.unit,
            source="simulated",
            hardware_model="simulated",
            status="active",
            min_valid=spec.min_valid,
            max_valid=spec.max_valid,
            # Spread across a 4-column grid in the zone's local digital-twin coordinates.
            twin_position={"x": (i % 4) * 3.0 - 4.5, "y": 0.5, "z": (i // 4) * 3.0 - 3.0},
            installed_at=now,
        )
        db.add(sensor)
        sensors.append(sensor)
    db.flush()
    for sensor in sensors:
        crud.audit(db, "create", sensor, {"sensor_type": sensor.sensor_type, "source": "simulated"})
    db.commit()
    for obj in (device, *sensors):
        db.refresh(obj)
    return device, sensors
