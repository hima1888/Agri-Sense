"""Farm-scoped authorization.

A user can see and change only farms they own (admins: all farms). Every
farm-scoped record is checked through its farm. Records the caller may not see
return 404, not 403, so the API never confirms that another user's record exists.
"""

from typing import Any, TypeVar

from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.api.errors import NotFoundError
from app.db.base import Base
from app.models import Farm, FarmZone, User

M = TypeVar("M", bound=Base)


def can_access(user: User, farm: Farm) -> bool:
    return user.role == "admin" or farm.owner_id == user.id


def farm_for(db: Session, user: User, farm_id: int) -> Farm:
    farm = db.get(Farm, farm_id)
    if farm is None or not can_access(user, farm):
        raise NotFoundError(f"Farm {farm_id} not found.")
    return farm


def zone_for(db: Session, user: User, zone_id: int) -> FarmZone:
    zone = db.get(FarmZone, zone_id)
    if zone is None or not can_access(user, zone.farm):
        raise NotFoundError(f"Zone {zone_id} not found.")
    return zone


def record_for(db: Session, user: User, model: type[M], obj_id: Any, label: str) -> tuple[M, int]:
    """Load a farm- or zone-scoped record and return it with its farm id, if the user may access it."""
    obj = db.get(model, obj_id)
    if obj is not None:
        farm_id = getattr(obj, "farm_id", None)
        if farm_id is None and getattr(obj, "zone_id", None) is not None:
            zone = db.get(FarmZone, obj.zone_id)  # type: ignore[attr-defined]
            farm_id = zone.farm_id if zone else None
        farm = db.get(Farm, farm_id) if farm_id is not None else None
        if farm is not None and can_access(user, farm):
            return obj, farm.id
    raise NotFoundError(f"{label} {obj_id} not found.")


def visible_farms(stmt: Select[Any], user: User) -> Select[Any]:
    return stmt if user.role == "admin" else stmt.where(Farm.owner_id == user.id)
