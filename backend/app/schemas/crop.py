from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import Field, model_validator

from app.models.enums import CropCategory, CropCycleStatus, SoilMeasurementSource, SoilTexture
from app.schemas.common import InputModel, Name, NonNeg, Notes, Num, OutputModel, Pct

Ph = Annotated[Decimal, Field(ge=0, le=14)]
TempC = Annotated[Decimal, Field(ge=-60, le=70)]


def _check_order(low: Any, high: Any, message: str) -> None:
    if low is not None and high is not None and low > high:
        raise ValueError(message)


# --- crop catalogue --------------------------------------------------------
class CropCreate(InputModel):
    common_name: Name
    scientific_name: Name | None = None
    category: CropCategory
    typical_cycle_days: Annotated[int, Field(ge=1, le=3650)] | None = None
    optimal_ph_min: Ph | None = None
    optimal_ph_max: Ph | None = None
    optimal_temp_min_c: TempC | None = None
    optimal_temp_max_c: TempC | None = None
    water_requirement_mm: NonNeg | None = None

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        _check_order(self.optimal_ph_min, self.optimal_ph_max, "optimal_ph_min must be <= optimal_ph_max")
        _check_order(self.optimal_temp_min_c, self.optimal_temp_max_c, "optimal_temp_min_c must be <= max")
        return self


class CropUpdate(InputModel):
    common_name: Name | None = None
    scientific_name: Name | None = None
    category: CropCategory | None = None
    typical_cycle_days: Annotated[int, Field(ge=1, le=3650)] | None = None
    optimal_ph_min: Ph | None = None
    optimal_ph_max: Ph | None = None
    optimal_temp_min_c: TempC | None = None
    optimal_temp_max_c: TempC | None = None
    water_requirement_mm: NonNeg | None = None


class CropRead(OutputModel):
    id: int
    common_name: str
    scientific_name: str | None
    category: CropCategory
    typical_cycle_days: int | None
    optimal_ph_min: Num | None
    optimal_ph_max: Num | None
    optimal_temp_min_c: Num | None
    optimal_temp_max_c: Num | None
    water_requirement_mm: Num | None
    created_at: datetime
    updated_at: datetime


# --- crop cycles -----------------------------------------------------------
class CropCycleCreate(InputModel):
    crop_id: int
    variety: Name | None = None
    status: CropCycleStatus = "planned"
    planted_on: date | None = None
    expected_harvest_on: date | None = None
    harvested_on: date | None = None
    area_hectares: NonNeg | None = None
    plant_count: Annotated[int, Field(ge=0)] | None = None
    actual_yield_kg: NonNeg | None = None
    notes: Notes | None = None

    @model_validator(mode="after")
    def _dates(self) -> Self:
        _check_order(self.planted_on, self.harvested_on, "harvested_on cannot be before planted_on")
        return self


class CropCycleUpdate(InputModel):
    variety: Name | None = None
    status: CropCycleStatus | None = None
    planted_on: date | None = None
    expected_harvest_on: date | None = None
    harvested_on: date | None = None
    area_hectares: NonNeg | None = None
    plant_count: Annotated[int, Field(ge=0)] | None = None
    actual_yield_kg: NonNeg | None = None
    notes: Notes | None = None


class CropCycleRead(OutputModel):
    id: int
    zone_id: int
    crop_id: int
    variety: str | None
    status: CropCycleStatus
    planted_on: date | None
    expected_harvest_on: date | None
    harvested_on: date | None
    area_hectares: Num | None
    plant_count: int | None
    actual_yield_kg: Num | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# --- soil ------------------------------------------------------------------
class SoilProfileCreate(InputModel):
    texture: SoilTexture | None = None
    sand_pct: Pct | None = None
    silt_pct: Pct | None = None
    clay_pct: Pct | None = None
    organic_matter_pct: Pct | None = None
    bulk_density_g_cm3: Annotated[Decimal, Field(gt=0, le=3)] | None = None
    field_capacity_pct: Pct | None = None
    wilting_point_pct: Pct | None = None
    depth_cm: Annotated[int, Field(ge=0, le=500)] | None = None
    surveyed_on: date | None = None
    notes: Notes | None = None

    @model_validator(mode="after")
    def _fractions(self) -> Self:
        parts = [p for p in (self.sand_pct, self.silt_pct, self.clay_pct) if p is not None]
        if len(parts) == 3 and abs(sum(parts, Decimal(0)) - 100) > 1:
            raise ValueError("sand_pct + silt_pct + clay_pct must total 100 (±1)")
        _check_order(
            self.wilting_point_pct, self.field_capacity_pct, "wilting point must be <= field capacity"
        )
        return self


class SoilProfileUpdate(SoilProfileCreate):
    pass


class SoilProfileRead(OutputModel):
    id: int
    zone_id: int
    texture: SoilTexture | None
    sand_pct: Num | None
    silt_pct: Num | None
    clay_pct: Num | None
    organic_matter_pct: Num | None
    bulk_density_g_cm3: Num | None
    field_capacity_pct: Num | None
    wilting_point_pct: Num | None
    depth_cm: int | None
    surveyed_on: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class SoilMeasurementCreate(InputModel):
    measured_at: datetime
    source: SoilMeasurementSource
    soil_profile_id: int | None = None
    depth_cm: Annotated[int, Field(ge=0, le=500)] | None = None
    ph: Ph | None = None
    nitrogen_mg_kg: NonNeg | None = None
    phosphorus_mg_kg: NonNeg | None = None
    potassium_mg_kg: NonNeg | None = None
    organic_carbon_pct: Pct | None = None
    electrical_conductivity_ds_m: NonNeg | None = None
    moisture_pct: Pct | None = None
    notes: Notes | None = None


class SoilMeasurementRead(OutputModel):
    id: int
    zone_id: int
    soil_profile_id: int | None
    measured_at: datetime
    source: SoilMeasurementSource
    depth_cm: int | None
    ph: Num | None
    nitrogen_mg_kg: Num | None
    phosphorus_mg_kg: Num | None
    potassium_mg_kg: Num | None
    organic_carbon_pct: Num | None
    electrical_conductivity_ds_m: Num | None
    moisture_pct: Num | None
    notes: str | None
    created_at: datetime


class GrowthStage(OutputModel):
    key: str
    name: str
    start_day: int
    end_day: int
    fao_stage: str
    approximate_boundary: bool
    description: str


class Fao56Stages(OutputModel):
    initial: int
    development: int
    mid_season: int
    late_season: int
    region: str


class GrowthPosition(OutputModel):
    day: int
    stage_key: str | None
    progress: float
    note: str | None


class CropGrowth(OutputModel):
    crop: str
    crop_key: str
    crop_id: int
    cycle_id: int | None = None
    planted_on: date | None = None
    cycle_days: int
    cycle_days_source: str
    fao56: Fao56Stages
    stages: list[GrowthStage]
    current: GrowthPosition | None = None
    method: str
    limitations: list[str]
