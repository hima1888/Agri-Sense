# ruff: noqa: E501  (compact test fixtures)
"""Explainable recommendations: each rule on controlled inputs, then the API on real stored data."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain import recommend_rules as r
from app.models import WeatherData
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor

NOW = datetime(2026, 11, 14, 6, 0, tzinfo=UTC)


def water(
    status: str, depletion: float = 40, days: int | None = None, moisture_src: str = "lab test (3 days old)"
) -> dict[str, Any]:
    return {"status": status, "moisture_pct": 19.3, "field_capacity_pct": 25, "depletion_mm": depletion, "raw_mm": 36.4,
            "days_to_stress": days, "confidence": 0.8,
            "sources": {"moisture": moisture_src, "soil_water_limits": "measured soil profile"}}  # fmt: skip


def zone(soil: dict[str, Any], **kw: Any) -> r.ZoneContext:
    base = {
        "zone_id": 1,
        "zone_name": "North Field",
        "area_ha": 0.5,
        "irrigation_method": "drip",
        "soil": soil,
    }
    return r.ZoneContext(**{**base, **kw})


def ctx(
    zones: list[r.ZoneContext],
    hourly: list[dict[str, Any]] | None = None,
    daily: list[dict[str, Any]] | None = None,
) -> r.FarmContext:
    return r.FarmContext(2, NOW, hourly or [], daily or [], NOW, zones)


def hours(n: int = 72, **vals: Any) -> list[dict[str, Any]]:
    row = {"temperature_c": 22.0, "relative_humidity_pct": 60.0, "precipitation_mm": 0.0,
           "precipitation_probability_pct": 0.0, "wind_speed_ms": 2.0}  # fmt: skip
    return [
        {**row, **vals, "valid_at": NOW + timedelta(hours=i), "local_hour": (11 + i) % 24} for i in range(n)
    ]


def only(recs: list[dict[str, Any]], rule: str) -> dict[str, Any]:
    found = [x for x in recs if x["rule"] == rule]
    assert len(found) == 1, [x["rule"] for x in recs]
    return found[0]


# --- irrigation -------------------------------------------------------------------
def test_irrigate_now_with_volume_from_area_and_drip_efficiency() -> None:
    rec = only(r.generate(ctx([zone({"water": water("stress", 40)})], hours())), "irrigate_now")
    assert rec["priority"] == "high" and rec["category"] == "irrigation"
    # net 40 mm / 0.9 drip efficiency = 44.4 mm gross; x 5000 m2 = 222,000 L
    assert rec["action"] == {**rec["action"], "net_mm": 40, "gross_mm": 44.4, "volume_liters": 222000}
    assert rec["confidence"] == round(0.8 * r.RULE_CERTAINTY["irrigate_now"], 2)
    assert "0.80 x rule certainty 0.95" in rec["confidence_basis"]
    assert {f["name"] for f in rec["factors"]} >= {
        "Soil moisture",
        "Root-zone depletion",
        "Forecast rain, next 48 h",
    }


def test_severe_is_critical_and_no_area_means_no_volume() -> None:
    rec = only(r.generate(ctx([zone({"water": water("severe", 80)}, area_ha=None)], hours())), "irrigate_now")
    assert rec["priority"] == "critical" and rec["action"]["volume_liters"] is None
    assert any("Zone area unknown" in lim for lim in rec["limitations"])


def test_forecast_rain_holds_irrigation() -> None:
    wet = hours(precipitation_mm=1.5)  # 72 mm in 48 h
    rec = only(r.generate(ctx([zone({"water": water("stress", 40)})], wet)), "hold_irrigation_rain")
    assert (
        rec["action"]["type"] == "hold_irrigation" and rec["expected_impact"]["water_saved_liters"] == 222000
    )


def test_soon_wet_and_fine() -> None:
    assert only(r.generate(ctx([zone({"water": water("adequate", 30, days=2)})], hours())), "irrigation_soon")
    assert only(
        r.generate(ctx([zone({"water": water("above_field_capacity", 0)})], hours())), "skip_irrigation_wet"
    )
    assert r.water_rules(ctx([], hours()), zone({"water": water("adequate", 10, days=6)})) == []


def test_simulated_inputs_are_flagged() -> None:
    rec = only(
        r.generate(ctx([zone({"water": water("stress", moisture_src="sensors (simulated)")})], hours())),
        "irrigate_now",
    )
    assert rec["uses_simulated_data"] and "simulated" in rec["limitations"][0]


def test_no_forecast_lowers_confidence() -> None:
    rec = only(r.generate(ctx([zone({"water": water("stress")})])), "irrigate_now")
    assert rec["confidence"] == round(0.8 * 0.85 * 0.95, 2)


# --- soil -------------------------------------------------------------------------
def comp(value: float, status: str, source: str, target: list[float], unit: str = "kg/ha") -> dict[str, Any]:
    return {"value": value, "unit": unit, "status": status, "source": source, "target": target,
            "target_source": "Soil Health Card rating limits", "confidence": 0.9}  # fmt: skip


def test_soil_rules_from_lab_vs_sensor() -> None:
    soil = {"crop": {"name": "Tomato"}, "inputs": {"lab_test_age_days": 20},
            "components": {"nitrogen": comp(224, "low", "lab test (20 days old)", [280, 560]),
                           "potassium": comp(90, "low", "NPK probe 24 h mean (simulated)", [110, 280]),
                           "organic_carbon": comp(0.42, "low", "lab test (20 days old)", [0.5, 0.75], "%"),
                           "ph": {**comp(5.4, "acidic", "lab test (20 days old)", [6.0, 6.8], ""), "target_source": "Tomato optimum"},
                           "salinity": comp(2.5, "slightly saline", "lab test (20 days old)", [0, 1], "dS/m")}}  # fmt: skip
    recs = r.generate(ctx([zone(soil)], hours()))
    n = [x for x in recs if x["rule"].startswith("nutrient_low:")]
    assert sorted(x["rule"] for x in n) == [
        "nutrient_low:nitrogen",
        "nutrient_low:potassium",
    ]  # distinct keys
    lab_n = next(x for x in n if x["action"]["nutrient"] == "nitrogen")
    probe_k = next(x for x in n if x["action"]["nutrient"] == "potassium")
    assert lab_n["priority"] == "medium" and "Soil Health Card" in lab_n["action"]["next_step"]
    assert (
        probe_k["priority"] == "low"
        and "lab" in probe_k["action"]["next_step"]
        and probe_k["uses_simulated_data"]
    )
    assert all("Phase 13" in " ".join(x["limitations"]) for x in n)  # no invented doses
    om = only(recs, "organic_matter_low")
    assert (
        om["category"] == "soil"
        and "compost" in om["action"]["next_step"]
        and "dose" not in om["action"]["next_step"]
    )
    ph = only(recs, "ph_out_of_range")
    assert ph["action"]["direction"] == "raise" and "lime" in ph["rationale"]
    assert only(recs, "salinity")["priority"] == "medium"
    assert not [x for x in recs if x["rule"] == "soil_test_needed"]


def test_missing_lab_test_asks_for_one() -> None:
    rec = only(
        r.generate(ctx([zone({"components": {}, "inputs": {"lab_test_age_days": None}})])), "soil_test_needed"
    )
    assert rec["confidence"] == 1.0 and rec["priority"] == "low"


# --- health, weather, sensors ----------------------------------------------------
def test_disease_follow_up_scouts_and_never_prescribes() -> None:
    d = {
        "id": 9,
        "label": "Corn: Gray leaf spot",
        "confidence": 0.72,
        "detected_at": NOW,
        "model": "crop-leaf-diseases-vit",
    }
    rec = only(
        r.generate(ctx([zone({"crop": {"name": "Maize"}}, recent_disease=[d])], hours())),
        "confirm_suspected_disease",
    )
    assert rec["action"]["type"] == "scout" and rec["action"]["spray_windows"]
    assert "confirm" in rec["rationale"] and "pesticide" not in rec["category"]


def test_spray_windows_respect_wind_rain_and_daylight() -> None:
    h = hours(48)
    for row in h[:6]:
        row["wind_speed_ms"] = 6  # too windy
    h[20]["precipitation_probability_pct"] = 80  # rain at hour 20 blocks hours 15 to 20
    win = r.spray_windows(ctx([], h))
    allowed = {x["valid_at"].isoformat() for x in h if 6 <= x["local_hour"] <= 18}
    assert win and set(win) <= allowed
    assert h[0]["valid_at"].isoformat() not in win and h[15]["valid_at"].isoformat() not in win


def test_humid_spell_heat_and_silent_sensors() -> None:
    z = zone(
        {"crop": {"name": "Tomato"}}, silent_sensors=[{"id": 4, "name": "Soil probe A", "last_at": None}]
    )
    daily = [{"date": NOW.date(), "temp_max_c": 37.2}]
    recs = r.generate(ctx([z], hours(relative_humidity_pct=95.0), daily))
    assert "not a validated disease-risk model" in " ".join(
        only(recs, "humid_weather_scouting")["limitations"]
    )
    assert only(recs, "heat_stress")["factors"][0]["value"] == 37.2
    assert only(recs, "sensors_silent")["action"]["sensor_ids"] == [4]


def test_sorted_by_priority_then_confidence() -> None:
    recs = r.generate(
        ctx(
            [zone({"water": water("severe", 80), "components": {}, "inputs": {"lab_test_age_days": None}})],
            hours(),
        )
    )
    order = [r.PRIORITY_ORDER[x["priority"]] for x in recs]
    assert order == sorted(order) and recs[0]["priority"] == "critical"


# --- API on real stored data ---------------------------------------------------------
@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    body = {"name": "Advice Farm", "latitude": 17.385, "longitude": 78.4867, "timezone": "Asia/Kolkata"}
    f: dict[str, Any] = ok(api.post(f"{V1}/farms", json=body), 201)
    return f


def lab_test(api: TestClient, zone_id: int, **values: Any) -> None:
    body = {"measured_at": (datetime.now(UTC) - timedelta(days=5)).isoformat(), "source": "lab", **values}
    ok(api.post(f"{V1}/zones/{zone_id}/soil-measurements", json=body), 201)


def test_generate_store_dedupe_expire_and_respond(api: TestClient, db: Session, farm: dict[str, Any]) -> None:
    zone_ = make_zone(api, farm["id"], "Dry Field")
    ok(api.post(f"{V1}/zones/{zone_['id']}/soil-profiles", json={"texture": "loam"}), 201)
    lab_test(api, zone_["id"], moisture_pct=15, ph=6.5, nitrogen_mg_kg=200)  # loam: 15 % is past RAW
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for h in range(72):
        db.add(WeatherData(farm_id=farm["id"], kind="forecast", source="open-meteo", valid_at=start + timedelta(hours=h),
                           et0_mm=0.2, precipitation_mm=0, temperature_c=24, relative_humidity_pct=55, wind_speed_ms=2))  # fmt: skip
    db.flush()

    preview = ok(api.get(f"{V1}/farms/{farm['id']}/recommendations/preview"))
    assert preview["forecast_hours"] >= 70 and preview["uses_simulated_data"] is False
    irrigate = next(x for x in preview["recommendations"] if x["rule"] == "irrigate_now")
    assert irrigate["factors"][0]["source"].startswith("lab") and irrigate["id"] is None
    assert ok(api.get(f"{V1}/farms/{farm['id']}/recommendations"))["total"] == 0  # preview stores nothing

    first = ok(api.post(f"{V1}/farms/{farm['id']}/recommendations/generate"))
    assert first["stored"]["created"] >= 1 and first["stored"]["refreshed"] == 0
    again = ok(api.post(f"{V1}/farms/{farm['id']}/recommendations/generate"))
    assert again["stored"] == {"created": 0, "refreshed": first["stored"]["created"], "expired": 0}

    stored = ok(api.get(f"{V1}/farms/{farm['id']}/recommendations?status=pending"))["items"]
    rec = next(x for x in stored if x["rule"] == "irrigate_now")
    assert rec["factors"] and rec["limitations"] and rec["action"]["type"] == "irrigate"
    accepted = ok(api.post(f"{V1}/recommendations/{rec['id']}/respond", json={"status": "accepted"}))
    assert accepted["status"] == "accepted" and accepted["responded_at"]
    assert (
        ok(api.post(f"{V1}/recommendations/{rec['id']}/respond", json={"status": "applied"}))["status"]
        == "applied"
    )
    err(api.post(f"{V1}/recommendations/{rec['id']}/respond", json={"status": "rejected"}), 409, "conflict")
    err(
        api.post(f"{V1}/recommendations/{rec['id']}/respond", json={"status": "expired"}),
        422,
        "validation_error",
    )

    # Soil is wet now: the old irrigation advice no longer applies and pending irrigation advice expires.
    lab_test(api, zone_["id"], moisture_pct=27)
    third = ok(api.post(f"{V1}/farms/{farm['id']}/recommendations/generate"))
    assert any(x["rule"] == "skip_irrigation_wet" for x in third["recommendations"])
    assert (
        ok(api.get(f"{V1}/farms/{farm['id']}/recommendations?status=applied"))["total"] == 1
    )  # history kept


def test_recommendations_are_owner_only(client_for: ClientFor, api: TestClient, farm: dict[str, Any]) -> None:
    mallory = client_for("mallory@example.com")
    err(mallory.get(f"{V1}/farms/{farm['id']}/recommendations/preview"), 404, "not_found")
    err(mallory.post(f"{V1}/farms/{farm['id']}/recommendations/generate"), 404, "not_found")
    zone_ = make_zone(api, farm["id"])
    ok(api.post(f"{V1}/farms/{farm['id']}/recommendations/generate"))
    rec_id = ok(api.get(f"{V1}/farms/{farm['id']}/recommendations"))["items"][0]["id"]
    assert zone_
    err(mallory.post(f"{V1}/recommendations/{rec_id}/respond", json={"status": "accepted"}), 404, "not_found")


def test_growth_stage_is_an_input_and_raises_priority_at_flowering() -> None:
    soil = {"water": water("adequate", 30, days=2)}
    veg = only(
        r.generate(ctx([zone(soil, stage={"key": "vegetative", "name": "Vegetative", "day": 40})], hours())),
        "irrigation_soon",
    )
    flw = only(
        r.generate(ctx([zone(soil, stage={"key": "flowering", "name": "Flowering", "day": 70})], hours())),
        "irrigation_soon",
    )
    assert veg["priority"] == "medium" and flw["priority"] == "high"
    assert "FAO-33" in flw["rationale"] and "FAO-33" not in veg["rationale"]
    assert any(f["name"] == "Growth stage" and f["value"] == "Flowering (day 70)" for f in flw["factors"])
