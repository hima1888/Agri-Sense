"""Engine/session management and a real database health check."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


def normalize_database_url(url: str) -> str:
    """Accept the URL exactly as Supabase shows it (postgres:// or postgresql://) and use psycopg 3."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def make_engine(url: str, *, pooled: bool = True) -> Engine:
    connect_args = {
        "connect_timeout": 5,
        # Supabase's transaction pooler (port 6543) cannot use server-side prepared statements.
        "prepare_threshold": None,
    }
    if not pooled:  # one-off work such as migrations
        return create_engine(normalize_database_url(url), poolclass=NullPool, connect_args=connect_args)
    return create_engine(
        normalize_database_url(url),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        connect_args=connect_args,
    )


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if not settings.database_configured:
        raise RuntimeError("DATABASE_URL is not configured")
    return make_engine(settings.database_url)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


@dataclass(frozen=True)
class DatabaseStatus:
    state: Literal["ok", "degraded", "not_configured"]
    detail: str
    revision: str | None = None


def check_database(engine: Engine | None) -> DatabaseStatus:
    """Connect, and verify the schema is migrated to the latest Alembic revision."""
    if engine is None:
        return DatabaseStatus("not_configured", "DATABASE_URL is not set.")
    try:
        with engine.connect() as conn:
            exists = conn.execute(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")).scalar()
            current = (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar() if exists else None
            )
    except SQLAlchemyError as exc:
        # Never echo the exception message: it can contain the connection string.
        return DatabaseStatus("degraded", f"Database unreachable ({type(exc).__name__}).")

    head = head_revision()
    if current is None:
        return DatabaseStatus(
            "degraded", "Connected, but migrations have not been applied (run: alembic upgrade head)."
        )
    if current != head:
        return DatabaseStatus("degraded", f"Connected; schema at {current}, latest is {head}.", current)
    return DatabaseStatus("ok", f"Connected; schema up to date ({current}).", current)
