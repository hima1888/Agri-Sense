# ruff: noqa: E501  (compact fixtures)
"""Yield estimate: FAO-33 maths by hand, then the API with moisture history, saving and back-testing."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain import yield_model as ym
from app.domain.soil_reference import CROP_WATER, CropWater
from tests.api.helpers import V1, err, ok
from tests.conftest import ClientFor

FLAT = CropWater(1.0, 1.0, 1.0, 0.5, 0.5)  # constant Kc: every day weighs the same
P0 = date(2026, 9, 1)


def est(
    daily: dict[date, float],
    today: date,
    ym_kg: float | None = 10_000,
    crop: str = "maize",
    harvest: date | None = None,
) -> dict[str, Any]:
    return ym.estimate(
        crop=crop,
        planted=P0,
        harvest=harvest or P0 + timedelta(days=99),
        today=today,
        daily_ks=daily,
        cw=FLAT,
        ym_kg_ha=ym_kg,
        ym_source="variety trial",
    )


def test_ks_follows_fao56() -> None:
    assert ym.ks(30, 100, 50, 0.5) == 1.0  # not past RAW
    assert ym.ks(75, 100, 50, 0.5) == pytest.approx(0.5)  # (100 - 75) / (0.5 x 100)
    assert ym.ks(100, 100, 50, 0.5) == 0.0


def test_fully_measured_season_matches_fao33_by_hand() -> None:
    # 100 days, all measured: 50 days Ks 1, 50 days Ks 0.6 -> ETa/ETc 0.8 -> maize Ky 1.25 -> 1 - 1.25 x 0.2 = 0.75
    daily = {P0 + timedelta(days=i): (1.0 if i < 50 else 0.6) for i in range(100)}
    e = est(daily, today=P0 + timedelta(days=120))
    assert e["relative_et"] == {"high": 0.8, "central": 0.8, "low": 0.8}
    assert e["yield_kg_ha"] == {"high": 7500, "central": 7500, "low": 7500}
    assert e["water_loss_pct_central"] == 25.0 and e["season"]["coverage_season"] == 1.0


def test_partial_coverage_gives_a_range() -> None:
    # Day 50 of 100; measured 10 days at Ks 0.5. Unknown past: 40 days. Future: 50 days.
    daily = {P0 + timedelta(days=i): 0.5 for i in range(40, 50)}
    e = est(daily, today=P0 + timedelta(days=49))
    r = e["relative_et"]
    assert r["high"] == pytest.approx((10 * 0.5 + 90) / 100, abs=0.001)
    assert r["central"] == pytest.approx((10 * 0.5 + 40 * 0.5 + 50) / 100, abs=0.001)
    assert r["low"] == pytest.approx(0.5, abs=0.001)
    y = e["yield_kg_ha"]
    assert y["low"] < y["central"] < y["high"] and y["low"] == 3750  # 10000 x (1 - 1.25 x 0.5)
    assert "only 10 of 50 days" in e["limitations"][0] and e["confidence"] < 0.5


def test_kc_weighting_makes_mid_season_stress_cost_more() -> None:
    tomato = CROP_WATER["tomato"]
    early = {P0 + timedelta(days=i): 0.5 for i in range(0, 10)}
    mid = {P0 + timedelta(days=i): 0.5 for i in range(50, 60)}

    def full(d: dict[date, float]) -> dict[date, float]:
        return {**{P0 + timedelta(days=i): 1.0 for i in range(100)}, **d}

    def run(d: dict[date, float]) -> dict[str, Any]:
        return ym.estimate(crop="tomato", planted=P0, harvest=P0 + timedelta(days=99), today=P0 + timedelta(days=120),
                           daily_ks=full(d), cw=tomato, ym_kg_ha=1000, ym_source="x")  # fmt: skip

    assert run(mid)["yield_kg_ha"]["central"] < run(early)["yield_kg_ha"]["central"]


def test_refuses_without_ky_or_reference() -> None:
    assert est({}, P0, crop="rice")["status"] == "ky_unknown"
    assert est({}, P0, ym_kg=None)["status"] == "no_reference"
    e = est({}, P0 + timedelta(days=10))
    assert e["status"] == "estimate" and "No moisture measurements" in e["limitations"][0]
    assert e["yield_kg_ha"]["low"] == e["yield_kg_ha"]["high"] == 10_000  # no evidence of stress, says so


# --- API ------------------------------------------------------------------------------
@pytest.fixture
def setup(api: TestClient, admin: TestClient) -> dict[str, Any]:
    farm = ok(api.post(f"{V1}/farms", json={"name": "Yield Farm", "timezone": "UTC"}), 201)
    zone = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/zones",
            json={"name": "Maize Block", "zone_type": "field", "area_hectares": 2},
        ),
        201,
    )
    crop = ok(
        admin.post(
            f"{V1}/crops", json={"common_name": "Maize", "category": "cereal", "typical_cycle_days": 120}
        ),
        201,
    )
    ok(api.post(f"{V1}/zones/{zone['id']}/soil-profiles", json={"texture": "loam"}), 201)
    today = datetime.now(UTC).date()
    cycle = ok(
        api.post(
            f"{V1}/zones/{zone['id']}/crop-cycles",
            json={
                "crop_id": crop["id"],
                "status": "growing",
                "planted_on": (today - timedelta(days=30)).isoformat(),
            },
        ),
        201,
    )
    return {"farm": farm, "zone": zone, "cycle": cycle, "crop": crop, "today": today}


def moisture(api: TestClient, zone_id: int, days_ago: int, pct: float) -> None:
    at = (datetime.now(UTC) - timedelta(days=days_ago)).replace(hour=9).isoformat()
    ok(
        api.post(
            f"{V1}/zones/{zone_id}/soil-measurements",
            json={"measured_at": at, "source": "field_kit", "moisture_pct": pct},
        ),
        201,
    )


def test_reference_estimate_save_and_backtest(api: TestClient, setup: dict[str, Any]) -> None:
    z, cyc = setup["zone"]["id"], setup["cycle"]["id"]
    e = ok(api.get(f"{V1}/zones/{z}/yield"))
    assert e["status"] == "no_reference" and e["ky"] == 1.25
    err(api.post(f"{V1}/zones/{z}/yield/predictions"), 422, "invalid")

    ok(
        api.put(
            f"{V1}/crop-cycles/{cyc}/yield-reference",
            json={"kg_ha": 6000, "source": "state variety trial 2024"},
        )
    )
    # Loam FC 25 %, WP 12 %, maize Zr 1.0 m, p 0.55: TAW 130, RAW 71.5. 25 % -> Dr 0 (Ks 1); 15 % -> Dr 100 -> Ks (130-100)/(0.45x130) = 0.513.
    moisture(api, z, 10, 25.0)
    moisture(api, z, 5, 15.0)
    e = ok(api.get(f"{V1}/zones/{z}/yield"))
    assert (
        e["status"] == "estimate"
        and e["ym_source"] == "state variety trial 2024"
        and e["season"]["days_measured"] == 2
    )
    y = e["yield_kg_ha"]
    assert y["low"] < y["central"] < y["high"] <= 6000 and e["total_kg"]["central"] == y["central"] * 2
    assert {f["name"] for f in e["factors"]} >= {
        "Attainable yield (Ym)",
        "Yield response to water (Ky)",
        "Days with water stress",
    }
    assert any("NOT modelled" in lim for lim in e["limitations"]) and e["uses_simulated_data"] is False

    saved = ok(api.post(f"{V1}/zones/{z}/yield/predictions"), 201)
    assert saved["predicted_value"]["central"] == y["central"] and saved["predicted_value"]["unit"] == "kg/ha"
    assert ok(api.get(f"{V1}/zones/{z}/yield/predictions"))["total"] == 1

    assert ok(api.get(f"{V1}/farms/{setup['farm']['id']}/yield/backtest"))["n"] == 0  # nothing harvested yet
    actual_total = y["central"] * 2 * 0.9  # a harvest 10 % below the central estimate
    ok(
        api.patch(
            f"{V1}/crop-cycles/{cyc}",
            json={
                "status": "harvested",
                "harvested_on": setup["today"].isoformat(),
                "actual_yield_kg": actual_total,
            },
        )
    )
    bt = ok(api.get(f"{V1}/farms/{setup['farm']['id']}/yield/backtest"))
    assert bt["n"] == 1 and bt["cycles"][0]["error_pct"] == pytest.approx(11.1, abs=0.2)
    assert bt["mean_absolute_error_pct"] == bt["cycles"][0]["error_pct"]


def test_history_supplies_the_reference(api: TestClient, setup: dict[str, Any]) -> None:
    z = setup["zone"]["id"]
    ok(
        api.patch(
            f"{V1}/crop-cycles/{setup['cycle']['id']}",
            json={"status": "harvested", "harvested_on": setup["today"].isoformat(), "actual_yield_kg": 9000},
        )
    )
    ok(
        api.post(
            f"{V1}/zones/{z}/crop-cycles",
            json={
                "crop_id": setup["crop"]["id"],
                "status": "growing",
                "planted_on": setup["today"].isoformat(),
            },
        ),
        201,
    )
    e = ok(api.get(f"{V1}/zones/{z}/yield"))
    assert e["ym_kg_ha"] == 4500 and "past harvest" in e["ym_source"] and e["reference_is_custom"] is False


def test_no_crop_and_isolation(client_for: ClientFor, api: TestClient, setup: dict[str, Any]) -> None:
    other = ok(
        api.post(f"{V1}/farms/{setup['farm']['id']}/zones", json={"name": "Fallow", "zone_type": "field"}),
        201,
    )
    assert ok(api.get(f"{V1}/zones/{other['id']}/yield"))["status"] == "no_crop"
    mallory = client_for("mallory@example.com")
    err(mallory.get(f"{V1}/zones/{setup['zone']['id']}/yield"), 404, "not_found")
    err(
        mallory.put(
            f"{V1}/crop-cycles/{setup['cycle']['id']}/yield-reference", json={"kg_ha": 1, "source": "abc"}
        ),
        404,
        "not_found",
    )
    err(mallory.get(f"{V1}/farms/{setup['farm']['id']}/yield/backtest"), 404, "not_found")
    assert ok(api.get(f"{V1}/yield/ky"))["ky"]["maize"] == 1.25
