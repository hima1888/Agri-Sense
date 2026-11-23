"""Coverage gaps found in Phase 18: background runners, command-line tools, system status and JWKS errors.

Runners and CLIs normally open their own database sessions; here they get the test's session (wrapped so
they cannot close it), so everything still rolls back after each test.
"""

import asyncio
import contextlib
import hashlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints import system
from app.cli import fetch_models, seed, users
from app.core.config import Settings
from app.core.security import TokenError
from app.models import Crop, Farm, Sensor, SensorReading, User
from app.realtime.broadcaster import Broadcaster
from app.services.alert_runner import AlertRunner
from app.simulator.runner import SimulatorRunner
from tests.api.helpers import V1, ok
from tests.conftest import make_verifier


def shared(db: Session) -> Any:
    """A session factory handing out the test session without closing it."""
    return lambda: contextlib.nullcontext(db)


# --- background runners ---------------------------------------------------------------------
def simulated_zone(api: TestClient) -> dict[str, Any]:
    farm = ok(
        api.post(
            f"{V1}/farms",
            json={"name": "Runner Farm", "timezone": "UTC", "latitude": 17.4, "longitude": 78.5},
        ),
        201,
    )
    zone = ok(api.post(f"{V1}/farms/{farm['id']}/zones", json={"name": "Z", "zone_type": "field"}), 201)
    ok(api.post(f"{V1}/zones/{zone['id']}/simulator/provision", json={}), 201)
    return {"farm_id": farm["id"], "zone_id": zone["id"]}


def test_simulator_tick_stores_readings_and_reports_status(api: TestClient, db: Session) -> None:
    z = simulated_zone(api)
    runner = SimulatorRunner(shared(db), Broadcaster(), interval_seconds=60)
    before = db.scalar(select(func.count()).select_from(SensorReading)) or 0
    payloads = runner.tick_once(datetime.now(UTC))
    assert z["farm_id"] in payloads and runner.ticks == 1 and runner.last_tick_readings > 0
    assert (db.scalar(select(func.count()).select_from(SensorReading)) or 0) > before
    st = runner.status()
    assert st["running"] is False and st["last_tick_readings"] == runner.last_tick_readings


def test_simulator_fills_the_gap_left_while_the_server_slept(api: TestClient, db: Session) -> None:
    z = simulated_zone(api)
    runner = SimulatorRunner(shared(db), Broadcaster(), interval_seconds=60)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    runner.tick_once(now - timedelta(hours=3))  # last reading, then the server "slept" for 3 h

    def count() -> int:
        q = select(func.count()).select_from(SensorReading).join(Sensor)
        return db.scalar(q.where(Sensor.farm_id == z["farm_id"])) or 0

    sensors = count()  # one reading per sensor so far
    assert sensors > 0
    assert runner.fill_gaps(now) >= 17 * sensors  # 10-minute steps across the 3 h gap
    assert count() >= 18 * sensors
    assert runner.fill_gaps(now) == 0  # nothing left to fill


def test_alert_runner_evaluates_each_farm_and_loop_starts_and_stops(api: TestClient, db: Session) -> None:
    farm = ok(api.post(f"{V1}/farms", json={"name": "Dry Farm", "timezone": "UTC"}), 201)
    zone = ok(api.post(f"{V1}/farms/{farm['id']}/zones", json={"name": "Z", "zone_type": "field"}), 201)
    ok(
        api.post(
            f"{V1}/zones/{zone['id']}/soil-measurements",
            json={"measured_at": datetime.now(UTC).isoformat(), "source": "field_kit", "moisture_pct": 15},
        ),
        201,
    )
    runner = AlertRunner(shared(db), Broadcaster(), interval_seconds=300)
    published = dict(runner.run_once())
    assert published[farm["id"]][0]["type"] == "raised" and runner.runs == 1
    assert runner.run_once() and runner.runs == 2  # second pass: no duplicate raised
    assert all(not events for fid, events in runner.run_once() if fid == farm["id"])

    async def run_loop() -> None:
        loop_runner = AlertRunner(shared(db), Broadcaster(), interval_seconds=300)
        loop_runner.start()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if loop_runner.runs:
                break
        await loop_runner.stop()
        assert loop_runner.runs >= 1 and loop_runner.last_error is None

    asyncio.run(run_loop())


# --- command-line tools -----------------------------------------------------------------------
def test_users_cli_lists_and_sets_roles(
    api: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ok(api.get(f"{V1}/me"))  # creates owner@example.com's profile
    monkeypatch.setattr(users, "get_sessionmaker", lambda: shared(db))
    monkeypatch.setattr(sys, "argv", ["users", "list"])
    assert users.main() == 0 and "owner@example.com" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["users", "set-role", "OWNER@example.com", "admin"])
    assert users.main() == 0
    assert db.scalar(select(User.role).where(User.email == "owner@example.com")) == "admin"
    monkeypatch.setattr(sys, "argv", ["users", "set-role", "nobody@example.com", "admin"])
    assert users.main() == 1 and "sign in once" in capsys.readouterr().err


def test_seed_cli_is_idempotent_and_creates_demo(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: shared(db))
    monkeypatch.setattr(sys, "argv", ["seed", "--demo"])
    seed.main()
    crops = db.scalar(select(func.count()).select_from(Crop))
    assert crops == len(seed.CROPS) and "demo farm" in capsys.readouterr().out
    seed.main()  # second run: nothing new
    assert db.scalar(select(func.count()).select_from(Crop)) == crops
    assert (db.scalar(select(func.count()).select_from(Farm)) or 0) >= 1


def test_fetch_models_verifies_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model, labels = tmp_path / "m.onnx", tmp_path / "s.txt"
    monkeypatch.setattr(fetch_models, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(fetch_models, "MODEL_FILE", model)
    monkeypatch.setattr(fetch_models, "LABEL_FILE", labels)
    monkeypatch.setattr(
        fetch_models.urllib.request, "urlretrieve", lambda url, path: Path(path).write_bytes(b"weights")
    )
    monkeypatch.setattr(fetch_models, "MODEL_SHA256", hashlib.sha256(b"weights").hexdigest())
    assert fetch_models.main() == 0 and model.exists() and labels.exists()
    assert fetch_models.main() == 0  # already present: no download
    monkeypatch.setattr(fetch_models, "MODEL_SHA256", "0" * 64)
    assert fetch_models.main() == 1 and not model.exists()  # tampered file removed


# --- system status and token verification --------------------------------------------------------
class FakeResponse:
    def __init__(self, keys: list[dict[str, Any]] | None, fail: bool = False) -> None:
        self.keys, self.fail = keys, fail

    def raise_for_status(self) -> None:
        if self.fail:
            raise httpx.HTTPStatusError(
                "boom", request=httpx.Request("GET", "http://x"), response=httpx.Response(500)
            )

    def json(self) -> dict[str, Any]:
        return {"keys": self.keys or []}


def test_auth_status_reports_each_state(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SUPABASE_URL", "SUPABASE_JWKS_URL", "SUPABASE_JWT_SECRET"):  # CI sets SUPABASE_URL globally
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None, supabase_url="http://auth.local")  # type: ignore[call-arg]
    monkeypatch.setattr(system.httpx, "get", lambda *a, **k: FakeResponse([{"kid": "k"}]))
    assert system.auth_status(s) == ("ok", "Supabase Auth reachable; 1 signing key(s).")
    monkeypatch.setattr(system.httpx, "get", lambda *a, **k: FakeResponse([]))
    assert system.auth_status(s)[0] == "degraded"
    monkeypatch.setattr(system.httpx, "get", lambda *a, **k: FakeResponse(None, fail=True))
    assert "unreachable" in system.auth_status(s)[1]
    assert system.auth_status(Settings(_env_file=None, supabase_jwt_secret="x"))[0] == "ok"  # type: ignore[call-arg]
    assert system.auth_status(Settings(_env_file=None))[0] == "not_configured"  # type: ignore[call-arg]


def test_simulator_service_states() -> None:
    off = Settings(_env_file=None, simulator_enabled=False)  # type: ignore[call-arg]
    assert system.simulator_service(off, None).state == "not_configured"

    class FakeRunner:
        def __init__(self, **st: Any) -> None:
            self.st = {
                "running": True,
                "interval_seconds": 10,
                "last_tick_readings": 24,
                "last_error": None,
                **st,
            }

        def status(self) -> dict[str, Any]:
            return self.st

    on = Settings(_env_file=None)  # type: ignore[call-arg]
    assert system.simulator_service(on, FakeRunner()).state == "ok"  # type: ignore[arg-type]
    assert system.simulator_service(on, FakeRunner(last_error="OperationalError")).state == "degraded"  # type: ignore[arg-type]
    assert system.simulator_service(on, FakeRunner(running=False)).state == "degraded"  # type: ignore[arg-type]


def test_jwks_failure_without_cached_keys_rejects_tokens() -> None:
    def broken() -> dict[str, Any]:
        raise httpx.ConnectError("down")

    verifier = make_verifier(jwks_fetcher=broken)
    with pytest.raises(TokenError, match="Unable to load token signing keys"):
        verifier._key_for("some-kid")
