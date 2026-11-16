# ruff: noqa: E501  (compact fixtures)
"""Automatic alerts: each rule on a crafted snapshot, then raise / dedupe / escalate / auto-resolve via the API."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain import alert_rules as r
from app.models import WeatherData
from tests.api.helpers import V1, err, ok
from tests.conftest import ClientFor

NOW = datetime(2026, 11, 15, 6, 0, tzinfo=UTC)


def water(status: str, **kw: Any) -> dict[str, Any]:
    return {
        "status": status,
        "depletion_mm": 50,
        "raw_mm": 36.4,
        "moisture_pct": 18,
        "field_capacity_pct": 25,
        **kw,
    }


def snap(**kw: Any) -> r.Snapshot:
    base: dict[str, Any] = {"now": NOW, "zones": [], "sensors": [], "hourly": [], "daily": [], "disease": []}
    return r.Snapshot(**{**base, **kw})


def rules_of(conds: list[r.Condition]) -> dict[str, r.Condition]:
    return {c.rule: c for c in conds}


# --- rules ----------------------------------------------------------------------------
def test_soil_rules() -> None:
    z = lambda status, i=1: {"id": i, "name": f"Z{i}", "water": water(status), "simulated": True}  # noqa: E731
    c = rules_of(
        r.evaluate(
            snap(
                zones=[
                    z("stress"),
                    z("severe", 2),
                    z("above_field_capacity", 3),
                    z("adequate", 4),
                    {"id": 5, "name": "Z5", "water": None},
                ]
            )
        )
    )
    assert set(c) == {"soil_dry", "soil_saturated"}
    conds = r.evaluate(snap(zones=[z("stress"), z("severe", 2)]))
    assert [(x.key, x.severity) for x in conds] == [
        ("soil_dry:zone:1", "warning"),
        ("soil_dry:zone:2", "critical"),
    ]
    assert "simulated sensors" in conds[0].message and conds[0].category == "irrigation"


def test_sensor_rules() -> None:
    sensors = [
        {"id": 1, "name": "probe-1", "zone_id": 1, "last_at": None, "recent_total": 0, "recent_bad": 0},
        {
            "id": 2,
            "name": "probe-2",
            "zone_id": 1,
            "last_at": NOW - timedelta(hours=3),
            "recent_total": 0,
            "recent_bad": 0,
        },
        {"id": 3, "name": "probe-3", "zone_id": 1, "last_at": NOW, "recent_total": 10, "recent_bad": 3},
        {"id": 4, "name": "probe-4", "zone_id": 1, "last_at": NOW, "recent_total": 10, "recent_bad": 1},
        {
            "id": 5,
            "name": "probe-5",
            "zone_id": 1,
            "last_at": NOW,
            "recent_total": 2,
            "recent_bad": 2,
        },  # too few to judge
    ]
    keys = sorted(c.key for c in r.evaluate(snap(sensors=sensors)))
    assert keys == ["sensor_bad_quality:sensor:3", "sensor_silent:sensor:1", "sensor_silent:sensor:2"]


def test_weather_rules_and_thresholds() -> None:
    d0 = NOW.date()
    daily = [{"date": d0, "temp_min_c": 1.5, "temp_max_c": 36, "precipitation_mm": 0},
             {"date": d0 + timedelta(days=1), "temp_min_c": 12, "temp_max_c": 41, "precipitation_mm": 60},
             {"date": d0 + timedelta(days=5), "temp_min_c": -3, "temp_max_c": 50, "precipitation_mm": 300}]  # beyond 48 h: ignored  # fmt: skip
    hourly = [
        {
            "valid_at": NOW + timedelta(hours=h),
            "wind_speed_ms": 14 if h == 10 else 3,
            "temperature_c": 20,
            "precipitation_mm": 0,
        }
        for h in range(72)
    ]
    c = rules_of(r.evaluate(snap(daily=daily, hourly=hourly)))
    assert (c["heat_forecast"].severity, c["heat_forecast"].values["peak_c"]) == ("critical", 41)
    assert (c["frost_forecast"].severity, c["frost_forecast"].values["low_c"]) == ("warning", 1.5)
    assert c["heavy_rain_forecast"].values["max_daily_mm"] == 60 and c["wind_forecast"].values["hours"] == 1
    relaxed = r.evaluate(
        snap(daily=daily, hourly=hourly),
        {"thresholds": {"heat_c": 45, "wind_ms": 20}, "disabled_rules": ["frost_forecast"]},
    )
    assert set(rules_of(relaxed)) == {"heavy_rain_forecast"}


def test_disease_rule_window() -> None:
    dets = [{"id": 7, "zone_id": 1, "label": "Corn: Gray leaf spot", "detected_at": NOW - timedelta(days=1), "model": "vit"},
            {"id": 8, "zone_id": 1, "label": "Old", "detected_at": NOW - timedelta(days=5), "model": "vit"}]  # fmt: skip
    assert [c.key for c in r.evaluate(snap(disease=dets))] == ["disease_suspected:check:7"]


# --- API --------------------------------------------------------------------------------
@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    f = ok(api.post(f"{V1}/farms", json={"name": "Alert Farm", "timezone": "UTC"}), 201)
    z = ok(api.post(f"{V1}/farms/{f['id']}/zones", json={"name": "Field 1", "zone_type": "field"}), 201)
    ok(api.post(f"{V1}/zones/{z['id']}/soil-profiles", json={"texture": "loam"}), 201)
    return {**f, "zone_id": z["id"]}


def moisture(api: TestClient, zone_id: int, pct: float) -> None:
    ok(
        api.post(
            f"{V1}/zones/{zone_id}/soil-measurements",
            json={"measured_at": datetime.now(UTC).isoformat(), "source": "field_kit", "moisture_pct": pct},
        ),
        201,
    )


def evaluate(api: TestClient, farm_id: int) -> dict[str, Any]:
    result: dict[str, Any] = ok(api.post(f"{V1}/farms/{farm_id}/alerts/evaluate"))
    return result


def rule_alerts(api: TestClient, farm_id: int, status: str = "open") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = ok(api.get(f"{V1}/farms/{farm_id}/alerts?status={status}"))["items"]
    return items


def test_raise_dedupe_escalate_acknowledge_and_auto_resolve(api: TestClient, farm: dict[str, Any]) -> None:
    fid, zid = farm["id"], farm["zone_id"]
    manual = ok(
        api.post(
            f"{V1}/farms/{fid}/alerts",
            json={"severity": "info", "category": "system", "title": "Manual note", "message": "x"},
        ),
        201,
    )
    # Loam FC 25 %, WP 12 %; with no crop, Zr 0.6 m, p 0.5: TAW 78, RAW 39. 17 % -> Dr 48 mm: stress.
    moisture(api, zid, 17)
    first = evaluate(api, fid)
    assert first["raised"] == 1 and first["events"][0]["type"] == "raised"
    open_ = [a for a in rule_alerts(api, fid) if a["title"] != "Manual note"]
    assert len(open_) == 1 and open_[0]["severity"] == "warning" and open_[0]["category"] == "irrigation"

    again = evaluate(api, fid)  # still true: no duplicate
    assert (again["raised"], again["updated"], again["resolved"]) == (0, 0, 0)

    ok(api.post(f"{V1}/alerts/{open_[0]['id']}/acknowledge"))
    moisture(api, zid, 12)  # at the wilting point: severe
    esc = evaluate(api, fid)
    assert esc["updated"] == 1 and esc["events"][0]["type"] == "escalated"
    a = ok(api.get(f"{V1}/alerts/{open_[0]['id']}"))
    assert (a["severity"], a["status"]) == ("critical", "acknowledged")  # still acknowledged

    moisture(api, zid, 24)  # watered
    done = evaluate(api, fid)
    assert done["resolved"] == 1 and done["events"][0]["type"] == "resolved"
    a = ok(api.get(f"{V1}/alerts/{open_[0]['id']}"))
    assert a["status"] == "resolved" and a["resolved_at"]
    assert (
        ok(api.get(f"{V1}/alerts/{manual['id']}"))["status"] == "open"
    )  # manual alerts are never auto-resolved

    moisture(api, zid, 17)  # dry again later: a new alert, the old one stays resolved
    assert evaluate(api, fid)["raised"] == 1


def test_silent_sensor_weather_and_settings(api: TestClient, db: Session, farm: dict[str, Any]) -> None:
    fid = farm["id"]
    ok(
        api.post(
            f"{V1}/farms/{fid}/sensors",
            json={
                "name": "New probe",
                "sensor_type": "temperature",
                "source": "hardware",
                "zone_id": farm["zone_id"],
            },
        ),
        201,
    )
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for h in range(48):
        db.add(WeatherData(farm_id=fid, kind="forecast", source="open-meteo", valid_at=start + timedelta(hours=h),
                           temperature_c=38 if 10 <= h % 24 <= 15 else 25, precipitation_mm=0, wind_speed_ms=2))  # fmt: skip
    db.commit()  # flushed-only rows would be lost: each API request rolls back on exit
    rules_now = {c["rule"] for c in evaluate(api, fid)["conditions"]}
    assert {"sensor_silent", "heat_forecast"} <= rules_now

    s = ok(api.get(f"{V1}/farms/{fid}/alert-settings"))
    assert s["thresholds"]["heat_c"] == 35 and all(x["enabled"] for x in s["rules"])
    ok(
        api.put(
            f"{V1}/farms/{fid}/alert-settings",
            json={"disabled_rules": ["sensor_silent"], "thresholds": {"heat_c": 40}},
        )
    )
    after = evaluate(api, fid)
    assert (
        after["resolved"] == 2 and not after["conditions"]
    )  # both alerts close once their rules no longer apply
    err(
        api.put(f"{V1}/farms/{fid}/alert-settings", json={"disabled_rules": ["nope"]}),
        422,
        "validation_error",
    )
    err(
        api.put(f"{V1}/farms/{fid}/alert-settings", json={"thresholds": {"bogus": 1}}),
        422,
        "validation_error",
    )


def test_isolation(client_for: ClientFor, farm: dict[str, Any]) -> None:
    mallory = client_for("mallory@example.com")
    err(mallory.post(f"{V1}/farms/{farm['id']}/alerts/evaluate"), 404, "not_found")
    err(mallory.get(f"{V1}/farms/{farm['id']}/alert-settings"), 404, "not_found")
    err(mallory.put(f"{V1}/farms/{farm['id']}/alert-settings", json={}), 404, "not_found")
