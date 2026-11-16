"""Data-integrity behaviour of the schema: constraints, cascades, triggers."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AIPrediction,
    Crop,
    CropCycle,
    Device,
    Farm,
    FarmZone,
    Sensor,
    SensorReading,
    SoilMeasurement,
    User,
)

NOW = datetime(2026, 11, 13, 8, 0, tzinfo=UTC)


@pytest.fixture
def farm(db: Session) -> Farm:
    user = User(email="grower@example.com", full_name="Test Grower")
    f = Farm(owner=user, name="Test Farm", latitude=Decimal("17.385"), longitude=Decimal("78.4867"))
    f.zones.append(FarmZone(name="North Block", zone_type="field", irrigation_method="drip"))
    db.add(f)
    db.flush()
    return f


def expect_integrity_error(db: Session, action: Callable[[], object]) -> str:
    with pytest.raises(IntegrityError) as exc, db.begin_nested():
        action()
        db.flush()
    return str(exc.value.orig)


def test_full_iot_chain_round_trip(db: Session, farm: Farm) -> None:
    zone = farm.zones[0]
    device = Device(
        farm_id=farm.id,
        zone_id=zone.id,
        name="Sim node 1",
        device_type="simulator",
        source="simulated",
        protocol="simulator",
    )
    db.add(device)
    db.flush()
    sensor = Sensor(
        farm_id=farm.id,
        zone_id=zone.id,
        device_id=device.id,
        name="Soil moisture A",
        sensor_type="soil_moisture",
        unit="%",
        source="simulated",
        min_valid=0,
        max_valid=100,
    )
    db.add(sensor)
    db.flush()
    db.add_all(
        SensorReading(sensor_id=sensor.id, recorded_at=NOW + timedelta(minutes=i), value=30.0 + i)
        for i in range(5)
    )
    db.flush()

    latest = db.scalars(
        select(SensorReading)
        .where(SensorReading.sensor_id == sensor.id)
        .order_by(SensorReading.recorded_at.desc())
    ).first()
    assert latest is not None
    assert latest.value == 34.0
    assert latest.quality == "good"
    assert db.scalar(select(Sensor.source).where(Sensor.id == sensor.id)) == "simulated"


def test_duplicate_reading_for_same_sensor_and_time_is_rejected(db: Session, farm: Farm) -> None:
    sensor = Sensor(farm_id=farm.id, name="T", sensor_type="temperature", unit="°C", source="simulated")
    db.add(sensor)
    db.flush()
    db.add(SensorReading(sensor_id=sensor.id, recorded_at=NOW, value=21.5))
    db.flush()
    msg = expect_integrity_error(
        db, lambda: db.add(SensorReading(sensor_id=sensor.id, recorded_at=NOW, value=22))
    )
    assert "uq_sensor_readings_sensor_id_recorded_at" in msg


@pytest.mark.parametrize(
    ("factory", "constraint"),
    [
        (
            lambda f: Sensor(farm_id=f.id, name="x", sensor_type="radar", unit="?", source="simulated"),
            "ck_sensors_sensor_type_valid",
        ),
        (
            lambda f: Sensor(farm_id=f.id, name="x", sensor_type="light", unit="lx", source="imaginary"),
            "ck_sensors_source_valid",
        ),
        (
            lambda f: Device(
                farm_id=f.id, name="x", device_type="simulator", source="hardware", protocol="http"
            ),
            "ck_devices_simulator_source_consistent",
        ),
        (
            lambda f: SoilMeasurement(zone_id=f.zones[0].id, measured_at=NOW, source="lab", ph=Decimal("15")),
            "ck_soil_measurements_ph_range",
        ),
        (
            lambda f: AIPrediction(
                farm_id=f.id,
                prediction_type="yield",
                predicted_value={"value": 1},
                confidence=Decimal("1.5"),
                factors=[],
                limitations="n/a",
            ),
            "ck_ai_predictions_confidence_range",
        ),
        (lambda f: FarmZone(farm_id=f.id, name="North Block"), "uq_farm_zones_farm_id_name"),
    ],
)
def test_invalid_data_is_rejected_by_the_database(
    db: Session, farm: Farm, factory: Callable[[Farm], object], constraint: str
) -> None:
    assert constraint in expect_integrity_error(db, lambda: db.add(factory(farm)))


def test_user_email_is_unique_case_insensitively(db: Session, farm: Farm) -> None:
    msg = expect_integrity_error(db, lambda: db.add(User(email="GROWER@example.com")))
    assert "uq_users_email_lower" in msg


def test_deleting_a_farm_cascades_to_zones_sensors_and_readings(db: Session, farm: Farm) -> None:
    sensor = Sensor(
        farm_id=farm.id,
        zone_id=farm.zones[0].id,
        name="H",
        sensor_type="humidity",
        unit="%",
        source="simulated",
    )
    db.add(sensor)
    db.flush()
    db.add(SensorReading(sensor_id=sensor.id, recorded_at=NOW, value=60))
    db.flush()

    db.execute(text("DELETE FROM farms WHERE id = :id"), {"id": farm.id})
    for model in (FarmZone, Sensor):
        assert db.scalar(select(func.count()).select_from(model).where(model.farm_id == farm.id)) == 0
    assert db.scalar(select(func.count()).where(SensorReading.sensor_id == sensor.id)) == 0


def test_deleting_a_device_keeps_its_sensors(db: Session, farm: Farm) -> None:
    device = Device(
        farm_id=farm.id,
        name="ESP32-1",
        device_type="esp32",
        source="hardware",
        protocol="mqtt",
        hardware_id="esp32-aa:bb",
    )
    db.add(device)
    db.flush()
    sensor = Sensor(
        farm_id=farm.id,
        device_id=device.id,
        name="DHT22 temp",
        sensor_type="temperature",
        unit="°C",
        source="hardware",
        hardware_model="DHT22",
    )
    db.add(sensor)
    db.flush()

    db.execute(text("DELETE FROM devices WHERE id = :id"), {"id": device.id})
    db.expire_all()
    assert db.get(Sensor, sensor.id) is not None
    assert db.get(Sensor, sensor.id).device_id is None  # type: ignore[union-attr]


def test_crop_in_use_cannot_be_deleted(db: Session, farm: Farm) -> None:
    crop = Crop(common_name="Tomato", scientific_name="Solanum lycopersicum", category="vegetable")
    db.add(crop)
    db.flush()
    db.add(CropCycle(zone_id=farm.zones[0].id, crop_id=crop.id, status="growing"))
    db.flush()
    msg = expect_integrity_error(
        db, lambda: db.execute(text("DELETE FROM crops WHERE id = :id"), {"id": crop.id})
    )
    assert "fk_crop_cycles_crop_id_crops" in msg


def test_updated_at_trigger_fires_on_raw_sql_updates(db: Session, farm: Farm) -> None:
    past = datetime(2020, 1, 1, tzinfo=UTC)
    db.execute(text("UPDATE farms SET updated_at = :p WHERE id = :id"), {"p": past, "id": farm.id})
    # The trigger overrides any explicit value with now(), proving it runs on every UPDATE.
    db.execute(text("UPDATE farms SET name = 'Renamed' WHERE id = :id"), {"id": farm.id})
    updated = db.scalar(text("SELECT updated_at FROM farms WHERE id = :id"), {"id": farm.id})
    assert updated > past


def test_failed_transaction_leaves_no_partial_rows(db: Session, farm: Farm) -> None:
    """A multi-row write that fails part-way must roll back completely (atomicity)."""
    zones_before = db.scalar(select(func.count()).where(FarmZone.farm_id == farm.id))

    def write_zone_then_bad_sensor() -> None:
        zone = FarmZone(farm_id=farm.id, name="Greenhouse 2", zone_type="greenhouse")
        db.add(zone)
        db.flush()  # zone row is written inside the transaction...
        db.add(
            Sensor(
                farm_id=farm.id, zone_id=zone.id, name="x", sensor_type="radar", unit="?", source="simulated"
            )
        )

    expect_integrity_error(db, write_zone_then_bad_sensor)  # ...then the sensor violates a CHECK
    assert db.scalar(select(func.count()).where(FarmZone.farm_id == farm.id)) == zones_before
    assert db.scalar(select(FarmZone).where(FarmZone.name == "Greenhouse 2")) is None


def test_relationships_navigate_user_farm_zone(db: Session, farm: Farm) -> None:
    db.expire_all()
    loaded = db.get(Farm, farm.id)
    assert loaded is not None
    assert loaded.owner.email == "grower@example.com"
    assert [z.name for z in loaded.zones] == ["North Block"]
    assert loaded in loaded.owner.farms
    assert loaded.zones[0].farm is loaded
