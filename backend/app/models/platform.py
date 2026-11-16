"""Alerts, reports, federated learning and audit logging."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdPk, TimestampMixin, non_negative, one_of
from app.models.enums import (
    ALERT_CATEGORIES,
    ALERT_SEVERITIES,
    ALERT_STATUSES,
    FL_CLIENT_STATUSES,
    FL_RUN_STATUSES,
    REPORT_STATUSES,
    REPORT_TYPES,
)


class Alert(CreatedAtMixin, Base):
    __tablename__ = "alerts"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="CASCADE"), index=True
    )
    sensor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sensors.id", ondelete="SET NULL"), index=True
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_recommendations.id", ondelete="SET NULL"), index=True
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(None, "farm_id", "triggered_at"),
        # Small partial index for the hot "open alerts" query.
        Index("ix_alerts_farm_id_open", "farm_id", postgresql_where=text("status = 'open'")),
        one_of("severity", ALERT_SEVERITIES),
        one_of("category", ALERT_CATEGORIES),
        one_of("status", ALERT_STATUSES),
    )


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    file_uri: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(None, "farm_id", "created_at"),
        one_of("report_type", REPORT_TYPES),
        one_of("status", REPORT_STATUSES),
        CheckConstraint("period_end >= period_start", name="period_order"),
    )


class FederatedLearningRun(TimestampMixin, Base):
    """One federated training job (e.g. FedAvg over N rounds) producing a new model version."""

    __tablename__ = "federated_learning_runs"

    id: Mapped[IdPk]
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    base_model_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("model_versions.id", ondelete="SET NULL"), index=True
    )
    result_model_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("model_versions.id", ondelete="SET NULL"), index=True
    )
    aggregation_strategy: Mapped[str] = mapped_column(Text, nullable=False, server_default="fedavg")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        one_of("status", FL_RUN_STATUSES),
        CheckConstraint("total_rounds > 0", name="total_rounds_positive"),
        CheckConstraint("current_round >= 0 AND current_round <= total_rounds", name="current_round_range"),
    )


class FederatedClient(TimestampMixin, Base):
    """A farm enrolled as a federated-learning participant. Raw farm data never leaves the client."""

    __tablename__ = "federated_clients"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    client_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (one_of("status", FL_CLIENT_STATUSES),)


class FederatedClientUpdate(CreatedAtMixin, Base):
    """A client's contribution to one round of a run (model delta + local metrics, never raw data).
    Junction between runs and clients; needed because participation is many-to-many per round."""

    __tablename__ = "federated_client_updates"

    id: Mapped[IdPk]
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("federated_learning_runs.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("federated_clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    num_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    update_uri: Mapped[str | None] = mapped_column(Text)
    local_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("run_id", "round_number", "client_id"),
        CheckConstraint("round_number > 0", name="round_number_positive"),
        non_negative("num_samples"),
    )


class AuditLog(Base):
    """Append-only record of who changed what."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    farm_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. "sensor.create"
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index(None, "entity_type", "entity_id"), Index(None, "created_at"))
