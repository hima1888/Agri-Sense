from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import Field, model_validator

from app.models.enums import (
    AlertCategory,
    AlertSeverity,
    AlertStatus,
    FertilizerMethod,
    IrrigationMethod,
    IrrigationStatus,
    IrrigationTrigger,
    PesticideType,
    QuantityUnit,
)
from app.schemas.common import InputModel, Name, NonNeg, Notes, Num, OutputModel, Pct


# --- irrigation ------------------------------------------------------------
class IrrigationCreate(InputModel):
    method: IrrigationMethod
    trigger: IrrigationTrigger = "manual"
    status: IrrigationStatus = "scheduled"
    scheduled_for: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    volume_liters: NonNeg | None = None
    notes: Notes | None = None

    @model_validator(mode="after")
    def _times(self) -> Self:
        if self.started_at and self.ended_at and self.ended_at < self.started_at:
            raise ValueError("ended_at cannot be before started_at")
        return self


class IrrigationUpdate(InputModel):
    status: IrrigationStatus | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    volume_liters: NonNeg | None = None
    notes: Notes | None = None


class IrrigationRead(OutputModel):
    id: int
    zone_id: int
    recommendation_id: int | None
    method: IrrigationMethod
    trigger: IrrigationTrigger
    status: IrrigationStatus
    scheduled_for: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    volume_liters: Num | None
    notes: str | None
    created_at: datetime


# --- fertilizer ------------------------------------------------------------
class FertilizerCreate(InputModel):
    applied_at: datetime
    product_name: Name
    method: FertilizerMethod
    quantity_kg: NonNeg
    crop_cycle_id: int | None = None
    is_organic: bool = False
    n_pct: Pct | None = None
    p_pct: Pct | None = None
    k_pct: Pct | None = None
    notes: Notes | None = None


class FertilizerRead(OutputModel):
    id: int
    zone_id: int
    crop_cycle_id: int | None
    recommendation_id: int | None
    applied_at: datetime
    product_name: str
    is_organic: bool
    n_pct: Num | None
    p_pct: Num | None
    k_pct: Num | None
    quantity_kg: Num
    method: FertilizerMethod
    notes: str | None
    created_at: datetime


# --- pesticide -------------------------------------------------------------
class PesticideCreate(InputModel):
    applied_at: datetime
    product_name: Name
    pesticide_type: PesticideType
    quantity: Annotated[Decimal, Field(ge=0)]
    quantity_unit: QuantityUnit
    crop_cycle_id: int | None = None
    active_ingredient: Name | None = None
    target: Name | None = None
    pre_harvest_interval_days: Annotated[int, Field(ge=0, le=365)] | None = None
    # Phase 13: the disease check that justified this spray (evidence-based use).
    disease_detection_id: int | None = None
    notes: Notes | None = None


class PesticideRead(OutputModel):
    id: int
    zone_id: int
    crop_cycle_id: int | None
    disease_detection_id: int | None
    recommendation_id: int | None
    applied_at: datetime
    product_name: str
    active_ingredient: str | None
    pesticide_type: PesticideType
    target: str | None
    quantity: Num
    quantity_unit: QuantityUnit
    pre_harvest_interval_days: int | None
    notes: str | None
    created_at: datetime


# --- alerts ----------------------------------------------------------------
class AlertCreate(InputModel):
    severity: AlertSeverity
    category: AlertCategory
    title: Name
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    zone_id: int | None = None
    sensor_id: int | None = None
    context: dict[str, Any] | None = None


class AlertRead(OutputModel):
    id: int
    farm_id: int
    zone_id: int | None
    sensor_id: int | None
    recommendation_id: int | None
    severity: AlertSeverity
    category: AlertCategory
    status: AlertStatus
    title: str
    message: str
    context: dict[str, Any] | None
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
