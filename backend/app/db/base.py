"""Declarative base, naming conventions and shared column types."""

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep Alembic autogenerate diffs stable and
# make constraint errors readable (e.g. ck_sensors_sensor_type_valid).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# bigint identity is the recommended PK for single-database tables
# (sequential, compact, no index fragmentation like random UUIDv4).
IdPk = Annotated[int, mapped_column(BigInteger, Identity(always=True), primary_key=True)]


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Kept current by the ORM and by a DB trigger (see initial migration),
    # so edits made outside the API (e.g. Supabase dashboard) also update it.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def one_of(column: str, values: Sequence[str]) -> CheckConstraint:
    """text + CHECK instead of native enums: same safety, far easier to evolve in migrations."""
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_valid")


def between(column: str, low: float, high: float, *, name: str | None = None) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IS NULL OR ({column} >= {low} AND {column} <= {high})", name=name or f"{column}_range"
    )


def non_negative(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IS NULL OR {column} >= 0", name=f"{column}_non_negative")
