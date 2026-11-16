from datetime import date, datetime

from app.models.enums import SensorType
from app.schemas.common import OutputModel
from app.schemas.operations import AlertRead


# --- weather ---------------------------------------------------------------
class WeatherPoint(OutputModel):
    valid_at: datetime
    temperature_c: float | None
    relative_humidity_pct: float | None
    precipitation_mm: float | None
    precipitation_probability_pct: float | None
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    cloud_cover_pct: float | None
    shortwave_radiation_wm2: float | None
    et0_mm: float | None


class WeatherDay(OutputModel):
    date: date
    temp_min_c: float | None
    temp_max_c: float | None
    precipitation_mm: float
    precipitation_probability_max_pct: float | None
    et0_mm: float


class FarmWeather(OutputModel):
    farm_id: int
    source: str
    attribution: str
    timezone: str
    fetched_at: datetime | None
    stale: bool
    error: str | None
    current: WeatherPoint | None
    hourly: list[WeatherPoint]
    daily: list[WeatherDay]


# --- dashboard -------------------------------------------------------------
class ActiveCycle(OutputModel):
    id: int
    crop_name: str
    variety: str | None
    status: str
    planted_on: date | None
    expected_harvest_on: date | None


class KeyValue(OutputModel):
    value: float
    recorded_at: datetime
    unit: str


class ZoneSummary(OutputModel):
    id: int
    name: str
    zone_type: str
    area_hectares: float | None
    irrigation_method: str | None
    sensor_count: int
    active_cycle: ActiveCycle | None
    latest: dict[str, KeyValue]


class SensorCounts(OutputModel):
    total: int
    active: int
    simulated: int
    hardware: int
    reporting: int


class AlertSummary(OutputModel):
    open: int
    by_severity: dict[str, int]
    recent: list[AlertRead]


class ActivityItem(OutputModel):
    kind: str
    id: int
    zone_id: int
    at: datetime | None
    title: str
    amount: float | None
    unit: str
    status: str


class WaterSummary(OutputModel):
    liters: float
    events: int


class ReadingCounts(OutputModel):
    count: int
    not_good: int


class TypeStats(OutputModel):
    sensor_type: SensorType
    unit: str
    min: float
    max: float
    avg: float
    count: int


class DashboardSummary(OutputModel):
    farm_id: int
    generated_at: datetime
    zones: list[ZoneSummary]
    sensors: SensorCounts
    alerts: AlertSummary
    activity: list[ActivityItem]
    water_7d: WaterSummary
    readings_24h: ReadingCounts
    stats_24h: list[TypeStats]


# --- series ----------------------------------------------------------------
class SeriesPoint(OutputModel):
    t: datetime
    avg: float
    min: float
    max: float
    n: int


class ZoneSeries(OutputModel):
    zone_id: int | None
    zone_name: str
    points: list[SeriesPoint]


class FarmSeries(OutputModel):
    sensor_type: SensorType
    unit: str | None
    includes_simulated: bool
    bucket_minutes: int
    start: datetime
    end: datetime
    zones: list[ZoneSeries]
