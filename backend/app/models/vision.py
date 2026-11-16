"""Computer-vision results: what the plant/produce is, and whether it is diseased.

Kept as two tables: recognition (species/organ) and disease diagnosis use different
models, labels and follow-up actions. A disease detection may reference the
recognition result produced from the same image.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdPk, between, one_of
from app.models.enums import DETECTION_SUBJECTS, DISEASE_SEVERITY


class PlantDetection(CreatedAtMixin, Base):
    __tablename__ = "plant_detections"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="SET NULL"), index=True
    )
    plant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plants.id", ondelete="SET NULL"), index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("model_versions.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    image_uri: Mapped[str] = mapped_column(Text, nullable=False)  # Supabase Storage path
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_label: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    # Alternatives, e.g. [{"label": "tomato", "confidence": 0.81}, ...]
    top_k: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Explainability payload: occlusion map, image-quality factors, limitations (Phase 9).
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(None, "farm_id", "detected_at"),
        one_of("subject_type", DETECTION_SUBJECTS),
        between("confidence", 0, 1),
    )


class DiseaseDetection(CreatedAtMixin, Base):
    __tablename__ = "disease_detections"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="SET NULL"), index=True
    )
    plant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plants.id", ondelete="SET NULL"), index=True
    )
    plant_detection_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plant_detections.id", ondelete="SET NULL"), index=True
    )
    model_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("model_versions.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    image_uri: Mapped[str] = mapped_column(Text, nullable=False)
    disease_label: Mapped[str] = mapped_column(Text, nullable=False)
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    affected_area_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    top_k: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Explainability payload: salient regions, key visual cues, limitations.
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(None, "farm_id", "detected_at"),
        one_of("severity", DISEASE_SEVERITY),
        between("confidence", 0, 1),
        between("affected_area_pct", 0, 100),
    )
