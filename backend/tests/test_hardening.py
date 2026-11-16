"""Phase 19: security headers, request-size limit, rate limiting, production docs, CORS."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.hardening import RateLimiter
from app.main import create_app


def client(**kw: Any) -> TestClient:
    settings = Settings(_env_file=None, simulator_enabled=False, alerts_enabled=False, **kw)  # type: ignore[call-arg]
    return TestClient(create_app(settings))


def test_security_headers_on_every_response_including_errors() -> None:
    c = client()
    for res in (c.get("/api/v1/health"), c.get("/api/v1/farms"), c.get("/api/v1/nope")):  # 200, 401, 404
        h = res.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer" and "camera=()" in h["permissions-policy"]
        assert "frame-ancestors 'none'" in h["content-security-policy"]
        assert "strict-transport-security" not in h  # HTTPS-only header: production only


def test_production_hides_docs_and_enables_hsts() -> None:
    dev, prod = client(), client(app_env="production")
    assert dev.get("/docs").status_code == 200 and dev.get("/api/v1/openapi.json").status_code == 200
    assert "content-security-policy" not in dev.get("/docs").headers  # Swagger UI needs its own scripts
    assert prod.get("/docs").status_code == 404 and prod.get("/api/v1/openapi.json").status_code == 404
    assert "max-age=" in prod.get("/api/v1/health").headers["strict-transport-security"]


def test_oversized_body_is_rejected_before_it_is_read() -> None:
    c = client(max_upload_mb=1)
    res = c.post(
        "/api/v1/farms/1/vision/recognitions",
        content=b"x" * (3 * 1_048_576),
        headers={"content-type": "application/octet-stream"},
    )
    assert res.status_code == 413 and res.json()["error"]["code"] == "payload_too_large"
    small = c.post(
        "/api/v1/farms", json={"name": "x"}
    )  # under the limit: normal handling (401 without a token)
    assert small.status_code == 401


def test_cors_only_allows_configured_origins() -> None:
    c = client()
    ok = c.options(
        "/api/v1/farms", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = c.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_rate_limit_per_caller_with_retry_after() -> None:
    c = client(rate_limit_per_minute=10)
    codes = [c.get("/api/v1/farms", headers={"Authorization": "Bearer a"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    limited = c.get("/api/v1/farms", headers={"Authorization": "Bearer a"})
    assert limited.json()["error"]["code"] == "rate_limited" and int(limited.headers["retry-after"]) >= 1
    assert "x-content-type-options" in limited.headers  # headers wrap the 429 too
    assert (
        c.get("/api/v1/farms", headers={"Authorization": "Bearer b"}).status_code == 401
    )  # another caller is unaffected
    assert c.get("/api/v1/health").status_code == 200  # health checks are never limited


def test_expensive_endpoints_have_a_lower_limit_and_window_slides() -> None:
    now = [1000.0]
    seen: list[int] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(1)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    limiter = RateLimiter(inner, per_minute=100, expensive_per_minute=2, clock=lambda: now[0])

    async def call(method: str, path: str) -> int:
        status: list[int] = []

        async def send(m: Any) -> None:
            if m["type"] == "http.response.start":
                status.append(m["status"])

        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"authorization", b"Bearer t")],
            "client": ("1.2.3.4", 1),
        }
        await limiter(scope, lambda: None, send)  # type: ignore[arg-type,return-value]
        return status[0]

    import asyncio

    expensive = "/api/v1/zones/1/vision/recognitions"
    assert [asyncio.run(call("POST", expensive)) for _ in range(3)] == [200, 200, 429]
    assert asyncio.run(call("GET", "/api/v1/farms")) == 200  # ordinary calls use their own budget
    now[0] += 61
    assert asyncio.run(call("POST", expensive)) == 200  # the window slid forward
    assert len(seen) == 4


@pytest.mark.parametrize("bad", [0, 5, 200_000])
def test_rate_limit_settings_are_bounded(bad: int) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, rate_limit_per_minute=bad)  # type: ignore[call-arg]


def test_weather_values_just_outside_physical_ranges_are_clamped_not_rejected() -> None:
    """Regression: Open-Meteo returned shortwave radiation of -0.1 W/m2 and the database constraint failed the
    whole refresh, so weather silently stopped updating."""
    from app.integrations.open_meteo import parse

    payload = {
        "current": {
            "time": "2026-11-15T17:45",
            "temperature_2m": 24.0,
            "shortwave_radiation": -0.1,
            "relative_humidity_2m": 100.4,
        },
        "hourly": {
            "time": ["2026-11-15T18:00", "2026-11-15T19:00"],
            "shortwave_radiation": [-0.3, 12.5],
            "precipitation": [-0.01, 0.4],
            "wind_direction_10m": [361, 90],
            "temperature_2m": [-3.0, 20.0],  # temperature has no lower bound: can be genuinely negative
        },
    }
    rows = parse(payload)
    assert rows[0].values["shortwave_radiation_wm2"] == 0 and rows[0].values["relative_humidity_pct"] == 100
    assert [r.values["shortwave_radiation_wm2"] for r in rows[1:]] == [0, 12.5]
    assert [r.values["precipitation_mm"] for r in rows[1:]] == [0, 0.4]
    assert rows[1].values["wind_direction_deg"] == 360 and rows[1].values["temperature_c"] == -3.0


def test_jwks_url_defaults_to_issuer_and_can_be_overridden() -> None:
    s = Settings(_env_file=None, supabase_url="http://127.0.0.1:54321")  # type: ignore[call-arg]
    assert s.jwks_url == "http://127.0.0.1:54321/auth/v1/.well-known/jwks.json"
    o = Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_url="http://127.0.0.1:54321",
        supabase_jwks_url="http://host.docker.internal:54321/auth/v1/.well-known/jwks.json",
    )
    assert o.auth_issuer == "http://127.0.0.1:54321/auth/v1"  # issuer still matches the tokens
    assert o.jwks_url.startswith("http://host.docker.internal")  # type: ignore[union-attr]
    assert Settings(_env_file=None).jwks_url is None  # type: ignore[call-arg]
