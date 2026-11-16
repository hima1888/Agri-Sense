# ruff: noqa: E501  (compact fixtures)
"""Fertilizer planning and chemical-use tracking: domain rules by hand, then the API on stored data."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain import chemicals, nutrients
from app.models import WeatherData
from tests.api.helpers import V1, err, ok
from tests.conftest import ClientFor

NOW = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
LAB = "lab test (10 days old)"
PROBE = "NPK probe 24 h mean (simulated)"


def rating(status: str, source: str = LAB) -> dict[str, Any]:
    return {"status": status, "source": source}


# --- fertilizer -------------------------------------------------------------------
def test_products_cover_the_need_exactly() -> None:
    prods = {p["product"]: p["kg_per_ha"] for p in nutrients.products_for({"n": 120, "p2o5": 60, "k2o": 40})}
    assert prods == {"DAP": 130.4, "MOP": 66.7, "Urea": 209.8}
    # Check by recomputing nutrients delivered: N = DAP 18 % + urea 46 %, P2O5 = DAP 46 %, K2O = MOP 60 %.
    assert prods["DAP"] * 0.18 + prods["Urea"] * 0.46 == pytest.approx(120, abs=0.1)
    assert prods["DAP"] * 0.46 == pytest.approx(60, abs=0.1) and prods["MOP"] * 0.60 == pytest.approx(
        40, abs=0.1
    )


def test_lab_ratings_adjust_the_dose_and_probes_do_not() -> None:
    p = nutrients.plan(crop="Maize", target=None, target_source=None, irrigation_method="drip", area_ha=2.0,
                       soil_ratings={"nitrogen": rating("low"), "phosphorus": rating("high"), "potassium": rating("low", PROBE)},
                       applied_kg_ha={"n": 0.0, "p2o5": 0.0, "k2o": 0.0})  # fmt: skip
    assert p["target_kg_ha"] == {"n": 120, "p2o5": 60, "k2o": 40} and "indicative" in p["target_source"]
    assert p["adjusted_kg_ha"] == {"n": 150.0, "p2o5": 45.0, "k2o": 40.0}  # x1.25, x0.75, probe ignored
    assert p["soil_test_saving_kg_ha"] == {"p2o5": 15.0}
    k = next(f for f in p["factors"] if f["nutrient"] == "k2o")
    assert k["factor"] == 1.0 and "not used to change the dose" in k["note"]
    assert any("INDICATIVE" in lim for lim in p["limitations"]) and p["confidence"] == 0.5
    assert any("fertigation" in n for n in p["notes"])
    dap = next(x for x in p["products"] if x["product"] == "DAP")
    assert dap["kg_for_zone"] == round(dap["kg_per_ha"] * 2, 1) and dap["bags_50kg"] == round(
        dap["kg_for_zone"] / 50, 1
    )


def test_applied_fertilizer_is_credited_and_surplus_flagged() -> None:
    applied = nutrients.applied_nutrients([{"quantity_kg": 100, "n_pct": 46, "p_pct": None, "k_pct": None},
                                           {"quantity_kg": 50, "n_pct": 18, "p_pct": 46, "k_pct": 0}], area_ha=0.5)  # fmt: skip
    assert applied == {"n": 110.0, "p2o5": 46.0, "k2o": 0.0}  # (46 + 9) / 0.5 ; 23 / 0.5
    p = nutrients.plan(crop="tomato", target={"n": 100, "p2o5": 40, "k2o": 50}, target_source="State PoP 2024",
                       soil_ratings={}, applied_kg_ha=applied, area_ha=0.5, irrigation_method=None)  # fmt: skip
    assert p["remaining_kg_ha"] == {"n": 0.0, "p2o5": 0.0, "k2o": 50.0}
    assert p["surplus_kg_ha"] == {"n": 10.0, "p2o5": 6.0}
    assert [x["product"] for x in p["products"]] == ["MOP"] and p["confidence"] == round(0.85 * 0.75, 2)


def test_unknown_crop_needs_a_target() -> None:
    p = nutrients.plan(
        crop="Okra",
        target=None,
        target_source=None,
        soil_ratings={},
        applied_kg_ha={"n": 0, "p2o5": 0, "k2o": 0},
        area_ha=1,
        irrigation_method=None,
    )
    assert p["status"] == "no_target" and "Package of Practices" in p["message"]


# --- chemicals --------------------------------------------------------------------
def app_(
    i: int, kind: str, days_ago: int, qty: float, phi: int | None = None, det: int | None = None
) -> dict[str, Any]:
    return {"id": i, "product_name": f"P{i}", "pesticide_type": kind, "quantity": qty, "quantity_unit": "l",
            "applied_at": NOW - timedelta(days=days_ago), "disease_detection_id": det, "pre_harvest_interval_days": phi}  # fmt: skip


def test_use_summary_phi_and_evidence() -> None:
    apps = [
        app_(1, "fungicide", 20, 1.0, phi=7, det=5),
        app_(2, "insecticide", 2, 0.5, phi=10),
        app_(3, "fungicide", 1, 1.0),
    ]
    s = chemicals.use_summary(apps, 0.5, expected_harvest=date(2026, 11, 20), today=NOW.date())
    assert s["applications"] == 3 and s["by_type"] == {"fungicide": 2, "insecticide": 1}
    assert s["quantity_per_ha_by_unit"] == {"l": 5.0} and s["evidence_share"] == 0.33
    status = {p["id"]: p["status"] for p in s["phi"]}
    assert (
        status == {1: "safe", 2: "conflict", 3: "unknown"} and s["phi_conflicts"] == 1
    )  # 12 Nov + 10 d > 20 Nov


def test_cycle_comparison_per_hectare() -> None:
    cur = chemicals.use_summary([app_(1, "fungicide", 3, 2.0)], 1.0, None, NOW.date())
    prev = chemicals.use_summary(
        [app_(2, "fungicide", 100, 2.0), app_(3, "fungicide", 90, 2.0)], 1.0, None, NOW.date()
    )
    c = chemicals.compare(cur, prev, 1.0, 1.0)
    assert c is not None and c["change_pct"] == -50.0 and c["by_unit_per_ha"]["l"]["change_pct"] == -50.0
    assert chemicals.compare(cur, None, 1.0, 1.0) is None


def hour(i: int, **kw: Any) -> dict[str, Any]:
    base = {
        "precipitation_probability_pct": 10.0,
        "precipitation_mm": 0.0,
        "wind_speed_ms": 2.0,
        "temperature_c": 24.0,
    }
    return {**base, **kw, "valid_at": NOW + timedelta(hours=i)}


def test_spray_check_flags_each_risk() -> None:
    ok_ = chemicals.spray_check(pesticide_type="fungicide", phi_days=7, now=NOW, expected_harvest=date(2026, 12, 1),
                                evidence=[{"label": "Tomato: Early blight", "detected_at": NOW, "outcome": "possible_disease"}],
                                hourly=[hour(i) for i in range(6)], recent_same_type=[])  # fmt: skip
    assert ok_["verdict"] == "ok_to_proceed" and ok_["warnings"] == 0
    bad = chemicals.spray_check(pesticide_type="fungicide", phi_days=21, now=NOW, expected_harvest=date(2026, 11, 20),
                                evidence=[], hourly=[hour(0), hour(2, precipitation_probability_pct=70), hour(3, wind_speed_ms=6.5), hour(4, temperature_c=33)],
                                recent_same_type=[NOW - timedelta(days=3)])  # fmt: skip
    status = {c["check"]: c["status"] for c in bad["checks"]}
    assert bad["verdict"] == "hold" and status == {"evidence": "warning", "rain": "warning", "wind": "warning", "heat": "warning",
                                                   "pre_harvest_interval": "warning", "repeat": "warning"}  # fmt: skip
    none = chemicals.spray_check(
        pesticide_type="herbicide",
        phi_days=None,
        now=NOW,
        expected_harvest=None,
        evidence=[],
        hourly=[],
        recent_same_type=[],
    )
    assert {c["check"]: c["status"] for c in none["checks"]}["weather"] == "unknown"


# --- API ------------------------------------------------------------------------------
@pytest.fixture
def setup(api: TestClient, admin: TestClient) -> dict[str, Any]:
    farm = ok(api.post(f"{V1}/farms", json={"name": "Nutrient Farm", "timezone": "UTC"}), 201)
    zone = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/zones",
            json={
                "name": "Wheat Block",
                "zone_type": "field",
                "area_hectares": 2,
                "irrigation_method": "sprinkler",
            },
        ),
        201,
    )
    crop = ok(admin.post(f"{V1}/crops", json={"common_name": "Wheat", "category": "cereal"}), 201)
    planted = (datetime.now(UTC).date() - timedelta(days=30)).isoformat()
    harvest = (datetime.now(UTC).date() + timedelta(days=10)).isoformat()
    cycle = ok(
        api.post(
            f"{V1}/zones/{zone['id']}/crop-cycles",
            json={
                "crop_id": crop["id"],
                "status": "growing",
                "planted_on": planted,
                "expected_harvest_on": harvest,
            },
        ),
        201,
    )
    measured = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    ok(
        api.post(
            f"{V1}/zones/{zone['id']}/soil-measurements",
            json={
                "measured_at": measured,
                "source": "lab",
                "nitrogen_mg_kg": 100,
                "phosphorus_mg_kg": 20,
                "potassium_mg_kg": 80,
            },
        ),
        201,
    )
    return {"farm": farm, "zone": zone, "cycle": cycle, "crop": crop}


def test_plan_target_override_and_credit(api: TestClient, setup: dict[str, Any]) -> None:
    z = setup["zone"]["id"]
    p = ok(api.get(f"{V1}/zones/{z}/nutrients/plan"))
    # Lab: N 224 kg/ha low, P 44.8 high, K 179 medium -> 120x1.25, 60x0.75, 40x1.
    assert (
        p["crop"] == "Wheat"
        and p["target_is_custom"] is False
        and p["adjusted_kg_ha"] == {"n": 150.0, "p2o5": 45.0, "k2o": 40.0}
    )
    ok(
        api.put(
            f"{V1}/crop-cycles/{setup['cycle']['id']}/nutrient-target",
            json={"n": 100, "p2o5": 50, "k2o": 50, "source": "State PoP wheat 2024"},
        )
    )
    when = datetime.now(UTC).isoformat()
    ok(
        api.post(
            f"{V1}/zones/{z}/fertilizer-applications",
            json={
                "applied_at": when,
                "product_name": "Urea",
                "method": "broadcast",
                "quantity_kg": 200,
                "n_pct": 46,
            },
        ),
        201,
    )
    p = ok(api.get(f"{V1}/zones/{z}/nutrients/plan"))
    assert p["target_is_custom"] and p["target_source"] == "State PoP wheat 2024" and p["confidence"] == 0.85
    assert (
        p["applied_kg_ha"]["n"] == 46.0 and p["remaining_kg_ha"]["n"] == 125.0 - 46.0
    )  # 100 x 1.25 - 200 x 0.46 / 2
    assert api.delete(f"{V1}/crop-cycles/{setup['cycle']['id']}/nutrient-target").status_code == 204
    assert ok(api.get(f"{V1}/zones/{z}/nutrients/plan"))["target_is_custom"] is False
    err(
        api.put(
            f"{V1}/crop-cycles/{setup['cycle']['id']}/nutrient-target",
            json={"n": -1, "p2o5": 0, "k2o": 0, "source": "x"},
        ),
        422,
        "validation_error",
    )


def test_use_spray_check_and_evidence_link(api: TestClient, db: Session, setup: dict[str, Any]) -> None:
    z, farm = setup["zone"]["id"], setup["farm"]["id"]
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for h in range(8):
        db.add(WeatherData(farm_id=farm, kind="forecast", source="open-meteo", valid_at=start + timedelta(hours=h),
                           precipitation_probability_pct=10, precipitation_mm=0, wind_speed_ms=6 if h == 2 else 2, temperature_c=22))  # fmt: skip
    db.commit()  # flushed-only rows would be lost: each API request rolls back on exit
    check = ok(api.get(f"{V1}/zones/{z}/chemicals/spray-check?pesticide_type=fungicide&phi_days=21"))
    status = {c["check"]: c["status"] for c in check["checks"]}
    assert (
        check["verdict"] == "hold"
        and status["wind"] == "warning"
        and status["pre_harvest_interval"] == "warning"
        and status["evidence"] == "warning"
    )

    body = {"applied_at": datetime.now(UTC).isoformat(), "product_name": "Mancozeb 75 WP", "pesticide_type": "fungicide",
            "quantity": 2, "quantity_unit": "kg", "pre_harvest_interval_days": 21}  # fmt: skip
    ok(api.post(f"{V1}/zones/{z}/pesticide-applications", json=body), 201)
    err(
        api.post(f"{V1}/zones/{z}/pesticide-applications", json={**body, "disease_detection_id": 999999}),
        422,
        "invalid",
    )
    use = ok(api.get(f"{V1}/zones/{z}/chemicals/use"))
    cur = use["current"]
    assert (
        cur["applications"] == 1
        and cur["quantity_per_ha_by_unit"] == {"kg": 1.0}
        and cur["phi_conflicts"] == 1
    )
    assert use["comparison"] is None and use["previous"] is None  # no earlier cycle: nothing invented
    assert (
        ok(api.get(f"{V1}/zones/{z}/chemicals/spray-check?pesticide_type=fungicide"))["checks"][-1]["status"]
        == "warning"
    )  # repeat


def test_owner_only(client_for: ClientFor, setup: dict[str, Any]) -> None:
    mallory = client_for("mallory@example.com")
    z = setup["zone"]["id"]
    err(mallory.get(f"{V1}/zones/{z}/nutrients/plan"), 404, "not_found")
    err(mallory.get(f"{V1}/zones/{z}/chemicals/use"), 404, "not_found")
    err(mallory.get(f"{V1}/zones/{z}/chemicals/spray-check?pesticide_type=fungicide"), 404, "not_found")
    err(
        mallory.put(
            f"{V1}/crop-cycles/{setup['cycle']['id']}/nutrient-target",
            json={"n": 1, "p2o5": 1, "k2o": 1, "source": "abc"},
        ),
        404,
        "not_found",
    )
