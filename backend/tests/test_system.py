from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.config import Settings
from app.db.session import make_engine, normalize_database_url

ClientFactory = Callable[..., TestClient]


def services(client: TestClient) -> dict[str, dict[str, str]]:
    body = client.get("/api/v1/system/info").json()
    return {s["key"]: s for s in body["services"]}


def test_health_ok(make_client: ClientFactory) -> None:
    res = make_client().get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "agri-sense-api"
    assert body["version"] == "1.0.0"
    assert "timestamp" in body


def test_system_info_without_database(make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SUPABASE_URL", "SUPABASE_JWKS_URL", "SUPABASE_JWT_SECRET"):  # CI sets SUPABASE_URL globally
        monkeypatch.delenv(var, raising=False)
    client = make_client()
    body = client.get("/api/v1/system/info").json()
    assert body["name"] == "AGRI-SENSE"
    assert body["data_mode"]["sensors"] == "none"
    svc = services(client)
    assert svc["api"]["state"] == "ok"
    assert svc["database"]["state"] == "not_configured"
    assert svc["auth"]["state"] == "not_configured"


def test_system_info_with_migrated_database(make_client: ClientFactory, engine: Engine) -> None:
    db = services(make_client(engine=engine))["database"]
    assert db["state"] == "ok"
    assert "up to date" in db["detail"]


def test_system_info_unreachable_database_does_not_leak_credentials(make_client: ClientFactory) -> None:
    bad = make_engine("postgresql://user:SECRET_PW@127.0.0.1:1/nope")
    db = services(make_client(engine=bad))["database"]
    assert db["state"] == "degraded"
    assert "unreachable" in db["detail"].lower()
    assert "SECRET_PW" not in db["detail"]


def test_database_url_normalization() -> None:
    assert normalize_database_url("postgres://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert normalize_database_url("postgresql://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert normalize_database_url("postgresql+psycopg://u@h/d") == "postgresql+psycopg://u@h/d"


def test_cors_allows_frontend_origin(make_client: ClientFactory) -> None:
    res = make_client().options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_origins_parsed_from_comma_string() -> None:
    s = Settings(_env_file=None, cors_origins="https://a.app/, https://b.app")
    assert s.cors_origins == ["https://a.app", "https://b.app"]


def test_unknown_route_is_404(make_client: ClientFactory) -> None:
    assert make_client().get("/api/v1/does-not-exist").status_code == 404


def test_openapi_served_under_prefix(make_client: ClientFactory) -> None:
    res = make_client().get("/api/v1/openapi.json")
    assert res.status_code == 200
    assert "/api/v1/health" in res.json()["paths"]


def test_inference_status_reports_installed_models(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.v1.endpoints.system import inference_status
    from app.vision import disease, recognizer

    monkeypatch.setattr(recognizer, "model_available", lambda: True)
    monkeypatch.setattr(disease, "model_available", lambda m: False)
    s = inference_status()
    assert s.state == "degraded" and s.detail.startswith("1 of 4 models installed")
    monkeypatch.setattr(recognizer, "model_available", lambda: False)
    assert inference_status().state == "not_configured"
    monkeypatch.setattr(recognizer, "model_available", lambda: True)
    monkeypatch.setattr(disease, "model_available", lambda m: True)
    assert inference_status().state == "ok"
