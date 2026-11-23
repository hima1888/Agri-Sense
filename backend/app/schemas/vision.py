from datetime import datetime
from typing import Any, Literal

from pydantic import Field, computed_field

from app.knowledge.diseases import key_for_label
from app.schemas.common import OutputModel


class Candidate(OutputModel):
    label: str
    subject_type: str
    confidence: float


class ModelGuess(OutputModel):
    label: str
    confidence: float


class QualityCheck(OutputModel):
    key: str
    value: float | str
    status: Literal["ok", "low", "poor"]
    note: str


class Occlusion(OutputModel):
    method: str
    grid: list[list[float]] | None
    crop: str


class ModelRef(OutputModel):
    id: int
    name: str
    version: str


class Recognition(OutputModel):
    outcome: Literal["recognized", "uncertain", "unsupported"]
    label: str | None
    subject_type: str | None
    confidence: float
    produce_probability: float
    candidates: list[Candidate]
    model_sees: list[ModelGuess]
    quality: list[QualityCheck]
    explanation: Occlusion
    limitations: list[str]
    image_size: list[int]
    detection_id: int | None
    saved: bool
    model: ModelRef


class Detection(OutputModel):
    id: int
    farm_id: int
    zone_id: int | None
    subject_type: str
    predicted_label: str
    confidence: float
    top_k: list[dict[str, Any]] | None
    explanation: dict[str, Any] | None
    model_version_id: int | None
    detected_at: datetime


class SupportedClass(OutputModel):
    label: str
    subject_type: str


class ModelInfo(OutputModel):
    name: str
    version: str
    available: bool
    framework: str
    source: str
    training_dataset: str
    metrics: dict[str, Any]
    supported: list[SupportedClass]
    min_confidence: float


# --- disease screening (Phase 10) ------------------------------------------------
class DiseaseModelRef(OutputModel):
    key: str
    name: str
    version: str
    id: int | None = None


class DiseaseCandidate(OutputModel):
    label: str
    crop: str | None
    disease: str | None
    is_healthy: bool
    confidence: float


class RuleCheck(OutputModel):
    rule: str
    passed: bool
    detail: str


class DiseaseKnowledge(OutputModel):
    """Structured guidance from app.knowledge.diseases (not generated per request)."""

    key: str
    name: str
    pathogen: str
    pathogen_type: str
    crops: list[str]
    what: str
    symptoms: list[str]
    causes: str
    conditions: str
    spread: str
    management: list[str]
    prevention: list[str]
    sustainable: list[str]
    monitor: list[str]
    seek_advice: str
    source: str
    reviewed: bool


class HealthyGuidance(OutputModel):
    what: str
    monitor: list[str]
    prevention: list[str]
    seek_advice: str
    source: str
    reviewed: bool


class DiseaseScreening(OutputModel):
    outcome: Literal[
        "possible_disease",
        "possible_healthy",
        "uncertain",
        "cannot_identify",
        "not_a_leaf",
        "unsupported_crop",
    ]
    part: Literal["leaf", "fruit"] = "leaf"
    crop: str | None
    crop_source: str | None
    model: DiseaseModelRef | None
    label: str | None
    disease: str | None
    is_healthy: bool | None
    confidence: float | None
    margin: float | None
    candidates: list[DiseaseCandidate]
    checks: list[RuleCheck]
    quality: list[QualityCheck]
    affected_area_pct: float | None
    severity: str | None
    reason: str
    limitations: list[str]
    image_size: list[int]
    detection_id: int | None
    saved: bool
    # Knowledge for the predicted disease: only for "possible_disease" (for "uncertain" the UI links the
    # candidates' knowledge separately, so unconfirmed guidance is never shown as the answer).
    knowledge_key: str | None = None
    knowledge: DiseaseKnowledge | None = None
    healthy_guidance: HealthyGuidance | None = None


class DiseaseRecord(OutputModel):
    id: int
    farm_id: int
    zone_id: int | None
    disease_label: str
    is_healthy: bool
    confidence: float
    severity: str
    affected_area_pct: float | None
    top_k: list[dict[str, Any]] | None
    explanation: dict[str, Any] | None
    model_version_id: int | None
    detected_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def knowledge_key(self) -> str | None:
        return None if self.is_healthy else key_for_label(self.disease_label)


class DiseaseModelInfo(OutputModel):
    key: str
    name: str
    version: str
    available: bool
    source: str
    weights_source: str
    licence: str
    architecture: str
    preprocessing: str
    input: list[int]
    crops: list[str]
    classes: list[str]
    used_for: list[str]
    part: Literal["leaf", "fruit"] = "leaf"
    published_accuracy: str
    limitations: list[str]


class DiseaseModels(OutputModel):
    models: list[DiseaseModelInfo]
    supported_crops: dict[str, str]
    supported_fruits: dict[str, str] = Field(default_factory=dict)
    crop_groups: dict[str, str] = Field(default_factory=dict)
    thresholds: dict[str, float]
    limitations: list[str]
