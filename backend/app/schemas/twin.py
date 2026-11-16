from datetime import date, datetime
from typing import Any

from app.models.enums import DataSource, SensorType
from app.schemas.common import OutputModel


class TwinCrop(OutputModel):
    cycle_id: int
    crop_name: str
    variety: str | None
    category: str
    status: str
    planted_on: date | None
    expected_harvest_on: date | None
    growth_fraction: float | None
    row_spacing_m: float
    form: str
    stage_key: str | None = None  # FAO-56 based stage (app/domain/growth.py); None if unknown/unsupported
    stage_name: str | None = None


class TwinHealth(OutputModel):
    """Latest saved disease check for the zone (within 30 days)."""

    state: str  # disease | healthy | uncertain
    detection_id: int
    label: str
    confidence: float
    severity: str
    knowledge_key: str | None
    detected_at: datetime


class TwinZone(OutputModel):
    id: int
    name: str
    zone_type: str
    area_hectares: float | None
    irrigation_method: str | None
    polygon: list[list[float]]
    center: list[float]
    size: list[float]
    layout: str
    crop: TwinCrop | None
    soil_moisture: float | None
    temperature: float | None
    irrigating: bool
    irrigation_started_at: datetime | None
    health: TwinHealth | None = None


class TwinLatest(OutputModel):
    value: float
    quality: str
    recorded_at: datetime


class TwinSensor(OutputModel):
    id: int
    name: str
    zone_id: int | None
    device_id: int | None
    sensor_type: SensorType
    unit: str
    source: DataSource
    is_simulated: bool
    status: str
    position: list[float]
    latest: TwinLatest | None


class TwinSun(OutputModel):
    elevation_deg: float
    azimuth_deg: float


class TwinWeather(OutputModel):
    observed_at: datetime
    temperature_c: float | None
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    cloud_cover_pct: float | None
    precipitation_mm: float | None


class TwinExtent(OutputModel):
    min: list[float]
    max: list[float]


class FarmTwin(OutputModel):
    farm_id: int
    farm_name: str
    generated_at: datetime
    units: str
    extent: TwinExtent
    sun: TwinSun | None
    weather: TwinWeather | None
    zones: list[TwinZone]
    sensors: list[TwinSensor]
    # Infrastructure items are heterogeneous (kind-specific fields); every item has kind, id, schematic.
    infrastructure: list[dict[str, Any]]
