from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from tests.api.helpers import V1, err, make_farm, make_zone, ok


def make_sensor(api: TestClient, farm_id: int, **overrides: Any) -> dict[str, Any]:
    body = {"name": "Soil moisture A", "sensor_type": "soil_moisture", "source": "simulated", **overrides}
    sensor: dict[str, Any] = ok(api.post(f"{V1}/farms/{farm_id}/sensors", json=body), 201)
    return sensor


def iso(dt: datetime) -> str:
    return dt.isoformat()


def test_device_source_is_derived_from_device_type(api: TestClient) -> None:
    farm = make_farm(api)
    sim = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/devices",
            json={"name": "Sim", "device_type": "simulator", "protocol": "simulator"},
        ),
        201,
    )
    esp = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/devices",
            json={"name": "ESP32", "device_type": "esp32", "protocol": "mqtt"},
        ),
        201,
    )
    assert sim["source"] == "simulated"
    assert esp["source"] == "hardware"
    # Clients cannot claim a source directly.
    err(
        api.post(
            f"{V1}/farms/{farm['id']}/devices",
            json={"name": "x", "device_type": "esp32", "protocol": "http", "source": "simulated"},
        ),
        422,
        "validation_error",
    )


def test_sensor_defaults_and_simulated_label(api: TestClient) -> None:
    farm = make_farm(api)
    sensor = make_sensor(api, farm["id"])
    assert sensor["unit"] == "%"
    assert (sensor["min_valid"], sensor["max_valid"]) == (0, 100)
    assert sensor["is_simulated"] is True
    types = ok(api.get(f"{V1}/sensor-types"))
    assert len(types) == 12
    assert {t["sensor_type"] for t in types} >= {"soil_ph", "nitrogen", "leaf_wetness", "water_level"}


def test_sensor_cannot_mix_sources_or_farms(api: TestClient) -> None:
    farm = make_farm(api)
    other = make_farm(api, "Other")
    sim = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/devices",
            json={"name": "Sim", "device_type": "simulator", "protocol": "simulator"},
        ),
        201,
    )
    body = err(
        api.post(
            f"{V1}/farms/{farm['id']}/sensors",
            json={"name": "x", "sensor_type": "temperature", "source": "hardware", "device_id": sim["id"]},
        ),
        422,
        "invalid",
    )
    assert body["details"] == {"field": "source"}
    foreign_zone = make_zone(api, other["id"])
    err(
        api.post(
            f"{V1}/farms/{farm['id']}/sensors",
            json={
                "name": "x",
                "sensor_type": "humidity",
                "source": "simulated",
                "zone_id": foreign_zone["id"],
            },
        ),
        422,
        "invalid",
    )


def test_reading_ingest_is_idempotent_and_flags_out_of_range(api: TestClient) -> None:
    farm = make_farm(api)
    sensor = make_sensor(api, farm["id"])
    t0 = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    batch = [{"recorded_at": iso(t0 + timedelta(minutes=i)), "value": 30 + i} for i in range(5)]
    batch.append({"recorded_at": iso(t0 + timedelta(minutes=10)), "value": 140})  # > max_valid 100

    first = ok(api.post(f"{V1}/sensors/{sensor['id']}/readings", json={"readings": batch}))
    assert first == {"received": 6, "inserted": 6, "duplicates": 0, "suspect": 1}
    again = ok(api.post(f"{V1}/sensors/{sensor['id']}/readings", json={"readings": batch[:3]}))
    assert again == {"received": 3, "inserted": 0, "duplicates": 3, "suspect": 0}

    latest = ok(api.get(f"{V1}/sensors/{sensor['id']}/readings/latest"))
    assert latest["value"] == 140
    assert latest["quality"] == "suspect"
    refreshed = ok(api.get(f"{V1}/sensors/{sensor['id']}"))
    assert refreshed["last_reading_at"] is not None


def test_reading_ingest_rejects_bad_input(api: TestClient) -> None:
    farm = make_farm(api)
    sensor = make_sensor(api, farm["id"])
    url = f"{V1}/sensors/{sensor['id']}/readings"
    future = datetime.now(UTC) + timedelta(hours=1)
    err(api.post(url, json={"readings": [{"recorded_at": iso(future), "value": 1}]}), 422, "invalid")
    err(
        api.post(url, json={"readings": [{"recorded_at": "2026-11-13T08:00:00", "value": 1}]}),
        422,
        "validation_error",
    )
    err(api.post(url, json={"readings": []}), 422, "validation_error")
    too_many = [
        {"recorded_at": iso(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=i)), "value": 1}
        for i in range(1001)
    ]
    err(api.post(url, json={"readings": too_many}), 422, "validation_error")
    err(
        api.post(url, json={"readings": [{"recorded_at": iso(datetime.now(UTC)), "value": "NaN"}]}),
        422,
        "validation_error",
    )


def test_reading_queries_window_order_and_limit(api: TestClient) -> None:
    farm = make_farm(api)
    sensor = make_sensor(api, farm["id"], sensor_type="temperature", name="Air temp")
    base = datetime(2026, 11, 1, tzinfo=UTC)
    rows = [{"recorded_at": iso(base + timedelta(minutes=10 * i)), "value": float(i)} for i in range(20)]
    ok(api.post(f"{V1}/sensors/{sensor['id']}/readings", json={"readings": rows}))

    params = {"start": iso(base), "end": iso(base + timedelta(hours=10)), "limit": 5}
    series = ok(api.get(f"{V1}/sensors/{sensor['id']}/readings", params=params))
    assert series["count"] == 5
    assert series["is_simulated"] is True
    assert series["unit"] == "°C"
    # The most recent 5, in chronological order.
    assert [r["value"] for r in series["readings"]] == [15.0, 16.0, 17.0, 18.0, 19.0]

    err(
        api.get(f"{V1}/sensors/{sensor['id']}/readings", params={"start": iso(base), "end": iso(base)}),
        422,
        "invalid",
    )
    err(
        api.get(
            f"{V1}/sensors/{sensor['id']}/readings",
            params={"start": iso(base), "end": iso(base + timedelta(days=200))},
        ),
        422,
        "invalid",
    )


def test_latest_reading_404_when_empty_and_delete_device_keeps_sensor(api: TestClient) -> None:
    farm = make_farm(api)
    esp = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/devices",
            json={"name": "ESP32", "device_type": "esp32", "protocol": "http"},
        ),
        201,
    )
    sensor = make_sensor(
        api,
        farm["id"],
        source="hardware",
        device_id=esp["id"],
        hardware_model="DHT22",
        sensor_type="humidity",
        name="RH",
    )
    assert sensor["is_simulated"] is False
    err(api.get(f"{V1}/sensors/{sensor['id']}/readings/latest"), 404, "not_found")

    ok(api.delete(f"{V1}/devices/{esp['id']}"), 204)
    assert ok(api.get(f"{V1}/sensors/{sensor['id']}"))["device_id"] is None


def test_sensor_filters(api: TestClient) -> None:
    farm = make_farm(api)
    zone = make_zone(api, farm["id"])
    make_sensor(api, farm["id"], zone_id=zone["id"])
    make_sensor(api, farm["id"], sensor_type="light", name="Lux")
    page = ok(api.get(f"{V1}/farms/{farm['id']}/sensors", params={"zone_id": zone["id"]}))
    assert page["total"] == 1
    page = ok(api.get(f"{V1}/farms/{farm['id']}/sensors", params={"sensor_type": "light"}))
    assert [s["unit"] for s in page["items"]] == ["lux"]
