"""Soil intelligence: FAO-56 water balance, Soil Health Card ratings, and the API."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.soil_reference import (
    CROP_WATER,
    MG_KG_TO_KG_HA,
    NPK_LIMITS_KG_HA,
    crop_water,
    kc_for_growth,
    rate,
)
from app.models import WeatherData
from app.services.soil import water_balance
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor

TOMATO = CROP_WATER["tomato"]


# --- reference maths ------------------------------------------------------------
def test_kc_follows_the_fao56_stage_curve() -> None:
    assert kc_for_growth(TOMATO, 0.1) == TOMATO.kc_ini
    assert kc_for_growth(TOMATO, 0.325) == pytest.approx((TOMATO.kc_ini + TOMATO.kc_mid) / 2)
    assert kc_for_growth(TOMATO, 0.6) == TOMATO.kc_mid
    assert kc_for_growth(TOMATO, 1.0) == pytest.approx(TOMATO.kc_end)
    assert kc_for_growth(TOMATO, None) == TOMATO.kc_mid


def test_crop_parameters_fall_back_from_crop_to_category_to_default() -> None:
    assert crop_water("Tomato", "vegetable")[1] == "crop"
    assert crop_water("Okra", "vegetable")[1] == "category"
    assert crop_water(None, None)[1] == "default"


def test_water_balance_matches_hand_calculation() -> None:
    # Loam: FC 25 %, WP 12 %; tomato Zr 0.7 m, p 0.40.
    # TAW = 0.13 * 700 = 91 mm; RAW = 36.4 mm; theta 20 % -> Dr = 0.05 * 700 = 35 mm.
    forecast = [{"date": date(2026, 11, 14 + i), "et0_mm": 5.0, "precipitation_mm": 0.0} for i in range(3)]
    w = water_balance(25, 12, 20, 0.7, 0.40, 1.15, forecast)
    assert (w["taw_mm"], w["raw_mm"], w["depletion_mm"]) == (91.0, 36.4, 35.0)
    assert w["status"] == "adequate"
    assert w["days_to_stress"] == 1  # 35 + 1.15 * 5 = 40.75 > 36.4
    assert w["projection"][0]["depletion_mm"] == pytest.approx(40.8, abs=0.06)
    assert w["available_fraction"] == pytest.approx(1 - 35 / 91, abs=0.001)


def test_rain_delays_stress_but_light_showers_do_not_count() -> None:
    wet = [{"date": date(2026, 11, 14), "et0_mm": 5.0, "precipitation_mm": 20.0}] + [
        {"date": date(2026, 11, 15 + i), "et0_mm": 5.0, "precipitation_mm": 0.0} for i in range(4)
    ]
    assert water_balance(25, 12, 20, 0.7, 0.40, 1.15, wet)["days_to_stress"] == 4
    drizzle = [{"date": date(2026, 11, 14), "et0_mm": 5.0, "precipitation_mm": 1.5}]
    assert water_balance(25, 12, 20, 0.7, 0.40, 1.15, drizzle)["projection"][0]["effective_rain_mm"] == 0


@pytest.mark.parametrize(
    ("theta", "status"), [(27, "above_field_capacity"), (21, "adequate"), (17, "stress"), (12, "severe")]
)
def test_water_status_thresholds(theta: float, status: str) -> None:
    assert water_balance(25, 12, theta, 0.7, 0.40, 1.15, [])["status"] == status


def test_soil_health_card_conversion_and_ratings() -> None:
    assert pytest.approx(313.6) == 140 * MG_KG_TO_KG_HA
    lo, hi = NPK_LIMITS_KG_HA["nitrogen"]
    assert (rate(250, lo, hi), rate(313.6, lo, hi), rate(600, lo, hi)) == ("low", "medium", "high")


# --- API ------------------------------------------------------------------------
@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    body = {"name": "Soil Farm", "latitude": 17.385, "longitude": 78.4867, "timezone": "Asia/Kolkata"}
    f: dict[str, Any] = ok(api.post(f"{V1}/farms", json=body), 201)
    return f


def plant(api: TestClient, admin: TestClient, zone_id: int, days_ago: int = 50) -> None:
    crop = ok(
        admin.post(
            f"{V1}/crops",
            json={
                "common_name": "Tomato",
                "category": "vegetable",
                "typical_cycle_days": 110,
                "optimal_ph_min": 6.0,
                "optimal_ph_max": 6.8,
            },
        ),
        201,
    )
    planted = (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()
    ok(
        api.post(
            f"{V1}/zones/{zone_id}/crop-cycles",
            json={"crop_id": crop["id"], "status": "growing", "planted_on": planted},
        ),
        201,
    )


def lab_test(api: TestClient, zone_id: int, **values: Any) -> None:
    body = {"measured_at": (datetime.now(UTC) - timedelta(days=20)).isoformat(), "source": "lab", **values}
    ok(api.post(f"{V1}/zones/{zone_id}/soil-measurements", json=body), 201)


def test_lab_backed_assessment(api: TestClient, admin: TestClient, farm: dict[str, Any]) -> None:
    zone = make_zone(api, farm["id"])
    plant(api, admin, zone["id"])
    ok(
        api.post(
            f"{V1}/zones/{zone['id']}/soil-profiles",
            json={"texture": "loam", "field_capacity_pct": 26, "wilting_point_pct": 12},
        ),
        201,
    )
    lab_test(
        api,
        zone["id"],
        ph=5.4,
        nitrogen_mg_kg=100,
        phosphorus_mg_kg=8,
        potassium_mg_kg=90,
        organic_carbon_pct=0.42,
        electrical_conductivity_ds_m=0.6,
        moisture_pct=19,
    )

    a = ok(api.get(f"{V1}/zones/{zone['id']}/soil"))
    c = a["components"]
    assert c["ph"]["status"] == "acidic" and c["ph"]["target"] == [6.0, 6.8]
    assert c["ph"]["target_source"] == "Tomato optimum" and c["ph"]["source"].startswith("lab test")
    assert (
        c["nitrogen"]["value"] == pytest.approx(224.0) and c["nitrogen"]["status"] == "low"
    )  # 100 mg/kg * 2.24
    assert c["phosphorus"]["status"] == "medium" and c["potassium"]["status"] == "medium"
    assert c["organic_carbon"]["status"] == "low" and c["salinity"]["status"] == "normal"
    assert a["not_assessed"] == []
    assert a["water"]["sources"]["soil_water_limits"] == "measured soil profile"
    assert a["water"]["sources"]["crop_parameters"] == "FAO-56 values for Tomato"
    assert a["uses_simulated_data"] is False
    assert a["confidence"] > 0.75
    assert 0 < a["index"] < 75 and a["rating"] in ("fair", "poor")
    impacts = [f["impact"] for f in a["factors"]]
    assert impacts == sorted(impacts, reverse=True) and a["factors"][0]["key"] in (
        "ph",
        "nitrogen",
        "organic_carbon",
    )
    text = " ".join(g["text"] for g in a["guidance"])
    assert "pH 5.4 is below the Tomato optimum" in text and "rated low" in text
    assert any("not a trained model" in lim for lim in a["limitations"])


def test_simulated_sensor_assessment_is_labelled_and_low_confidence(
    api: TestClient, farm: dict[str, Any]
) -> None:
    zone = make_zone(api, farm["id"])
    ok(api.post(f"{V1}/zones/{zone['id']}/simulator/provision", json={}), 201)
    ok(api.post(f"{V1}/farms/{farm['id']}/simulator/backfill", json={"hours": 6, "step_minutes": 10}))
    a = ok(api.get(f"{V1}/zones/{zone['id']}/soil"))
    assert a["uses_simulated_data"] is True
    assert a["components"]["nitrogen"]["source"] == "NPK probe 24 h mean (simulated)"
    assert a["water"]["sources"]["moisture"] == "soil-moisture sensors (latest) (simulated)"
    assert a["water"]["sources"]["soil_water_limits"].startswith("assumed loam")
    assert set(a["not_assessed"]) == {"organic_carbon", "salinity"}
    assert a["confidence"] < 0.5
    assert "uses simulated sensor data" in a["confidence_reasons"]
    assert any("simulated" in lim for lim in a["limitations"])
    assert any("NPK probes" in lim for lim in a["limitations"])


def test_texture_only_profile_and_forecast_projection(
    api: TestClient, admin: TestClient, db: Session, farm: dict[str, Any]
) -> None:
    zone = make_zone(api, farm["id"])
    plant(api, admin, zone["id"], days_ago=70)  # mid-season
    ok(api.post(f"{V1}/zones/{zone['id']}/soil-profiles", json={"texture": "sandy_loam"}), 201)
    lab_test(api, zone["id"], moisture_pct=18)
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=12)
    for h in range(24 * 5):  # 5 days of hourly forecast, ET0 0.25 mm/h = 6 mm/day
        db.add(
            WeatherData(
                farm_id=farm["id"],
                kind="forecast",
                source="open-meteo",
                valid_at=start + timedelta(hours=h),
                et0_mm=0.25,
                precipitation_mm=0,
            )
        )
    db.flush()
    w = ok(api.get(f"{V1}/zones/{zone['id']}/soil"))["water"]
    assert w["sources"]["soil_water_limits"] == "estimated from texture (sandy loam, FAO-56)"
    assert (w["field_capacity_pct"], w["wilting_point_pct"]) == (23.0, 11.0)
    assert w["kc"] == TOMATO.kc_mid
    # Day 0 may be a partial local day; day 1 is a full 24 h of forecast.
    assert w["forecast_days"] >= 3 and w["projection"][1]["etc_mm"] == pytest.approx(
        6 * TOMATO.kc_mid, abs=0.05
    )
    assert w["days_to_stress"] is not None  # 35 mm depleted of 33.6 mm RAW -> already at/near stress


def test_nothing_to_assess_and_history(api: TestClient, admin: TestClient, farm: dict[str, Any]) -> None:
    empty = make_zone(api, farm["id"], "Empty")
    a = ok(api.get(f"{V1}/zones/{empty['id']}/soil"))
    assert a["index"] is None and a["confidence"] == 0 and len(a["not_assessed"]) == 7
    err(api.post(f"{V1}/zones/{empty['id']}/soil/assessments"), 422, "invalid")

    zone = make_zone(api, farm["id"], "Tested")
    lab_test(api, zone["id"], ph=6.5, nitrogen_mg_kg=200)
    saved = ok(api.post(f"{V1}/zones/{zone['id']}/soil/assessments"), 201)
    assert saved["predicted_value"]["components"]["ph"]["status"] == "in_range"
    assert 0 < saved["confidence"] <= 1 and "not a trained model" in saved["limitations"]
    history = ok(api.get(f"{V1}/zones/{zone['id']}/soil/assessments"))
    assert history["total"] == 1 and history["items"][0]["id"] == saved["id"]

    summary = ok(api.get(f"{V1}/farms/{farm['id']}/soil"))
    assert {s["zone_name"]: s["index"] is not None for s in summary} == {"Empty": False, "Tested": True}


def test_soil_is_owner_only(client_for: ClientFor, api: TestClient, farm: dict[str, Any]) -> None:
    zone = make_zone(api, farm["id"])
    mallory = client_for("mallory@example.com")
    err(mallory.get(f"{V1}/zones/{zone['id']}/soil"), 404, "not_found")
    err(mallory.post(f"{V1}/zones/{zone['id']}/soil/assessments"), 404, "not_found")
    err(mallory.get(f"{V1}/farms/{farm['id']}/soil"), 404, "not_found")
