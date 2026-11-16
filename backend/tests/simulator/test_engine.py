"""Simulator against the real database: provisioning, ticks, recorded operations, backfill."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FertilizerApplication, IrrigationEvent, Sensor, SensorReading
from app.simulator.engine import SimulatorEngine
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor

T0 = datetime(2026, 11, 13, 6, 0, tzinfo=UTC)  # 11:30 local time in Hyderabad


@pytest.fixture
def kit(api: TestClient) -> dict[str, Any]:
    farm = ok(
        api.post(f"{V1}/farms", json={"name": "Sim Farm", "latitude": 17.385, "longitude": 78.4867}), 201
    )
    zone = make_zone(api, farm["id"], "North Field")
    result = ok(api.post(f"{V1}/zones/{zone['id']}/simulator/provision", json={}), 201)
    return {"farm": farm, "zone": zone, **result}


def readings_by_type(db: Session, sensors: list[dict[str, Any]], when: datetime) -> dict[str, float]:
    out = {}
    for s in sensors:
        r = db.scalar(
            select(SensorReading).where(SensorReading.sensor_id == s["id"], SensorReading.recorded_at == when)
        )
        if r is not None:
            out[s["sensor_type"]] = r.value
    return out


def test_provision_creates_a_labelled_simulated_kit(kit: dict[str, Any]) -> None:
    assert kit["device"]["device_type"] == "simulator"
    assert kit["device"]["source"] == "simulated"
    assert len(kit["sensors"]) == 12
    assert all(s["is_simulated"] and s["source"] == "simulated" for s in kit["sensors"])
    assert all(s["twin_position"] is not None for s in kit["sensors"])


def test_provision_rules(api: TestClient, client_for: ClientFor, kit: dict[str, Any]) -> None:
    # Second kit in the same zone is refused.
    err(api.post(f"{V1}/zones/{kit['zone']['id']}/simulator/provision", json={}), 409, "conflict")
    # A farm without coordinates cannot be simulated realistically.
    farm = ok(api.post(f"{V1}/farms", json={"name": "No location"}), 201)
    zone = make_zone(api, farm["id"])
    body = err(api.post(f"{V1}/zones/{zone['id']}/simulator/provision", json={}), 422, "invalid")
    assert "latitude" in body["message"]
    # Subset of sensor types.
    zone2 = make_zone(api, kit["farm"]["id"], "Greenhouse")
    subset = ok(
        api.post(
            f"{V1}/zones/{zone2['id']}/simulator/provision",
            json={"sensor_types": ["temperature", "humidity"]},
        ),
        201,
    )
    assert [s["sensor_type"] for s in subset["sensors"]] == ["temperature", "humidity"]
    # Another user's zone.
    err(
        client_for("mallory@example.com").post(f"{V1}/zones/{zone2['id']}/simulator/provision", json={}),
        404,
        "not_found",
    )


def test_tick_writes_one_plausible_reading_per_active_simulated_sensor(
    api: TestClient, db: Session, kit: dict[str, Any]
) -> None:
    hw = ok(
        api.post(
            f"{V1}/farms/{kit['farm']['id']}/sensors",
            json={"name": "Real DHT22", "sensor_type": "temperature", "source": "hardware"},
        ),
        201,
    )
    paused = next(s for s in kit["sensors"] if s["sensor_type"] == "water_level")
    ok(api.patch(f"{V1}/sensors/{paused['id']}", json={"status": "inactive"}))

    engine = SimulatorEngine(seed=1, fault_rate=0)
    stored = engine.tick(db, T0)
    db.flush()
    assert len(stored) == 11  # 12 simulated minus the inactive one; never the hardware sensor
    assert all(r.is_simulated for r in stored)
    assert {r.sensor_id for r in stored}.isdisjoint({hw["id"], paused["id"]})
    assert all(r.quality == "good" for r in stored)

    values = readings_by_type(db, kit["sensors"], T0)
    assert 10 < values["temperature"] < 40
    assert 0 <= values["humidity"] <= 100
    assert values["light"] > 20_000  # late morning
    assert 5 < values["soil_moisture"] < 45
    assert db.scalar(select(Sensor.last_reading_at).where(Sensor.id == kit["sensors"][1]["id"])) == T0

    assert engine.tick(db, T0) == []  # same instant again: nothing new


def test_recorded_irrigation_and_fertilizer_change_the_simulated_soil(
    db: Session, kit: dict[str, Any]
) -> None:
    engine = SimulatorEngine(seed=2, fault_rate=0)
    engine.tick(db, T0)
    t1 = T0 + timedelta(hours=1)
    zone_id = kit["zone"]["id"]
    db.add(IrrigationEvent(zone_id=zone_id, method="drip", status="completed", volume_liters=200_000,
                           started_at=T0 + timedelta(minutes=5)))  # fmt: skip  # 20 mm on 1 ha
    db.add(
        FertilizerApplication(
            zone_id=zone_id,
            applied_at=T0 + timedelta(minutes=10),
            product_name="Urea",
            method="broadcast",
            quantity_kg=500,
            n_pct=46,
        )
    )
    db.flush()
    engine.tick(db, t1)
    before, after = readings_by_type(db, kit["sensors"], T0), readings_by_type(db, kit["sensors"], t1)
    assert after["soil_moisture"] - before["soil_moisture"] > 4  # +6.7 % minus an hour of ET
    assert after["nitrogen"] - before["nitrogen"] > 20  # ~ +35 mg/kg
    assert after["water_level"] < before["water_level"]  # drawn from the tank


def test_backfill_is_bounded_and_idempotent(api: TestClient, db: Session, kit: dict[str, Any]) -> None:
    url = f"{V1}/farms/{kit['farm']['id']}/simulator/backfill"
    first = ok(api.post(url, json={"hours": 2, "step_minutes": 10}))
    assert first["sensors"] == 12
    assert first["inserted"] == 12 * 13  # 2 h at 10 min, inclusive
    assert ok(api.post(url, json={"hours": 2, "step_minutes": 10}))["inserted"] == 0
    series = ok(api.get(f"{V1}/sensors/{kit['sensors'][0]['id']}/readings", params={"limit": 50}))
    assert series["count"] == 13 and series["is_simulated"] is True
    err(api.post(url, json={"hours": 500}), 422, "validation_error")
    err(api.post(url, json={"step_minutes": 1}), 422, "validation_error")
    total = db.scalar(select(func.count()).select_from(SensorReading))
    assert total is not None and total >= 156


def test_simulator_status_endpoint(api: TestClient, kit: dict[str, Any]) -> None:
    status = ok(api.get(f"{V1}/farms/{kit['farm']['id']}/simulator"))
    assert status["simulated_sensors"] == 12
    assert status["enabled"] is False  # the background runner is off in tests
    assert "simulator" in status["note"]
