from datetime import date, datetime
from typing import Any, Literal

from app.schemas.common import OutputModel


class SoilComponent(OutputModel):
    value: float
    unit: str
    value_mg_kg: float | None = None
    status: str
    target: list[float]
    target_source: str
    source: str
    confidence: float
    score: float


class ProjectionDay(OutputModel):
    date: date
    et0_mm: float
    etc_mm: float
    effective_rain_mm: float
    depletion_mm: float


class WaterBalance(OutputModel):
    field_capacity_pct: float
    wilting_point_pct: float
    moisture_pct: float
    root_depth_m: float
    depletion_fraction_p: float
    kc: float
    taw_mm: float
    raw_mm: float
    depletion_mm: float
    available_fraction: float | None
    status: Literal["above_field_capacity", "adequate", "stress", "severe"]
    days_to_stress: int | None
    forecast_days: int
    projection: list[ProjectionDay]
    sources: dict[str, str]
    confidence: float
    measured_at: datetime | None = None
    irrigation_since_mm: float = 0.0


class Factor(OutputModel):
    key: str
    label: str
    status: str
    score: float
    weight: float
    impact: float


class Guidance(OutputModel):
    level: Literal["info", "warning"]
    text: str


class SoilCrop(OutputModel):
    name: str
    category: str
    growth_fraction: float | None
    status: str | None


class SoilAssessment(OutputModel):
    zone_id: int
    zone_name: str
    assessed_at: datetime
    method: str
    crop: SoilCrop | None
    index: float | None
    rating: Literal["good", "fair", "poor"] | None
    confidence: float
    confidence_reasons: list[str]
    components: dict[str, SoilComponent]
    not_assessed: list[str]
    factors: list[Factor]
    water: WaterBalance | None
    trends: dict[str, float]
    guidance: list[Guidance]
    limitations: list[str]
    uses_simulated_data: bool
    inputs: dict[str, Any]


class ZoneSoilSummary(OutputModel):
    zone_id: int
    zone_name: str
    index: float | None
    rating: str | None
    confidence: float
    water_status: str | None
    days_to_stress: int | None
    top_factor: str | None
    uses_simulated_data: bool


class SavedAssessment(OutputModel):
    id: int
    zone_id: int | None
    created_at: datetime
    confidence: float
    predicted_value: dict[str, Any]
    factors: list[dict[str, Any]]
    limitations: str
