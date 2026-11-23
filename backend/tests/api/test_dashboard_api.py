"""Dashboard summary, time series and Open-Meteo weather (network mocked)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.dashboard import get_weather_client
from app.integrations import open_meteo
from app.integrations.open_meteo import OpenMeteoClient, WeatherUnavailableError
from app.models import WeatherData
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor


# --- fixtures --------------------------------------------------------------
def open_meteo_payload(now: datetime) -> dict[str, Any]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    times = [start + timedelta(hours=i) for i in range(24 * 8)]
    hourly = {
        "time": [t.strftime("%Y-%m-%dT%H:%M") for t in times],
        "temperature_2m": [20 + (i % 24) / 2 for i in range(len(times))],
        "relative_humidity_2m": [60] * len(times),
        "precipitation_probability": [10 * (i % 5) for i in range(len(times))],
        "precipitation": [0.2 if i % 24 == 15 else 0.0 for i in range(len(times))],
        "wind_speed_10m": [2.5] * len(times),
        "wind_direction_10m": [90] * len(times),
        "cloud_cover": [40] * len(times),
        "shortwave_radiation": [0.0] * len(times),
        "et0_fao_evapotranspiration": [0.2] * len(times),
    }
    current = {
        "time": now.strftime("%Y-%m-%dT%H:%M"),
        "temperature_2m": 24.6,
        "relative_humidity_2m": 55,
        "precipitation": 0.0,
        "wind_speed_10m": 1.6,
        "wind_direction_10m": 73,
        "cloud_cover": 54,
        "shortwave_radiation": 412.0,
    }
    return {"latitude": 17.38, "longitude": 78.49, "current": current, "hourly": hourly}


class FakeOpenMeteo:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.last_params: dict[str, str] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self.last_params = dict(request.url.params)
        if self.fail:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json=open_meteo_payload(datetime.now(UTC)))


@pytest.fixture
def meteo(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> FakeOpenMeteo:
    monkeypatch.setattr(open_meteo, "BACKOFF_S", 0)
    fake = FakeOpenMeteo()
    client = OpenMeteoClient(transport=httpx.MockTransport(fake.handler))
    api.app.dependency_overrides[get_weather_client] = lambda: client  # type: ignore[attr-defined]
    return fake


@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    body = {"name": "Dash Farm", "latitude": 17.385, "longitude": 78.4867, "timezone": "Asia/Kolkata"}
    f: dict[str, Any] = ok(api.post(f"{V1}/farms", json=body), 201)
    return f


# --- weather ---------------------------------------------------------------
def test_weather_is_fetched_stored_and_cached(
    api: TestClient, db: Session, meteo: FakeOpenMeteo, farm: dict[str, Any]
) -> None:
    w = ok(api.get(f"{V1}/farms/{farm['id']}/weather"))
    assert meteo.calls == 1
    assert meteo.last_params["latitude"] == "17.385" and "user" not in str(
        meteo.last_params
    )  # coordinates only
    assert w["attribution"].startswith("Weather data by Open-Meteo.com")
    assert w["current"]["temperature_c"] == 24.6 and w["stale"] is False and w["error"] is None
    assert 45 <= len(w["hourly"]) <= 48
    assert len(w["daily"]) >= 5
    # The outlook starts at the farm's LOCAL today, even though the feed is in UTC.
    assert w["daily"][0]["date"] == datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    assert meteo.last_params["past_days"] == "1"
    day = w["daily"][0]
    assert day["temp_min_c"] <= day["temp_max_c"]
    assert day["et0_mm"] == pytest.approx(24 * 0.2, abs=0.01)  # 24 local hours summed in Asia/Kolkata
    stored = db.scalar(select(func.count()).select_from(WeatherData).where(WeatherData.farm_id == farm["id"]))

    ok(api.get(f"{V1}/farms/{farm['id']}/weather"))
    assert meteo.calls == 1  # served from the database within 30 minutes
    ok(api.get(f"{V1}/farms/{farm['id']}/weather", params={"refresh": True}))
    assert meteo.calls == 2
    again = db.scalar(select(func.count()).select_from(WeatherData).where(WeatherData.farm_id == farm["id"]))
    assert again == stored  # upsert, not duplicate rows


def test_weather_outage_is_reported_not_invented(
    api: TestClient, meteo: FakeOpenMeteo, farm: dict[str, Any]
) -> None:
    meteo.fail = True
    w = ok(api.get(f"{V1}/farms/{farm['id']}/weather"))
    assert w["current"] is None and w["hourly"] == [] and w["stale"] is True
    assert "Open-Meteo" in w["error"]
    meteo.fail = False
    ok(api.get(f"{V1}/farms/{farm['id']}/weather"))
    meteo.fail = True
    cached = ok(api.get(f"{V1}/farms/{farm['id']}/weather", params={"refresh": True}))
    assert cached["current"]["temperature_c"] == 24.6  # last good data kept...
    assert cached["error"] is not None  # ...and the failure is visible


def test_weather_needs_coordinates_and_ownership(
    api: TestClient, client_for: ClientFor, meteo: FakeOpenMeteo
) -> None:
    no_loc = ok(api.post(f"{V1}/farms", json={"name": "Nowhere"}), 201)
    err(api.get(f"{V1}/farms/{no_loc['id']}/weather"), 422, "invalid")
    err(client_for("mallory@example.com").get(f"{V1}/farms/{no_loc['id']}/weather"), 404, "not_found")
    assert meteo.calls == 0
    err(api.post(f"{V1}/farms", json={"name": "x", "timezone": "Mars/Olympus"}), 422, "validation_error")


# --- dashboard & series ----------------------------------------------------
def build_farm(api: TestClient, admin: TestClient, farm: dict[str, Any]) -> dict[str, Any]:
    north, south = make_zone(api, farm["id"], "North"), make_zone(api, farm["id"], "South")
    for z in (north, south):
        ok(
            api.post(
                f"{V1}/zones/{z['id']}/simulator/provision",
                json={"sensor_types": ["soil_moisture", "temperature"]},
            ),
            201,
        )
    ok(api.post(f"{V1}/farms/{farm['id']}/simulator/backfill", json={"hours": 6, "step_minutes": 10}))
    crop = ok(admin.post(f"{V1}/crops", json={"common_name": "Dash tomato", "category": "vegetable"}), 201)
    ok(
        api.post(
            f"{V1}/zones/{north['id']}/crop-cycles",
            json={"crop_id": crop["id"], "status": "growing", "planted_on": "2026-09-01"},
        ),
        201,
    )
    now = datetime.now(UTC)
    ok(
        api.post(
            f"{V1}/zones/{north['id']}/irrigation-events",
            json={
                "method": "drip",
                "status": "completed",
                "volume_liters": 1500,
                "started_at": (now - timedelta(days=2)).isoformat(),
            },
        ),
        201,
    )
    ok(
        api.post(
            f"{V1}/zones/{south['id']}/irrigation-events",
            json={
                "method": "drip",
                "status": "completed",
                "volume_liters": 999,
                "started_at": (now - timedelta(days=9)).isoformat(),
            },
        ),
        201,
    )  # outside 7 d
    ok(
        api.post(
            f"{V1}/zones/{south['id']}/fertilizer-applications",
            json={
                "applied_at": (now - timedelta(hours=3)).isoformat(),
                "product_name": "Urea",
                "method": "broadcast",
                "quantity_kg": 25,
                "n_pct": 46,
            },
        ),
        201,
    )
    for sev in ("critical", "warning", "info"):
        ok(
            api.post(
                f"{V1}/farms/{farm['id']}/alerts",
                json={"severity": sev, "category": "soil", "title": f"{sev} alert", "message": "m"},
            ),
            201,
        )
    return {"north": north, "south": south}


def test_dashboard_summary_reflects_stored_records(
    api: TestClient, admin: TestClient, farm: dict[str, Any]
) -> None:
    zones = build_farm(api, admin, farm)
    d = ok(api.get(f"{V1}/farms/{farm['id']}/dashboard"))

    assert d["sensors"] == {"total": 4, "active": 4, "simulated": 4, "hardware": 0, "reporting": 4}
    north = next(z for z in d["zones"] if z["id"] == zones["north"]["id"])
    assert north["active_cycle"]["crop_name"] == "Dash tomato"
    assert set(north["latest"]) == {"soil_moisture", "temperature"}
    assert north["latest"]["soil_moisture"]["unit"] == "%"

    assert d["alerts"]["open"] == 3
    assert d["alerts"]["by_severity"] == {"info": 1, "warning": 1, "critical": 1}
    assert [a["severity"] for a in d["alerts"]["recent"]] == ["critical", "warning", "info"]

    assert d["water_7d"] == {"liters": 1500.0, "events": 1}  # the 9-day-old event is excluded
    assert d["activity"][0]["kind"] == "fertilizer"  # newest first
    assert {a["kind"] for a in d["activity"]} == {"fertilizer", "irrigation"}

    assert d["readings_24h"]["count"] == 4 * 37  # 6 h at 10 min, inclusive
    moisture = next(s for s in d["stats_24h"] if s["sensor_type"] == "soil_moisture")
    assert moisture["min"] <= moisture["avg"] <= moisture["max"]


def test_series_buckets_per_zone_and_excludes_suspect_values(
    api: TestClient, admin: TestClient, farm: dict[str, Any]
) -> None:
    zones = build_farm(api, admin, farm)
    sensors = ok(api.get(f"{V1}/farms/{farm['id']}/sensors", params={"sensor_type": "temperature"}))["items"]
    spike_at = (datetime.now(UTC) - timedelta(minutes=2)).replace(microsecond=0).isoformat()
    ok(
        api.post(
            f"{V1}/sensors/{sensors[0]['id']}/readings",
            json={"readings": [{"recorded_at": spike_at, "value": 400}]},
        )
    )  # > max_valid

    s = ok(api.get(f"{V1}/farms/{farm['id']}/series", params={"sensor_type": "temperature", "hours": 6}))
    assert s["bucket_minutes"] == 5 and s["unit"] == "°C" and s["includes_simulated"] is True
    assert {z["zone_name"] for z in s["zones"]} == {"North", "South"}
    for z in s["zones"]:
        assert len(z["points"]) >= 30
        assert all(p["max"] < 80 for p in z["points"])  # the suspect 400 °C spike is excluded
        times = [p["t"] for p in z["points"]]
        assert times == sorted(times)
    assert zones["north"]["id"] in {z["zone_id"] for z in s["zones"]}

    hourly = ok(
        api.get(
            f"{V1}/farms/{farm['id']}/series",
            params={"sensor_type": "temperature", "hours": 6, "bucket_minutes": 60},
        )
    )
    assert all(p["n"] <= 6 for z in hourly["zones"] for p in z["points"])  # <= 6 ten-minute readings per hour
    err(
        api.get(
            f"{V1}/farms/{farm['id']}/series",
            params={"sensor_type": "temperature", "hours": 744, "bucket_minutes": 1},
        ),
        422,
        "invalid",
    )
    err(api.get(f"{V1}/farms/{farm['id']}/series", params={"sensor_type": "radar"}), 422, "validation_error")


def test_dashboard_is_owner_only(client_for: ClientFor, farm: dict[str, Any]) -> None:
    mallory = client_for("mallory@example.com")
    err(mallory.get(f"{V1}/farms/{farm['id']}/dashboard"), 404, "not_found")
    err(
        mallory.get(f"{V1}/farms/{farm['id']}/series", params={"sensor_type": "temperature"}),
        404,
        "not_found",
    )


def test_weather_client_retries_rate_limits_and_reports_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(open_meteo, "BACKOFF_S", 0)
    calls: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": True, "reason": "Minutely API request limit exceeded"})
        return httpx.Response(200, json=open_meteo_payload(datetime.now(UTC)))

    assert OpenMeteoClient(transport=httpx.MockTransport(flaky)).forecast(17.4, 78.5)
    assert len(calls) == 2  # recovered on the retry

    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": True, "reason": "Daily API request limit exceeded"})

    with pytest.raises(WeatherUnavailableError, match="HTTP 429: Daily API request limit exceeded"):
        OpenMeteoClient(transport=httpx.MockTransport(limited)).forecast(17.4, 78.5)

    bad: list[int] = []

    def invalid(request: httpx.Request) -> httpx.Response:
        bad.append(1)
        return httpx.Response(400, json={"error": True, "reason": "Bad latitude"})

    with pytest.raises(WeatherUnavailableError, match="HTTP 400: Bad latitude"):
        OpenMeteoClient(transport=httpx.MockTransport(invalid)).forecast(17.4, 78.5)
    assert len(bad) == 1  # request errors are not retried

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(WeatherUnavailableError, match="network error: ConnectError"):
        OpenMeteoClient(transport=httpx.MockTransport(down)).forecast(17.4, 78.5)

    with pytest.raises(WeatherUnavailableError, match="invalid response"):
        html = httpx.MockTransport(lambda r: httpx.Response(200, text="<html>"))
        OpenMeteoClient(transport=html).forecast(1, 1)
