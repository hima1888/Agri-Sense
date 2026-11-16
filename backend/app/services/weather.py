"""Farm weather: fetch from Open-Meteo, store in weather_data, serve from the database.

The database is the source of truth the dashboard reads. A refresh happens when the
newest stored fetch is older than MAX_AGE; if Open-Meteo is down, the last stored
forecast is served and marked stale, never silently replaced by made-up values.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.errors import UnprocessableError
from app.integrations.open_meteo import (
    ATTRIBUTION,
    FIELD_MAP,
    SOURCE,
    OpenMeteoClient,
    WeatherUnavailableError,
)
from app.models import Farm, WeatherData

MAX_AGE = timedelta(minutes=30)
HOURLY_HORIZON = timedelta(hours=48)


@lru_cache
def default_client() -> OpenMeteoClient:
    return OpenMeteoClient()


def last_fetched_at(db: Session, farm_id: int) -> datetime | None:
    return db.scalar(
        select(func.max(WeatherData.fetched_at)).where(
            WeatherData.farm_id == farm_id, WeatherData.source == SOURCE
        )
    )


def refresh(db: Session, farm: Farm, client: OpenMeteoClient, now: datetime | None = None) -> int:
    """Fetch and upsert. Returns rows written. Raises WeatherUnavailableError on failure."""
    if farm.latitude is None or farm.longitude is None:
        raise UnprocessableError(
            "Set the farm's latitude and longitude to get weather.", {"field": "latitude"}
        )
    rows = client.forecast(float(farm.latitude), float(farm.longitude))
    now = now or datetime.now(UTC)
    # Every row carries every column: a multi-row INSERT takes its column list from the first
    # row, and the "current" observation lacks forecast-only fields such as ET0.
    columns = dict.fromkeys(FIELD_MAP.values())
    payload = [
        {
            "farm_id": farm.id,
            "kind": r.kind,
            "source": SOURCE,
            "valid_at": r.valid_at,
            "fetched_at": now,
            **columns,
            **r.values,
        }
        for r in rows
    ]
    if not payload:
        return 0
    stmt = insert(WeatherData).values(payload)
    update_cols = {
        c: stmt.excluded[c] for c in payload[0] if c not in ("farm_id", "kind", "source", "valid_at")
    }
    db.execute(
        stmt.on_conflict_do_update(index_elements=["farm_id", "kind", "source", "valid_at"], set_=update_cols)
    )
    db.commit()
    return len(payload)


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def _row_dict(w: WeatherData) -> dict[str, Any]:
    return {
        "valid_at": w.valid_at,
        "temperature_c": _f(w.temperature_c),
        "relative_humidity_pct": _f(w.relative_humidity_pct),
        "precipitation_mm": _f(w.precipitation_mm),
        "precipitation_probability_pct": _f(w.precipitation_probability_pct),
        "wind_speed_ms": _f(w.wind_speed_ms),
        "wind_direction_deg": _f(w.wind_direction_deg),
        "cloud_cover_pct": _f(w.cloud_cover_pct),
        "shortwave_radiation_wm2": _f(w.shortwave_radiation_wm2),
        "et0_mm": _f(w.et0_mm),
    }


def daily_summary(hourly: list[WeatherData], tz: ZoneInfo) -> list[dict[str, Any]]:
    """Aggregate hourly forecast rows into local calendar days (complete days only)."""
    by_day: dict[date, list[WeatherData]] = defaultdict(list)
    for w in hourly:
        by_day[w.valid_at.astimezone(tz).date()].append(w)
    out = []
    for day, rows in sorted(by_day.items()):
        if len(rows) < 20:  # partial day at either end of the forecast window
            continue
        temps = [float(r.temperature_c) for r in rows if r.temperature_c is not None]
        probs = [
            float(r.precipitation_probability_pct)
            for r in rows
            if r.precipitation_probability_pct is not None
        ]
        out.append(
            {
                "date": day,
                "temp_min_c": min(temps) if temps else None,
                "temp_max_c": max(temps) if temps else None,
                "precipitation_mm": round(sum(float(r.precipitation_mm or 0) for r in rows), 1),
                "precipitation_probability_max_pct": max(probs) if probs else None,
                "et0_mm": round(sum(float(r.et0_mm or 0) for r in rows), 2),
            }
        )
    return out


def farm_weather(
    db: Session,
    farm: Farm,
    client: OpenMeteoClient | None = None,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    error: str | None = None
    fetched = last_fetched_at(db, farm.id)
    if force or fetched is None or now - fetched > MAX_AGE:
        try:
            refresh(db, farm, client or default_client(), now)
            fetched = now
        except WeatherUnavailableError as exc:
            error = str(exc)

    tz = ZoneInfo(farm.timezone)
    base = select(WeatherData).where(WeatherData.farm_id == farm.id, WeatherData.source == SOURCE)
    current = db.scalars(
        base.where(WeatherData.kind == "observation").order_by(WeatherData.valid_at.desc()).limit(1)
    ).first()
    local_midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    forecast = list(
        db.scalars(
            base.where(WeatherData.kind == "forecast", WeatherData.valid_at >= local_midnight.astimezone(UTC))
            .order_by(WeatherData.valid_at)
            .limit(24 * 8)
        )
    )
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    hourly = [w for w in forecast if hour_start <= w.valid_at < hour_start + HOURLY_HORIZON]
    return {
        "farm_id": farm.id,
        "source": SOURCE,
        "attribution": ATTRIBUTION,
        "timezone": farm.timezone,
        "fetched_at": fetched,
        "stale": fetched is None or now - fetched > MAX_AGE,
        "error": error,
        "current": _row_dict(current) if current else None,
        "hourly": [_row_dict(w) for w in hourly],
        "daily": [d for d in daily_summary(forecast, tz) if d["date"] >= now.astimezone(tz).date()],
    }
