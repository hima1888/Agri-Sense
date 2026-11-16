"""Model registry, explainable predictions and actionable recommendations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdPk, TimestampMixin, between, one_of
from app.models.enums import (
    MODEL_STATUSES,
    MODEL_TASKS,
    PREDICTION_TYPES,
    PRIORITIES,
    RECOMMENDATION_CATEGORIES,
    RECOMMENDATION_STATUSES,
)


class ModelVersion(TimestampMixin, Base):
    """A trained model artifact (trained in Colab, served with ONNX Runtime)."""

    __tablename__ = "model_versions"

    id: Mapped[IdPk]
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    framework: Mapped[str] = mapped_column(Text, nullable=False, server_default="onnx")
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="staging")
    labels: Mapped[list[str] | None] = mapped_column(JSONB)
    input_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Honest evaluation metrics, e.g. {"accuracy": 0.91, "f1_macro": 0.88, "dataset": "PlantVillage val"}
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    training_dataset: Mapped[str | None] = mapped_column(Text)
    known_limitations: Mapped[str | None] = mapped_column(Text)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("model_name", "version"),
        one_of("task", MODEL_TASKS),
        one_of("status", MODEL_STATUSES),
    )


class AIPrediction(CreatedAtMixin, Base):
    """Every prediction stores what is needed to explain it: value, confidence, factors, limitations."""

    __tablename__ = "ai_predictions"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), index=True
    )
    crop_cycle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("crop_cycles.id", ondelete="SET NULL"), index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("model_versions.id", ondelete="SET NULL"), index=True
    )
    prediction_type: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. {"value": 4200, "unit": "kg/ha", "interval": [3800, 4600]}
    predicted_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    # Ranked contributing factors, e.g. [{"name": "soil_moisture", "impact": -0.32, "detail": "..."}]
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(None, "farm_id", "prediction_type", "created_at"),
        one_of("prediction_type", PREDICTION_TYPES),
        between("confidence", 0, 1),
    )


class AIRecommendation(CreatedAtMixin, Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), index=True
    )
    prediction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_predictions.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default="medium")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    # Phase 11: which rule produced it, and the evidence it used (name, value, unit, source, simulated).
    rule: Mapped[str | None] = mapped_column(Text)
    factors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Machine-readable action, e.g. {"type": "irrigate", "volume_l": 1200, "window": "05:00-07:00"}
    action: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Estimated savings, e.g. {"water_l": 800, "nitrogen_kg": 3.5}
    expected_impact: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    __table_args__ = (
        Index(None, "farm_id", "status"),
        Index(None, "farm_id", "zone_id", "rule", "status"),
        one_of("category", RECOMMENDATION_CATEGORIES),
        one_of("priority", PRIORITIES),
        one_of("status", RECOMMENDATION_STATUSES),
        between("confidence", 0, 1),
    )
