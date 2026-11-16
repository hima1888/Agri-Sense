"""Current user, user administration, farms and zones."""

from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.api.auth import AdminUser, CurrentUser
from app.api.deps import DbSession, Paging, no_content
from app.models import Farm, FarmZone, User
from app.schemas.common import Page
from app.schemas.farm import (
    AdminUserUpdate,
    FarmCreate,
    FarmRead,
    FarmUpdate,
    MeUpdate,
    UserRead,
    ZoneCreate,
    ZoneRead,
    ZoneUpdate,
)
from app.services import access, crud

router = APIRouter()


# --- current user ----------------------------------------------------------
@router.get("/me", response_model=UserRead, tags=["account"])
def get_me(user: CurrentUser) -> User:
    """The signed-in user's AGRI-SENSE profile (created automatically on first sign-in)."""
    return user


@router.patch("/me", response_model=UserRead, tags=["account"])
def update_me(body: MeUpdate, user: CurrentUser, db: DbSession) -> User:
    return crud.update(db, user, body)


# --- user administration (admin only) ----------------------------------------
@router.get("/users", response_model=Page[UserRead], tags=["admin"])
def list_users(_: AdminUser, db: DbSession, page: Paging) -> dict[str, object]:
    return crud.paginate(db, select(User).order_by(User.created_at), page)


@router.get("/users/{user_id}", response_model=UserRead, tags=["admin"])
def get_user(user_id: UUID, _: AdminUser, db: DbSession) -> User:
    return crud.get_or_404(db, User, user_id, "User")


@router.patch("/users/{user_id}", response_model=UserRead, tags=["admin"])
def update_user(user_id: UUID, body: AdminUserUpdate, _: AdminUser, db: DbSession) -> User:
    return crud.update(db, crud.get_or_404(db, User, user_id, "User"), body)


# --- farms -----------------------------------------------------------------
@router.post("/farms", response_model=FarmRead, status_code=201, tags=["farms"])
def create_farm(body: FarmCreate, user: CurrentUser, db: DbSession) -> Farm:
    return crud.create(db, Farm, body, owner_id=user.id)


@router.get("/farms", response_model=Page[FarmRead], tags=["farms"])
def list_farms(user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    """Farms the caller owns (administrators see all farms)."""
    return crud.paginate(db, access.visible_farms(select(Farm), user).order_by(Farm.id), page)


@router.get("/farms/{farm_id}", response_model=FarmRead, tags=["farms"])
def get_farm(farm_id: int, user: CurrentUser, db: DbSession) -> Farm:
    return access.farm_for(db, user, farm_id)


@router.patch("/farms/{farm_id}", response_model=FarmRead, tags=["farms"])
def update_farm(farm_id: int, body: FarmUpdate, user: CurrentUser, db: DbSession) -> Farm:
    return crud.update(db, access.farm_for(db, user, farm_id), body)


@router.delete("/farms/{farm_id}", status_code=204, tags=["farms"])
def delete_farm(farm_id: int, user: CurrentUser, db: DbSession) -> Response:
    """Deletes the farm and everything under it (zones, sensors, readings, records)."""
    crud.delete(db, access.farm_for(db, user, farm_id))
    return no_content()


# --- zones -----------------------------------------------------------------
@router.post("/farms/{farm_id}/zones", response_model=ZoneRead, status_code=201, tags=["zones"])
def create_zone(farm_id: int, body: ZoneCreate, user: CurrentUser, db: DbSession) -> FarmZone:
    access.farm_for(db, user, farm_id)
    return crud.create(db, FarmZone, body, farm_id=farm_id)


@router.get("/farms/{farm_id}/zones", response_model=Page[ZoneRead], tags=["zones"])
def list_zones(farm_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.farm_for(db, user, farm_id)
    return crud.paginate(db, select(FarmZone).where(FarmZone.farm_id == farm_id).order_by(FarmZone.id), page)


@router.get("/zones/{zone_id}", response_model=ZoneRead, tags=["zones"])
def get_zone(zone_id: int, user: CurrentUser, db: DbSession) -> FarmZone:
    return access.zone_for(db, user, zone_id)


@router.patch("/zones/{zone_id}", response_model=ZoneRead, tags=["zones"])
def update_zone(zone_id: int, body: ZoneUpdate, user: CurrentUser, db: DbSession) -> FarmZone:
    return crud.update(db, access.zone_for(db, user, zone_id), body)


@router.delete("/zones/{zone_id}", status_code=204, tags=["zones"])
def delete_zone(zone_id: int, user: CurrentUser, db: DbSession) -> Response:
    crud.delete(db, access.zone_for(db, user, zone_id))
    return no_content()
