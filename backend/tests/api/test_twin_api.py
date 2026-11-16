"""Solar position and the digital-twin scene endpoint."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.simulator.physics import solar_azimuth_deg, solar_elevation_deg
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor

HYD = (17.385, 78.4867)


def at_ist(hour: float) -> datetime:
    return datetime(2026, 11, 14, tzinfo=UTC) + timedelta(hours=hour - 5.5)


@pytest.mark.parametrize(("hour", "lo", "hi"), [(7.0, 90, 135), (12.25, 165, 200), (17.0, 225, 270)])
def test_sun_rises_east_peaks_south_sets_west(hour: float, lo: float, hi: float) -> None:
    assert lo < solar_azimuth_deg(*HYD, at_ist(hour)) < hi


def test_elevation_unchanged_by_refactor() -> None:
    assert solar_elevation_deg(*HYD, at_ist(12.25)) > 45
    assert solar_elevation_deg(*HYD, at_ist(0)) < -30


@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    body = {"name": "Twin Farm", "latitude": HYD[0], "longitude": HYD[1], "timezone": "Asia/Kolkata"}
    f: dict[str, Any] = ok(api.post(f"{V1}/farms", json=body), 201)
    return f


def boxes_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ax, az, bx, bz = a["center"][0], a["center"][1], b["center"][0], b["center"][1]
    overlap_x = abs(ax - bx) < (a["size"][0] + b["size"][0]) / 2
    overlap_z = abs(az - bz) < (a["size"][1] + b["size"][1]) / 2
    return bool(overlap_x and overlap_z)


def test_twin_scene_is_built_from_records(api: TestClient, admin: TestClient, farm: dict[str, Any]) -> None:
    north = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/zones",
            json={"name": "North", "area_hectares": 2, "irrigation_method": "drip"},
        ),
        201,
    )
    ok(api.post(f"{V1}/farms/{farm['id']}/zones", json={"name": "South", "area_hectares": 1}), 201)
    ok(api.post(f"{V1}/zones/{north['id']}/simulator/provision", json={}), 201)
    ok(api.post(f"{V1}/farms/{farm['id']}/simulator/backfill", json={"hours": 1, "step_minutes": 10}))
    crop = ok(
        admin.post(
            f"{V1}/crops",
            json={"common_name": "Twin tomato", "category": "vegetable", "typical_cycle_days": 100},
        ),
        201,
    )
    planted = (datetime.now(UTC).date() - timedelta(days=50)).isoformat()
    ok(
        api.post(
            f"{V1}/zones/{north['id']}/crop-cycles",
            json={"crop_id": crop["id"], "status": "growing", "planted_on": planted},
        ),
        201,
    )
    ok(
        api.post(
            f"{V1}/zones/{north['id']}/irrigation-events",
            json={
                "method": "drip",
                "status": "running",
                "started_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            },
        ),
        201,
    )

    t = ok(api.get(f"{V1}/farms/{farm['id']}/twin"))
    zones = {z["name"]: z for z in t["zones"]}

    # Zones are sized from their area (auto layout) and never overlap.
    n, s = zones["North"], zones["South"]
    assert n["layout"] == s["layout"] == "auto"
    assert n["size"][0] * n["size"][1] == pytest.approx(20_000, rel=0.01)
    assert not boxes_overlap(n, s)

    # Crop and growth stage come from the crop cycle and the catalogue cycle length.
    assert n["crop"]["crop_name"] == "Twin tomato" and n["crop"]["form"] == "bush"
    assert n["crop"]["growth_fraction"] == pytest.approx(0.5, abs=0.02)
    assert s["crop"] is None
    assert n["irrigating"] is True and s["irrigating"] is False
    assert n["soil_moisture"] is not None

    # Sensors sit inside their zone and carry their latest reading and simulated label.
    assert len(t["sensors"]) == 12
    half_w, half_d = n["size"][0] / 2, n["size"][1] / 2
    for sensor in t["sensors"]:
        assert sensor["is_simulated"] is True and sensor["latest"] is not None
        assert abs(sensor["position"][0] - n["center"][0]) <= half_w
        assert abs(sensor["position"][2] - n["center"][1]) <= half_d

    # Equipment is either data-backed or explicitly schematic.
    infra = {i["id"]: i for i in t["infrastructure"]}
    assert all("schematic" in i for i in t["infrastructure"])
    assert (
        infra["tank"]["level_pct"] is not None and infra["tank"]["schematic"] is False
    )  # from water_level sensor
    assert infra["pump"]["running"] is True
    assert infra[f"pipe-{n['id']}"]["flowing"] is True
    assert f"pipe-{s['id']}" not in infra  # South has no irrigation method
    assert infra["farmhouse"]["schematic"] is True and "gateway" in infra

    # Real sun position for the farm's coordinates.
    assert -90 <= t["sun"]["elevation_deg"] <= 90 and 0 <= t["sun"]["azimuth_deg"] < 360


def test_geojson_boundary_is_projected_to_metres(api: TestClient, farm: dict[str, Any]) -> None:
    lat, lon = HYD
    d = 0.001  # ~111 m north-south, ~106 m east-west at 17.4°N
    ring = [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]
    ok(
        api.post(
            f"{V1}/farms/{farm['id']}/zones",
            json={"name": "Mapped", "boundary": {"type": "Polygon", "coordinates": [ring]}},
        ),
        201,
    )
    z = ok(api.get(f"{V1}/farms/{farm['id']}/twin"))["zones"][0]
    assert z["layout"] == "boundary"
    assert z["size"][0] == pytest.approx(106.2, abs=0.5)
    assert z["size"][1] == pytest.approx(111.3, abs=0.5)
    assert z["center"][1] < 0  # north of the reference point is -z


def test_empty_farm_and_ownership(api: TestClient, client_for: ClientFor, farm: dict[str, Any]) -> None:
    t = ok(api.get(f"{V1}/farms/{farm['id']}/twin"))
    assert t["zones"] == [] and t["sensors"] == []
    assert {i["kind"] for i in t["infrastructure"]} >= {"farmhouse", "road", "solar"}
    make_zone(api, farm["id"])
    err(client_for("mallory@example.com").get(f"{V1}/farms/{farm['id']}/twin"), 404, "not_found")
