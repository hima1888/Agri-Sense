"""Crop catalogue, crop cycles (a planting in a zone) and individually tracked plants."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdPk, TimestampMixin, between, non_negative, one_of
from app.models.enums import CROP_CATEGORIES, CROP_CYCLE_STATUSES, PLANT_HEALTH


class Crop(TimestampMixin, Base):
    """Reference data: agronomic requirements of a crop species."""

    __tablename__ = "crops"

    id: Mapped[IdPk]
    common_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    scientific_name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    typical_cycle_days: Mapped[int | None] = mapped_column(Integer)
    optimal_ph_min: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    optimal_ph_max: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    optimal_temp_min_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    optimal_temp_max_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    water_requirement_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))

    __table_args__ = (
        one_of("category", CROP_CATEGORIES),
        between("optimal_ph_min", 0, 14),
        between("optimal_ph_max", 0, 14),
        CheckConstraint(
            "optimal_ph_min IS NULL OR optimal_ph_max IS NULL OR optimal_ph_min <= optimal_ph_max",
            name="ph_order",
        ),
        CheckConstraint(
            "optimal_temp_min_c IS NULL OR optimal_temp_max_c IS NULL "
            "OR optimal_temp_min_c <= optimal_temp_max_c",
            name="temp_order",
        ),
        non_negative("typical_cycle_days"),
        non_negative("water_requirement_mm"),
    )


class CropCycle(TimestampMixin, Base):
    """One planting of a crop in a zone, from planting to harvest."""

    __tablename__ = "crop_cycles"

    id: Mapped[IdPk]
    zone_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), nullable=False
    )
    crop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crops.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    variety: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="planned")
    planted_on: Mapped[date | None] = mapped_column(Date)
    expected_harvest_on: Mapped[date | None] = mapped_column(Date)
    harvested_on: Mapped[date | None] = mapped_column(Date)
    area_hectares: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    plant_count: Mapped[int | None] = mapped_column(Integer)
    actual_yield_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Phase 13: the recommended N/P2O5/K2O dose for this cycle (kg/ha) and where it came from,
    # e.g. {"n": 120, "p2o5": 60, "k2o": 40, "source": "TNAU crop production guide 2020"}.
    nutrient_target: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Phase 14: attainable (water-unstressed) yield for this cycle,
    # e.g. {"kg_ha": 6000, "source": "variety trial"}.
    yield_reference: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(None, "zone_id", "status"),
        one_of("status", CROP_CYCLE_STATUSES),
        CheckConstraint(
            "harvested_on IS NULL OR planted_on IS NULL OR harvested_on >= planted_on",
            name="harvest_after_plant",
        ),
        non_negative("area_hectares"),
        non_negative("plant_count"),
        non_negative("actual_yield_kg"),
    )


class Plant(CreatedAtMixin, Base):
    """An individually tracked plant (e.g. an orchard tree or a monitored sample plant)."""

    __tablename__ = "plants"

    id: Mapped[IdPk]
    crop_cycle_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crop_cycles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer)
    position_in_row: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    health_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    planted_on: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        one_of("health_status", PLANT_HEALTH),
        between("latitude", -90, 90),
        between("longitude", -180, 180),
    )
