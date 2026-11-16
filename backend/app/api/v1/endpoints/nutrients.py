"""Fertilizer planning and chemical-use endpoints (Phase 13)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from pydantic import Field

from app.api.auth import CurrentUser
from app.api.deps import DbSession, no_content
from app.models import CropCycle
from app.models.enums import PesticideType
from app.schemas.common import InputModel
from app.services import access, crud, soil
from app.services import nutrients as svc

router = APIRouter(tags=["nutrients & chemicals"])
Dose = Annotated[float, Field(ge=0, le=1000)]


class NutrientTarget(InputModel):
    n: Dose
    p2o5: Dose
    k2o: Dose
    source: Annotated[str, Field(min_length=3, max_length=200)]


@router.get("/zones/{zone_id}/nutrients/plan")
def nutrient_plan(zone_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Soil-test-adjusted fertilizer plan for the zone's current crop cycle."""
    return soil.json_safe(svc.nutrient_plan(db, access.zone_for(db, user, zone_id)))  # type: ignore[no-any-return]


@router.put("/crop-cycles/{cycle_id}/nutrient-target")
def set_target(cycle_id: int, body: NutrientTarget, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Record the recommended dose (kg/ha N, P2O5, K2O) for this crop cycle and where it came from."""
    cycle, farm_id = access.record_for(db, user, CropCycle, cycle_id, "Crop cycle")
    before = cycle.nutrient_target
    cycle.nutrient_target = body.model_dump()
    crud.audit(db, "update", cycle, {"nutrient_target": [before, cycle.nutrient_target]}, farm_id=farm_id)
    db.commit()
    return {"cycle_id": cycle.id, "nutrient_target": cycle.nutrient_target}


@router.delete("/crop-cycles/{cycle_id}/nutrient-target", status_code=204)
def clear_target(cycle_id: int, user: CurrentUser, db: DbSession) -> Response:
    cycle, farm_id = access.record_for(db, user, CropCycle, cycle_id, "Crop cycle")
    crud.audit(db, "update", cycle, {"nutrient_target": [cycle.nutrient_target, None]}, farm_id=farm_id)
    cycle.nutrient_target = None
    db.commit()
    return no_content()


@router.get("/zones/{zone_id}/chemicals/use")
def chemical_use(zone_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Pesticide use this crop cycle, PHI status, evidence share, and change vs the previous cycle."""
    return soil.json_safe(svc.chemical_use(db, access.zone_for(db, user, zone_id)))  # type: ignore[no-any-return]


@router.get("/zones/{zone_id}/chemicals/spray-check")
def spray_check(
    zone_id: int,
    user: CurrentUser,
    db: DbSession,
    pesticide_type: PesticideType,
    phi_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> dict[str, Any]:
    """Advisory pre-spray check: evidence, rain/wind/heat in the next 6 h, PHI vs harvest, recent sprays."""
    zone = access.zone_for(db, user, zone_id)
    return soil.json_safe(svc.spray_check(db, zone, pesticide_type, phi_days))  # type: ignore[no-any-return]
