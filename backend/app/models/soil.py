"""Soil: slow-changing characterisation (profiles) vs. point-in-time chemistry (measurements)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdPk, TimestampMixin, between, non_negative, one_of
from app.models.enums import SOIL_MEASUREMENT_SOURCES, SOIL_TEXTURES


class SoilProfile(TimestampMixin, Base):
    """Physical soil properties of a zone (texture, water-holding capacity). Changes over years."""

    __tablename__ = "soil_profiles"

    id: Mapped[IdPk]
    zone_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    texture: Mapped[str | None] = mapped_column(Text)
    sand_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    silt_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    clay_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    organic_matter_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    bulk_density_g_cm3: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    field_capacity_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    wilting_point_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    depth_cm: Mapped[int | None] = mapped_column()
    surveyed_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        one_of("texture", SOIL_TEXTURES),
        between("sand_pct", 0, 100),
        between("silt_pct", 0, 100),
        between("clay_pct", 0, 100),
        between("organic_matter_pct", 0, 100),
        between("field_capacity_pct", 0, 100),
        between("wilting_point_pct", 0, 100),
        non_negative("bulk_density_g_cm3"),
    )


class SoilMeasurement(CreatedAtMixin, Base):
    """A soil test result (lab, field kit or aggregated from sensors) at a point in time."""

    __tablename__ = "soil_measurements"

    id: Mapped[IdPk]
    zone_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), nullable=False
    )
    soil_profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("soil_profiles.id", ondelete="SET NULL"), index=True
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    depth_cm: Mapped[int | None] = mapped_column()
    ph: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    nitrogen_mg_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    phosphorus_mg_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    potassium_mg_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    organic_carbon_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    electrical_conductivity_ds_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    moisture_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # Zone history queries (btree is scanned backwards for newest-first). Leading zone_id covers the FK.
        Index(None, "zone_id", "measured_at"),
        one_of("source", SOIL_MEASUREMENT_SOURCES),
        between("ph", 0, 14),
        non_negative("nitrogen_mg_kg"),
        non_negative("phosphorus_mg_kg"),
        non_negative("potassium_mg_kg"),
        between("organic_carbon_pct", 0, 100),
        non_negative("electrical_conductivity_ds_m"),
        between("moisture_pct", 0, 100),
    )
