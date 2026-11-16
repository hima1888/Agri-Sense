"""IoT: devices (ESP32, gateway, simulator), the sensors attached to them, and their readings.

A device can carry several sensors (an ESP32 + DHT22 = temperature AND humidity),
so devices and sensors are separate tables. Every sensor records whether its data
is `simulated` or from `hardware`, so simulated data can always be labelled.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdPk, TimestampMixin, between, one_of
from app.models.enums import (
    DATA_SOURCES,
    DEVICE_STATUSES,
    DEVICE_TYPES,
    PROTOCOLS,
    READING_QUALITY,
    SENSOR_TYPES,
)


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    device_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    protocol: Mapped[str] = mapped_column(Text, nullable=False)
    # Hardware identifier (e.g. ESP32 MAC / chip id). Unique when present.
    hardware_id: Mapped[str | None] = mapped_column(Text, unique=True)
    firmware_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        one_of("device_type", DEVICE_TYPES),
        one_of("source", DATA_SOURCES),
        one_of("protocol", PROTOCOLS),
        one_of("status", DEVICE_STATUSES),
        # A simulator device can never claim to be hardware, and vice versa.
        CheckConstraint(
            "(device_type = 'simulator') = (source = 'simulated')", name="simulator_source_consistent"
        ),
    )


class Sensor(TimestampMixin, Base):
    __tablename__ = "sensors"

    id: Mapped[IdPk]
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("farm_zones.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sensor_type: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    hardware_model: Mapped[str | None] = mapped_column(Text)  # e.g. DHT22, capacitive v1.2
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    # Physically plausible range; readings outside it are marked suspect at ingestion.
    min_valid: Mapped[float | None] = mapped_column(Double)
    max_valid: Mapped[float | None] = mapped_column(Double)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    # Position in the 3D digital twin's local coordinate system: {"x":..,"y":..,"z":..}
    twin_position: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_simulated(self) -> bool:
        return self.source == "simulated"

    __table_args__ = (
        one_of("sensor_type", SENSOR_TYPES),
        one_of("source", DATA_SOURCES),
        one_of("status", DEVICE_STATUSES),
        CheckConstraint(
            "min_valid IS NULL OR max_valid IS NULL OR min_valid < max_valid", name="valid_range_order"
        ),
        between("latitude", -90, 90),
        between("longitude", -180, 180),
    )


class SensorReading(Base):
    """High-volume time series. bigint identity PK; (sensor_id, recorded_at) is unique so
    re-sent device batches are idempotent (ON CONFLICT DO NOTHING).
    Range partitioning by month can be added once volume warrants it."""

    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    sensor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Double, nullable=False)
    quality: Mapped[str] = mapped_column(Text, nullable=False, server_default="good")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("sensor_id", "recorded_at"),
        one_of("quality", READING_QUALITY),
        # Cheap index for time-window scans across all sensors (e.g. retention jobs).
        Index("ix_sensor_readings_recorded_at_brin", "recorded_at", postgresql_using="brin"),
    )
