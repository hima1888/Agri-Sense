"""Open-Meteo forecast client (https://open-meteo.com, free, no API key).

Data is CC BY 4.0 and must be attributed ("Weather data by Open-Meteo.com").
Only the farm's coordinates are sent; no user or farm identifiers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)
RETRIES = 3
BACKOFF_S = 1.0

BASE_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

CURRENT_VARS = (
    "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,"
    "wind_direction_10m,cloud_cover,shortwave_radiation"
)
HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,wind_speed_10m,"
    "wind_direction_10m,cloud_cover,shortwave_radiation,et0_fao_evapotranspiration"
)

# Open-Meteo field -> weather_data column
FIELD_MAP = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "relative_humidity_pct",
    "precipitation": "precipitation_mm",
    "precipitation_probability": "precipitation_probability_pct",
    "wind_speed_10m": "wind_speed_ms",
    "wind_direction_10m": "wind_direction_deg",
    "cloud_cover": "cloud_cover_pct",
    "shortwave_radiation": "shortwave_radiation_wm2",
    "et0_fao_evapotranspiration": "et0_mm",
}


class WeatherUnavailableError(Exception):
    """Open-Meteo could not be reached or returned something unusable."""


@dataclass(frozen=True)
class WeatherRow:
    kind: str  # "observation" | "forecast"
    valid_at: datetime
    values: dict[str, float | None]


# Physical ranges enforced by database constraints. Open-Meteo's model output can fall a hair outside them
# (for example shortwave radiation of -0.1 W/m2 around dusk), which made the whole refresh fail.
RANGES: dict[str, tuple[float, float]] = {
    "relative_humidity_pct": (0, 100),
    "precipitation_probability_pct": (0, 100),
    "cloud_cover_pct": (0, 100),
    "wind_direction_deg": (0, 360),
    "precipitation_mm": (0, float("inf")),
    "wind_speed_ms": (0, float("inf")),
    "shortwave_radiation_wm2": (0, float("inf")),
    "et0_mm": (0, float("inf")),
}


def _clamp(values: dict[str, float | None]) -> dict[str, float | None]:
    out = dict(values)
    for col, (lo, hi) in RANGES.items():
        v = out.get(col)
        if v is not None:
            out[col] = min(hi, max(lo, v))
    return out


def _utc(ts: str) -> datetime:
    # timezone=UTC is requested, so timestamps are naive UTC like "2026-11-13T18:45".
    return datetime.fromisoformat(ts).replace(tzinfo=UTC)


def parse(payload: dict[str, Any]) -> list[WeatherRow]:
    try:
        rows: list[WeatherRow] = []
        current = payload.get("current")
        if current:
            values = {col: current.get(src) for src, col in FIELD_MAP.items() if src in current}
            rows.append(WeatherRow("observation", _utc(current["time"]), _clamp(values)))
        hourly = payload["hourly"]
        for i, ts in enumerate(hourly["time"]):
            values = {col: hourly[src][i] for src, col in FIELD_MAP.items() if src in hourly}
            rows.append(WeatherRow("forecast", _utc(ts), _clamp(values)))
        return rows
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise WeatherUnavailableError("Unexpected response from Open-Meteo.") from exc


class OpenMeteoClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 10.0) -> None:
        self._client = httpx.Client(
            transport=transport, timeout=timeout, headers={"User-Agent": "agri-sense/0.1"}
        )

    def forecast(self, latitude: float, longitude: float, days: int = 7) -> list[WeatherRow]:
        params: dict[str, str | int | float] = {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "current": CURRENT_VARS,
            "hourly": HOURLY_VARS,
            "timezone": "UTC",
            "forecast_days": days,
            # Hourly data starts at 00:00 UTC; one past day guarantees the farm's whole local
            # "today" is present for time zones ahead of UTC (e.g. India, UTC+5:30).
            "past_days": 1,
            "wind_speed_unit": "ms",
        }
        return parse(self._get(params))

    def _get(self, params: dict[str, str | int | float]) -> dict[str, Any]:
        """GET with a short retry on rate limits, server errors and network failures."""
        problem = "unknown error"
        for attempt in range(RETRIES):
            if attempt:
                time.sleep(BACKOFF_S * attempt)
            try:
                res = self._client.get(BASE_URL, params=params)
            except httpx.HTTPError as exc:
                problem = f"network error: {type(exc).__name__}"
                continue
            if res.status_code == 200:
                try:
                    payload: dict[str, Any] = res.json()
                except ValueError:
                    problem = "invalid response"
                    continue
                return payload
            problem = f"HTTP {res.status_code}"
            try:
                reason = res.json().get("reason")
            except ValueError:
                reason = None
            if reason:
                problem += f": {str(reason)[:160]}"
            if res.status_code != 429 and res.status_code < 500:
                break  # a request error will not fix itself on retry
        log.warning("Open-Meteo request failed (%s)", problem)
        raise WeatherUnavailableError(f"Open-Meteo request failed ({problem}).")
