"""Users, farms and zones."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdPk, TimestampMixin, between, non_negative, one_of
from app.models.enums import IRRIGATION_METHODS, USER_ROLES, ZONE_TYPES


class User(TimestampMixin, Base):
    """Application profile. `id` equals the Supabase Auth user id (auth.users.id).

    No cross-schema FK to auth.users so the schema also runs on plain Postgres
    (local dev / CI); Phase 4 keeps the two in sync at sign-up.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="farmer")

    farms: Mapped[list[Farm]] = relationship(back_populates="owner", passive_deletes=True)

    __table_args__ = (
        one_of("role", USER_ROLES),
        # Case-insensitive uniqueness without the citext extension.
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
    )


class Farm(TimestampMixin, Base):
    __tablename__ = "farms"

    id: Mapped[IdPk]
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    area_hectares: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    # Phase 17: {"disabled_rules": [...], "thresholds": {"heat_c": 38, ...}} for automatic alerts.
    alert_settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    owner: Mapped[User] = relationship(back_populates="farms")
    zones: Mapped[list[FarmZone]] = relationship(back_populates="farm", passive_deletes=True)

    __table_args__ = (
        between("latitude", -90, 90),
        between("longitude", -180, 180),
        non_negative("area_hectares"),
    )


class FarmZone(TimestampMixin, Base):
    """A management unit within a farm (field block, greenhouse, orchard...)."""

    __tablename__ = "farm_zones"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    zone_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="field")
    area_hectares: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    irrigation_method: Mapped[str | None] = mapped_column(Text)
    # GeoJSON polygon; also drives zone placement in the 3D digital twin.
    boundary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    farm: Mapped[Farm] = relationship(back_populates="zones")

    __table_args__ = (
        # Leading farm_id also serves as the FK index.
        UniqueConstraint("farm_id", "name"),
        one_of("zone_type", ZONE_TYPES),
        one_of("irrigation_method", IRRIGATION_METHODS),
        non_negative("area_hectares"),
    )
