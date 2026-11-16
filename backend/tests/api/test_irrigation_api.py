# ruff: noqa: E501  (compact fixtures)
"""Smart irrigation: the scheduling engine on hand-checked cases, then the API on stored data."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain import irrigation as eng
from app.models import WeatherData
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor

D0 = date(2026, 11, 14)


def days(et0: list[float], rain: list[float] | None = None) -> list[dict[str, Any]]:
    rain = rain or [0.0] * len(et0)
    return [
        {"date": D0 + timedelta(days=i), "et0_mm": e, "precipitation_mm": r}
        for i, (e, r) in enumerate(zip(et0, rain, strict=True))
    ]


# Loam + tomato: TAW 91 mm, RAW 36.4 mm, Kc 1.15 (Phase 8 hand calculation).
BASE = {"taw_mm": 91.0, "raw_mm": 36.4, "kc": 1.15, "method": "drip", "area_ha": 0.5}


# --- engine ---------------------------------------------------------------------------
def test_irrigates_on_the_day_depletion_passes_raw_and_refills_to_fc() -> None:
    # Start 20 mm; ETc 5.75 mm/day -> 25.75, 31.5, 37.25 (> 36.4) on day 3.
    p = eng.plan(depletion_mm=20, forecast=days([5] * 5), **BASE)
    (e,) = p["events"][:1]
    assert e["date"] == D0 + timedelta(days=2) and e["net_mm"] == 37.2 and e["urgent"] is False
    assert e["gross_mm"] == round(37.2 / 0.9, 1) and e["volume_liters"] == round(e["gross_mm"] * 5000)
    assert p["days"][2]["depletion_end_mm"] == 0.0  # refilled to field capacity
    assert p["days"][3]["depletion_start_mm"] == 0.0


def test_already_stressed_is_urgent_today() -> None:
    p = eng.plan(depletion_mm=50, forecast=days([5, 5]), **BASE)
    assert p["events"][0]["day_index"] == 0 and p["events"][0]["urgent"] is True


def test_rain_ahead_defers_irrigation_and_saving_is_reported() -> None:
    # Day 3 would pass RAW, but 30 mm (24 mm effective) on day 4 brings it back under.
    p = eng.plan(depletion_mm=20, forecast=days([5] * 5, [0, 0, 0, 30, 0]), **BASE)
    ignoring = eng.plan(depletion_mm=20, forecast=days([5] * 5, [0, 0, 0, 30, 0]), rain_aware=False, **BASE)
    assert p["days"][2]["note"].startswith("deferred") and p["deferred_by_rain_mm"] > 0
    assert p["total_gross_mm"] < ignoring["total_gross_mm"]


def test_never_defers_past_the_wilting_point() -> None:
    p = eng.plan(depletion_mm=88, forecast=days([5, 5], [0, 50]), **BASE)
    assert p["events"] and p["events"][0]["day_index"] == 0


def test_refill_leaves_room_for_next_day_rain() -> None:
    p = eng.plan(depletion_mm=35, forecast=days([5, 5], [0, 10]), **BASE)
    # 35 + 5.75 = 40.75 > RAW; next day effective rain 8 mm; covered? 40.75 + 5.75 - 8 = 38.5 > RAW -> irrigate 40.75 - 8.
    assert p["events"][0]["net_mm"] == 32.8 and "rain expected the next day" in p["events"][0]["reason"]


def test_light_rain_and_efficiencies() -> None:
    assert eng.effective_rain(1.9) == 0 and eng.effective_rain(10) == 8
    assert eng.efficiency("sprinkler") == 0.75 and eng.efficiency(None) == eng.DEFAULT_EFFICIENCY
    assert eng.net_mm_from_volume(10_000, 1, "drip") == pytest.approx(0.9)  # 10 m3 on 1 ha = 1 mm gross


def test_window_prefers_calm_morning_and_warns_sprinklers() -> None:
    hours = [
        {"local_hour": h, "wind_speed_ms": w}
        for h, w in [(4, 0.1), (5, 5.0), (6, 4.6), (7, 4.5), (8, 6.0), (12, 0.0)]
    ]
    w = eng.best_window(hours, "sprinkler")
    assert w["start_local_hour"] == 7 and "drift" in w["basis"]
    assert eng.best_window([], "drip")["start_local_hour"] == 5


# --- API -------------------------------------------------------------------------------
@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    f: dict[str, Any] = ok(
        api.post(
            f"{V1}/farms", json={"name": "Water Farm", "latitude": 17.4, "longitude": 78.5, "timezone": "UTC"}
        ),
        201,
    )
    return f


@pytest.fixture
def zone(api: TestClient, admin: TestClient, db: Session, farm: dict[str, Any]) -> dict[str, Any]:
    z = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/zones",
            json={
                "name": "Tomatoes",
                "zone_type": "field",
                "area_hectares": 0.5,
                "irrigation_method": "drip",
            },
        ),
        201,
    )
    crop = ok(
        admin.post(
            f"{V1}/crops", json={"common_name": "Tomato", "category": "vegetable", "typical_cycle_days": 110}
        ),
        201,
    )
    planted = (datetime.now(UTC).date() - timedelta(days=60)).isoformat()  # mid-season, Kc = 1.15
    ok(
        api.post(
            f"{V1}/zones/{z['id']}/crop-cycles",
            json={"crop_id": crop["id"], "status": "growing", "planted_on": planted},
        ),
        201,
    )
    ok(api.post(f"{V1}/zones/{z['id']}/soil-profiles", json={"texture": "loam"}), 201)
    measured = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
    ok(
        api.post(
            f"{V1}/zones/{z['id']}/soil-measurements",
            json={"measured_at": measured, "source": "lab", "moisture_pct": 21.0},
        ),
        201,
    )
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    for h in range(24 * 7):  # 6 mm/day ET0, no rain
        db.add(WeatherData(farm_id=farm["id"], kind="forecast", source="open-meteo", valid_at=midnight + timedelta(hours=h),
                           et0_mm=0.25, precipitation_mm=0, wind_speed_ms=1 + (h % 24) / 10))  # fmt: skip
    db.commit()  # flushed-only rows would be lost: each API request rolls back on exit
    return z


def test_plan_schedule_and_counted_irrigation(
    api: TestClient, farm: dict[str, Any], zone: dict[str, Any]
) -> None:
    p = ok(api.get(f"{V1}/zones/{zone['id']}/irrigation/plan"))
    # Loam FC 25 %, theta 21 % over 0.7 m -> 28 mm depleted; ETc 6.9 mm/day -> passes 36.4 mm on day 2.
    assert p["water"]["depletion_mm"] == 28.0 and p["water"]["irrigation_since_mm"] == 0
    assert p["status"] == "planned" and len(p["plan"]["days"]) == 7
    first = p["plan"]["events"][0]
    assert first["day_index"] == 1 and first["volume_liters"] == round(first["gross_mm"] * 5000)
    assert first["window"]["start_local_hour"] == 5  # calmest morning hour in the stored forecast
    assert p["rain_aware_saving"]["gross_mm"] == 0  # no rain forecast, nothing to save
    assert any("not a trained model" in lim for lim in p["limitations"])

    event = ok(api.post(f"{V1}/zones/{zone['id']}/irrigation/schedule", json={"date": first["date"]}), 201)
    assert (
        event["status"] == "scheduled"
        and event["trigger"] == "scheduled"
        and event["volume_liters"] == first["volume_liters"]
    )
    again = ok(api.get(f"{V1}/zones/{zone['id']}/irrigation/plan"))
    assert again["plan"]["events"][0]["already_scheduled"] and again["scheduled"][0]["id"] == event["id"]
    err(
        api.post(f"{V1}/zones/{zone['id']}/irrigation/schedule", json={"date": first["date"]}),
        409,
        "conflict",
    )
    err(
        api.post(f"{V1}/zones/{zone['id']}/irrigation/schedule", json={"date": "2030-01-01"}), 409, "conflict"
    )

    # Completing 100 m3 of drip irrigation after the measurement: 100,000 L / 5,000 m2 x 0.9 = 18 mm net.
    ok(
        api.patch(
            f"{V1}/irrigation-events/{event['id']}",
            json={
                "status": "completed",
                "started_at": datetime.now(UTC).isoformat(),
                "volume_liters": 100000,
            },
        )
    )
    after = ok(api.get(f"{V1}/zones/{zone['id']}/irrigation/plan"))
    assert after["water"]["irrigation_since_mm"] == 18.0 and after["water"]["depletion_mm"] == 10.0
    assert "irrigation logged since" in after["water"]["sources"]["moisture"]

    use = ok(api.get(f"{V1}/zones/{zone['id']}/irrigation/water-use?days=7"))
    assert use["events"] == 0  # completed today; the window ends at local midnight
    summary = ok(api.get(f"{V1}/farms/{farm['id']}/irrigation/plan"))
    assert summary[0]["zone_name"] == "Tomatoes" and summary[0]["status"] in (
        "planned",
        "no_irrigation_needed",
    )


def test_water_use_counts_completed_events_and_flags_missing_weather(
    api: TestClient, zone: dict[str, Any]
) -> None:
    two_days_ago = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    for vol in (20000, None):
        body = {"method": "drip", "status": "completed", "trigger": "manual", "started_at": two_days_ago}
        ok(
            api.post(
                f"{V1}/zones/{zone['id']}/irrigation-events",
                json={**body, **({"volume_liters": vol} if vol else {})},
            ),
            201,
        )
    use = ok(api.get(f"{V1}/zones/{zone['id']}/irrigation/water-use?days=7"))
    assert (use["events"], use["events_without_volume"], use["applied_liters"]) == (2, 1, 20000)
    assert use["applied_gross_mm"] == 4.0 and use["applied_net_mm"] == 3.6
    assert (
        use["weather_days_covered"] == 0 and use["applied_to_need_ratio"] is None
    )  # no past weather stored: no ratio


def test_no_moisture_means_no_plan(api: TestClient, farm: dict[str, Any]) -> None:
    z = make_zone(api, farm["id"], "Bare")
    p = ok(api.get(f"{V1}/zones/{z['id']}/irrigation/plan"))
    assert p["status"] == "no_moisture_data" and p["plan"] is None and p["confidence"] == 0


def test_irrigation_is_owner_only(client_for: ClientFor, api: TestClient, zone: dict[str, Any]) -> None:
    mallory = client_for("mallory@example.com")
    err(mallory.get(f"{V1}/zones/{zone['id']}/irrigation/plan"), 404, "not_found")
    err(
        mallory.post(f"{V1}/zones/{zone['id']}/irrigation/schedule", json={"date": "2026-11-15"}),
        404,
        "not_found",
    )
    err(mallory.get(f"{V1}/zones/{zone['id']}/irrigation/water-use"), 404, "not_found")
