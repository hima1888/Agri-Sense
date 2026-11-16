"""Crop catalogue (shared reference data), crop cycles and soil records."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.api.auth import AdminUser, CurrentUser
from app.api.deps import DbSession, Paging, no_content
from app.api.errors import UnprocessableError
from app.domain import growth
from app.models import Crop, CropCycle, SoilMeasurement, SoilProfile
from app.models.enums import CropCategory, CropCycleStatus
from app.schemas.common import Page
from app.schemas.crop import (
    CropCreate,
    CropCycleCreate,
    CropCycleRead,
    CropCycleUpdate,
    CropGrowth,
    CropRead,
    CropUpdate,
    SoilMeasurementCreate,
    SoilMeasurementRead,
    SoilProfileCreate,
    SoilProfileRead,
    SoilProfileUpdate,
)
from app.services import access, crud
from app.services.scoping import require_profile_in_zone

router = APIRouter()


# --- crop catalogue: readable by every signed-in user, editable by admins ---
@router.post("/crops", response_model=CropRead, status_code=201, tags=["crops"])
def create_crop(body: CropCreate, _: AdminUser, db: DbSession) -> Crop:
    return crud.create(db, Crop, body)


@router.get("/crops", response_model=Page[CropRead], tags=["crops"])
def list_crops(
    _: CurrentUser,
    db: DbSession,
    page: Paging,
    category: Annotated[CropCategory | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100, description="Search common/scientific name")] = None,
) -> dict[str, object]:
    stmt = select(Crop).order_by(Crop.common_name)
    if category:
        stmt = stmt.where(Crop.category == category)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(Crop.common_name.ilike(pattern) | Crop.scientific_name.ilike(pattern))
    return crud.paginate(db, stmt, page)


@router.get("/crops/{crop_id}", response_model=CropRead, tags=["crops"])
def get_crop(crop_id: int, _: CurrentUser, db: DbSession) -> Crop:
    return crud.get_or_404(db, Crop, crop_id, "Crop")


@router.patch("/crops/{crop_id}", response_model=CropRead, tags=["crops"])
def update_crop(crop_id: int, body: CropUpdate, _: AdminUser, db: DbSession) -> Crop:
    return crud.update(db, crud.get_or_404(db, Crop, crop_id, "Crop"), body)


@router.delete("/crops/{crop_id}", status_code=204, tags=["crops"])
def delete_crop(crop_id: int, _: AdminUser, db: DbSession) -> Response:
    """Fails with 409 `in_use` while any crop cycle references the crop."""
    crud.delete(db, crud.get_or_404(db, Crop, crop_id, "Crop"))
    return no_content()


# --- crop cycles -----------------------------------------------------------
@router.post(
    "/zones/{zone_id}/crop-cycles", response_model=CropCycleRead, status_code=201, tags=["crop cycles"]
)
def create_crop_cycle(zone_id: int, body: CropCycleCreate, user: CurrentUser, db: DbSession) -> CropCycle:
    zone = access.zone_for(db, user, zone_id)
    crud.get_or_404(db, Crop, body.crop_id, "Crop")
    return crud.create(db, CropCycle, body, zone_id=zone_id, audit_farm_id=zone.farm_id)


@router.get("/zones/{zone_id}/crop-cycles", response_model=Page[CropCycleRead], tags=["crop cycles"])
def list_crop_cycles(
    zone_id: int,
    user: CurrentUser,
    db: DbSession,
    page: Paging,
    status: Annotated[CropCycleStatus | None, Query()] = None,
) -> dict[str, object]:
    access.zone_for(db, user, zone_id)
    stmt = select(CropCycle).where(CropCycle.zone_id == zone_id).order_by(CropCycle.id.desc())
    if status:
        stmt = stmt.where(CropCycle.status == status)
    return crud.paginate(db, stmt, page)


@router.get("/crop-cycles/{cycle_id}", response_model=CropCycleRead, tags=["crop cycles"])
def get_crop_cycle(cycle_id: int, user: CurrentUser, db: DbSession) -> CropCycle:
    return access.record_for(db, user, CropCycle, cycle_id, "Crop cycle")[0]


@router.patch("/crop-cycles/{cycle_id}", response_model=CropCycleRead, tags=["crop cycles"])
def update_crop_cycle(cycle_id: int, body: CropCycleUpdate, user: CurrentUser, db: DbSession) -> CropCycle:
    cycle, farm_id = access.record_for(db, user, CropCycle, cycle_id, "Crop cycle")
    return crud.update(db, cycle, body, audit_farm_id=farm_id)


@router.delete("/crop-cycles/{cycle_id}", status_code=204, tags=["crop cycles"])
def delete_crop_cycle(cycle_id: int, user: CurrentUser, db: DbSession) -> Response:
    cycle, farm_id = access.record_for(db, user, CropCycle, cycle_id, "Crop cycle")
    crud.delete(db, cycle, audit_farm_id=farm_id)
    return no_content()


# --- soil profiles ---------------------------------------------------------
@router.post("/zones/{zone_id}/soil-profiles", response_model=SoilProfileRead, status_code=201, tags=["soil"])
def create_soil_profile(
    zone_id: int, body: SoilProfileCreate, user: CurrentUser, db: DbSession
) -> SoilProfile:
    zone = access.zone_for(db, user, zone_id)
    return crud.create(db, SoilProfile, body, zone_id=zone_id, audit_farm_id=zone.farm_id)


@router.get("/zones/{zone_id}/soil-profiles", response_model=Page[SoilProfileRead], tags=["soil"])
def list_soil_profiles(zone_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.zone_for(db, user, zone_id)
    stmt = select(SoilProfile).where(SoilProfile.zone_id == zone_id).order_by(SoilProfile.id.desc())
    return crud.paginate(db, stmt, page)


@router.get("/soil-profiles/{profile_id}", response_model=SoilProfileRead, tags=["soil"])
def get_soil_profile(profile_id: int, user: CurrentUser, db: DbSession) -> SoilProfile:
    return access.record_for(db, user, SoilProfile, profile_id, "Soil profile")[0]


@router.patch("/soil-profiles/{profile_id}", response_model=SoilProfileRead, tags=["soil"])
def update_soil_profile(
    profile_id: int, body: SoilProfileUpdate, user: CurrentUser, db: DbSession
) -> SoilProfile:
    profile, farm_id = access.record_for(db, user, SoilProfile, profile_id, "Soil profile")
    return crud.update(db, profile, body, audit_farm_id=farm_id)


@router.delete("/soil-profiles/{profile_id}", status_code=204, tags=["soil"])
def delete_soil_profile(profile_id: int, user: CurrentUser, db: DbSession) -> Response:
    profile, farm_id = access.record_for(db, user, SoilProfile, profile_id, "Soil profile")
    crud.delete(db, profile, audit_farm_id=farm_id)
    return no_content()


# --- soil measurements -----------------------------------------------------
@router.post(
    "/zones/{zone_id}/soil-measurements", response_model=SoilMeasurementRead, status_code=201, tags=["soil"]
)
def create_soil_measurement(
    zone_id: int, body: SoilMeasurementCreate, user: CurrentUser, db: DbSession
) -> SoilMeasurement:
    zone = access.zone_for(db, user, zone_id)
    require_profile_in_zone(db, body.soil_profile_id, zone_id)
    return crud.create(db, SoilMeasurement, body, zone_id=zone_id, audit_farm_id=zone.farm_id)


@router.get("/zones/{zone_id}/soil-measurements", response_model=Page[SoilMeasurementRead], tags=["soil"])
def list_soil_measurements(
    zone_id: int,
    user: CurrentUser,
    db: DbSession,
    page: Paging,
    start: Annotated[datetime | None, Query(description="Inclusive lower bound on measured_at")] = None,
    end: Annotated[datetime | None, Query(description="Exclusive upper bound on measured_at")] = None,
) -> dict[str, object]:
    access.zone_for(db, user, zone_id)
    stmt = select(SoilMeasurement).where(SoilMeasurement.zone_id == zone_id)
    if start:
        stmt = stmt.where(SoilMeasurement.measured_at >= start)
    if end:
        stmt = stmt.where(SoilMeasurement.measured_at < end)
    return crud.paginate(db, stmt.order_by(SoilMeasurement.measured_at.desc()), page)


@router.get("/soil-measurements/{measurement_id}", response_model=SoilMeasurementRead, tags=["soil"])
def get_soil_measurement(measurement_id: int, user: CurrentUser, db: DbSession) -> SoilMeasurement:
    return access.record_for(db, user, SoilMeasurement, measurement_id, "Soil measurement")[0]


@router.delete("/soil-measurements/{measurement_id}", status_code=204, tags=["soil"])
def delete_soil_measurement(measurement_id: int, user: CurrentUser, db: DbSession) -> Response:
    m, farm_id = access.record_for(db, user, SoilMeasurement, measurement_id, "Soil measurement")
    crud.delete(db, m, audit_farm_id=farm_id)
    return no_content()


# --- crop growth stages (FAO-56 stage lengths; see app/domain/growth.py) ---
def _growth(crop: Crop, cycle_days: int | None, source: str) -> dict[str, Any]:
    try:
        model = growth.stages(crop.common_name, cycle_days)
    except growth.UnsupportedCropError as e:
        raise UnprocessableError(str(e), {"supported": growth.supported()}) from e
    return {**model, "crop_id": crop.id, "cycle_days_source": source}


@router.get("/crops/{crop_id}/growth", response_model=CropGrowth, tags=["crops"])
def crop_growth(crop_id: int, _: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Growth stages for a crop, scaled to its typical cycle length in the catalogue."""
    crop = crud.get_or_404(db, Crop, crop_id, "Crop")
    has = crop.typical_cycle_days is not None
    return _growth(crop, crop.typical_cycle_days, "crop catalogue" if has else "FAO-56 total")


@router.get("/crop-cycles/{cycle_id}/growth", response_model=CropGrowth, tags=["crop cycles"])
def cycle_growth(cycle_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Stages for a zone's crop cycle (its own dates if known) and where it is today."""
    cycle = access.record_for(db, user, CropCycle, cycle_id, "Crop cycle")[0]
    crop = db.get(Crop, cycle.crop_id)
    assert crop is not None
    if cycle.planted_on and cycle.expected_harvest_on and cycle.expected_harvest_on > cycle.planted_on:
        days, source = (cycle.expected_harvest_on - cycle.planted_on).days, "crop cycle dates"
    elif crop.typical_cycle_days:
        days, source = crop.typical_cycle_days, "crop catalogue"
    else:
        days, source = None, "FAO-56 total"
    out = _growth(crop, days, source)
    out.update(cycle_id=cycle.id, planted_on=cycle.planted_on)
    out["current"] = (
        growth.current(out, cycle.planted_on, date.today()) if cycle.status == "growing" else None
    )
    return out
