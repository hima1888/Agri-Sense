"""Weather observations and forecasts per farm (Open-Meteo in Phase 6)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Numeric, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, between, non_negative, one_of
from app.models.enums import WEATHER_KINDS


class WeatherData(Base):
    __tablename__ = "weather_data"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    farm_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="open-meteo")
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    relative_humidity_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    precipitation_probability_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    wind_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    wind_direction_deg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    cloud_cover_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    shortwave_radiation_wm2: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    et0_mm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # reference evapotranspiration
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Upsert key for refreshing forecasts; leading farm_id covers the FK.
        UniqueConstraint("farm_id", "kind", "source", "valid_at"),
        one_of("kind", WEATHER_KINDS),
        between("relative_humidity_pct", 0, 100),
        between("precipitation_probability_pct", 0, 100),
        between("cloud_cover_pct", 0, 100),
        between("wind_direction_deg", 0, 360),
        non_negative("precipitation_mm"),
        non_negative("wind_speed_ms"),
        non_negative("shortwave_radiation_wm2"),
        non_negative("et0_mm"),
    )
