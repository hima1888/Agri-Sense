"""Shared fixtures. Database tests run against a REAL Postgres (docker compose `db` service),
in a dedicated `agrisense_test` database, never against dev or production data.

Auth: the suite generates its own ES256 key pair and verifies tokens through the
production TokenVerifier (JWKS path), so every rejection rule is exercised for real.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.auth import get_verifier
from app.api.v1.endpoints.system import get_optional_engine
from app.core.config import Settings, get_settings
from app.core.security import TokenVerifier
from app.db.session import alembic_config, get_db, make_engine
from app.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://agrisense:agrisense_local_dev@127.0.0.1:54329/agrisense_test",
)
TEST_ISSUER = "http://auth.test.invalid/auth/v1"
TEST_KID = "test-key-1"

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_JWK: dict[str, Any] = {
    **json.loads(ECAlgorithm.to_jwk(_PRIVATE_KEY.public_key())),
    "kid": TEST_KID,
    "alg": "ES256",
    "use": "sig",
}


def migration_config() -> Config:
    cfg = alembic_config()
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    cfg.attributes["configure_logger"] = False
    return cfg


def make_token(
    user_id: uuid.UUID | str,
    email: str | None = "owner@example.com",
    *,
    key: Any = None,
    kid: str = TEST_KID,
    alg: str = "ES256",
    expires_in: int = 3600,
    **claims: Any,
) -> str:
    now = int(time.time())
    payload = {
        "iss": TEST_ISSUER,
        "aud": "authenticated",
        "sub": str(user_id),
        "email": email,
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
        "session_id": "test-session",
        **claims,
    }
    return jwt.encode(payload, key or _PRIVATE_KEY, algorithm=alg, headers={"kid": kid})


def make_verifier(**overrides: Any) -> TokenVerifier:
    options: dict[str, Any] = {"issuer": TEST_ISSUER, "jwks_fetcher": lambda: {"keys": [_PUBLIC_JWK]}}
    return TokenVerifier(**{**options, **overrides})


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = make_engine(TEST_DATABASE_URL)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Test Postgres not reachable. Start it with: docker compose up -d")
    cfg = migration_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Each test runs inside a transaction that is rolled back, so tests never leak data."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def make_client() -> Callable[..., TestClient]:
    """Client for unauthenticated system endpoints, with an injectable DB engine."""

    def _make(database_url: str = "", engine: Engine | None = None) -> TestClient:
        settings = Settings(_env_file=None, database_url=database_url)
        app = create_app(settings)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_optional_engine] = lambda: engine
        return TestClient(app)

    return _make


ClientFor = Callable[..., TestClient]


@pytest.fixture
def client_for(db: Session) -> Iterator[ClientFor]:
    """Build API clients signed in as different users, all sharing the per-test transaction."""
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        supabase_url="http://auth.test.invalid",
        simulator_enabled=False,  # tests drive the simulator explicitly
        alerts_enabled=False,  # tests evaluate alerts explicitly
        rate_limit_enabled=False,  # the limiter has its own tests
    )
    app = create_app(settings)
    verifier = make_verifier()

    def _db() -> Iterator[Session]:
        try:
            yield db
        finally:
            # Clear a failed state (e.g. after an IntegrityError) so the next request can proceed.
            db.rollback()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_verifier] = lambda: verifier
    clients: list[TestClient] = []

    def _for(email: str | None = "owner@example.com", *, token: str | None = None) -> TestClient:
        client = TestClient(app)
        if token is None and email is not None:
            token = make_token(uuid.uuid5(uuid.NAMESPACE_URL, email), email)
        if token is not None:
            client.headers["Authorization"] = f"Bearer {token}"
        clients.append(client)
        return client

    yield _for
    for c in clients:
        c.close()


@pytest.fixture
def api(client_for: ClientFor) -> TestClient:
    """Signed in as owner@example.com (a farmer)."""
    return client_for("owner@example.com")


@pytest.fixture
def admin(client_for: ClientFor, db: Session) -> TestClient:
    """Signed in as admin@example.com, promoted to admin the same way the CLI does it."""
    from sqlalchemy import update

    from app.models import User

    client = client_for("admin@example.com")
    assert client.get("/api/v1/me").status_code == 200  # first sign-in creates the profile
    db.execute(update(User).where(User.email == "admin@example.com").values(role="admin"))
    db.commit()
    db.expire_all()
    return client
