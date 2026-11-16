from datetime import datetime
from typing import Any, Literal

from app.schemas.common import InputModel, OutputModel


class Factor(OutputModel):
    name: str
    value: Any
    unit: str
    source: str
    simulated: bool


class Recommendation(OutputModel):
    id: int | None = None
    rule: str
    zone_id: int | None
    zone_name: str | None
    category: str
    priority: Literal["low", "medium", "high", "critical"]
    title: str
    rationale: str
    action: dict[str, Any]
    factors: list[Factor]
    confidence: float
    confidence_basis: str
    expected_impact: dict[str, Any] | None
    limitations: list[str]
    uses_simulated_data: bool
    expires_at: datetime


class Stored(OutputModel):
    created: int
    refreshed: int
    expired: int


class RecommendationSet(OutputModel):
    farm_id: int
    generated_at: datetime
    method: str
    weather_fetched_at: datetime | None
    forecast_hours: int
    zones_assessed: int
    recommendations: list[Recommendation]
    uses_simulated_data: bool
    stored: Stored | None = None


class StoredRecommendation(OutputModel):
    id: int
    farm_id: int
    zone_id: int | None
    rule: str | None
    category: str
    priority: str
    status: str
    title: str
    rationale: str
    action: dict[str, Any] | None
    factors: list[dict[str, Any]] | None
    expected_impact: dict[str, Any] | None
    confidence: float
    limitations: str
    expires_at: datetime | None
    responded_at: datetime | None
    created_at: datetime


class RespondInput(InputModel):
    status: Literal["accepted", "rejected", "applied"]
