"""Field operations: irrigation, fertilizer and pesticide applications.

Three tables rather than one generic "application" table: each has different
quantities, units, regulation (pre-harvest intervals) and sustainability metrics.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdPk, between, non_negative, one_of
from app.models.enums import (
    FERTILIZER_METHODS,
    IRRIGATION_METHODS,
    IRRIGATION_STATUSES,
    IRRIGATION_TRIGGERS,
    PESTICIDE_TYPES,
    QUANTITY_UNITS,
)


class IrrigationEvent(CreatedAtMixin, Base):
    __tablename__ = "irrigation_events"

    id: Mapped[IdPk]
    zone_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_recommendations.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    method: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="scheduled")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    volume_liters: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(None, "zone_id", "started_at"),
        one_of("method", IRRIGATION_METHODS),
        one_of("trigger", IRRIGATION_TRIGGERS),
        one_of("status", IRRIGATION_STATUSES),
        CheckConstraint(
            "ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at", name="end_after_start"
        ),
        non_negative("volume_liters"),
    )


class FertilizerApplication(CreatedAtMixin, Base):
    __tablename__ = "fertilizer_applications"

    id: Mapped[IdPk]
    zone_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), nullable=False
    )
    crop_cycle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("crop_cycles.id", ondelete="SET NULL"), index=True
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_recommendations.id", ondelete="SET NULL"), index=True
    )
    applied_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_organic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Nutrient analysis of the product (N-P-K %), so applied nutrient mass can be derived.
    n_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    p_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    k_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(None, "zone_id", "applied_at"),
        one_of("method", FERTILIZER_METHODS),
        between("n_pct", 0, 100),
        between("p_pct", 0, 100),
        between("k_pct", 0, 100),
        non_negative("quantity_kg"),
    )


class PesticideApplication(CreatedAtMixin, Base):
    __tablename__ = "pesticide_applications"

    id: Mapped[IdPk]
    zone_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), nullable=False
    )
    crop_cycle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("crop_cycles.id", ondelete="SET NULL"), index=True
    )
    disease_detection_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("disease_detections.id", ondelete="SET NULL"), index=True
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_recommendations.id", ondelete="SET NULL"), index=True
    )
    applied_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    active_ingredient: Mapped[str | None] = mapped_column(Text)
    pesticide_type: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str | None] = mapped_column(Text)  # pest / disease / weed targeted
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(Text, nullable=False)
    pre_harvest_interval_days: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(None, "zone_id", "applied_at"),
        one_of("pesticide_type", PESTICIDE_TYPES),
        one_of("quantity_unit", QUANTITY_UNITS),
        non_negative("quantity"),
        non_negative("pre_harvest_interval_days"),
    )
