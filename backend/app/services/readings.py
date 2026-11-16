"""Sensor reading ingestion and retrieval: the ONE write path for every data source.

The HTTP endpoint (future ESP32 over HTTP), the simulator and (later) an MQTT bridge
all call `store()`. It is idempotent: re-sending the same (sensor, timestamp) is
counted as a duplicate and ignored, so devices can safely retry after network failures.
Out-of-range values are stored but flagged `suspect`, never silently dropped.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.errors import UnprocessableError
from app.models import Device, Sensor, SensorReading
from app.schemas.iot import IngestResult, ReadingIn

MAX_CLOCK_SKEW = timedelta(minutes=5)
MAX_WINDOW = timedelta(days=93)
READINGS_EVENT = "readings"


@dataclass(frozen=True)
class StoredReading:
    farm_id: int
    sensor_id: int
    recorded_at: datetime
    value: float
    quality: str
    is_simulated: bool

    def as_event_item(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "recorded_at": self.recorded_at.isoformat(),
            "value": self.value,
            "quality": self.quality,
            "is_simulated": self.is_simulated,
        }


def classify(sensor: Sensor, value: float) -> str:
    if sensor.min_valid is not None and value < sensor.min_valid:
        return "suspect"
    if sensor.max_valid is not None and value > sensor.max_valid:
        return "suspect"
    return "good"


def store(
    db: Session, sensor: Sensor, points: Iterable[tuple[datetime, float]], now: datetime | None = None
) -> list[StoredReading]:
    """Insert points for one sensor (no commit). Returns only the rows actually inserted."""
    unique = dict(points)  # duplicates within one batch: last value wins
    if not unique:
        return []
    rows = [
        {"sensor_id": sensor.id, "recorded_at": ts, "value": v, "quality": classify(sensor, v)}
        for ts, v in unique.items()
    ]
    inserted = db.execute(
        insert(SensorReading)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["sensor_id", "recorded_at"])
        .returning(SensorReading.recorded_at, SensorReading.value, SensorReading.quality)
    ).all()
    if inserted:
        newest = max(r.recorded_at for r in inserted)
        db.execute(
            update(Sensor)
            .where(Sensor.id == sensor.id)
            .values(last_reading_at=func.greatest(func.coalesce(Sensor.last_reading_at, newest), newest))
        )
        if sensor.device_id is not None:
            db.execute(
                update(Device)
                .where(Device.id == sensor.device_id)
                .values(last_seen_at=now or datetime.now(UTC))
            )
    return [
        StoredReading(sensor.farm_id, sensor.id, r.recorded_at, r.value, r.quality, sensor.is_simulated)
        for r in sorted(inserted, key=lambda r: r.recorded_at)
    ]


def events_by_farm(stored: Iterable[StoredReading]) -> dict[int, dict[str, Any]]:
    """Group stored readings into one stream payload per farm."""
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in stored:
        grouped[r.farm_id].append(r.as_event_item())
    return {farm_id: {"farm_id": farm_id, "readings": items} for farm_id, items in grouped.items()}


def ingest(
    db: Session, sensor: Sensor, readings: list[ReadingIn], now: datetime | None = None
) -> tuple[IngestResult, list[StoredReading]]:
    now = now or datetime.now(UTC)
    future = [r.recorded_at.isoformat() for r in readings if r.recorded_at > now + MAX_CLOCK_SKEW]
    if future:
        raise UnprocessableError(
            "Readings cannot be timestamped in the future.", {"recorded_at": future[:10]}
        )
    stored = store(db, sensor, ((r.recorded_at, r.value) for r in readings), now)
    db.commit()
    result = IngestResult(
        received=len(readings),
        inserted=len(stored),
        duplicates=len(readings) - len(stored),
        suspect=sum(1 for r in stored if r.quality == "suspect"),
    )
    return result, stored


def query(
    db: Session, sensor: Sensor, start: datetime | None, end: datetime | None, limit: int
) -> tuple[datetime, datetime, list[SensorReading]]:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(hours=24)
    if start >= end:
        raise UnprocessableError("start must be before end.")
    if end - start > MAX_WINDOW:
        raise UnprocessableError(f"Time window cannot exceed {MAX_WINDOW.days} days.")
    # Most recent `limit` points in the window, returned in chronological order (chart-ready).
    newest_first = db.scalars(
        select(SensorReading)
        .where(SensorReading.sensor_id == sensor.id)
        .where(SensorReading.recorded_at >= start, SensorReading.recorded_at < end)
        .order_by(SensorReading.recorded_at.desc())
        .limit(limit)
    ).all()
    return start, end, list(reversed(newest_first))


def latest_per_sensor(db: Session, farm_id: int) -> dict[int, SensorReading]:
    """Most recent reading of every sensor on a farm (one index-backed query)."""
    rows = db.scalars(
        select(SensorReading)
        .join(Sensor, Sensor.id == SensorReading.sensor_id)
        .where(Sensor.farm_id == farm_id)
        .order_by(SensorReading.sensor_id, SensorReading.recorded_at.desc())
        .distinct(SensorReading.sensor_id)
    ).all()
    return {r.sensor_id: r for r in rows}
