"""Generic persistence helpers shared by all resource routers.

Every mutation writes an audit_logs row in the same transaction, so the change
and its audit record either both persist or neither does.
"""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams
from app.api.errors import NotFoundError
from app.db.base import Base
from app.models import AuditLog, Farm


class HasId(Protocol):
    id: Any


M = TypeVar("M", bound=Base)


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


def entity_name(model: type[Base]) -> str:
    return str(model.__tablename__)


def get_or_404(db: Session, model: type[M], obj_id: Any, label: str | None = None) -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFoundError(f"{label or model.__name__} {obj_id} not found.")
    return obj


def audit(
    db: Session, action: str, obj: Base, changes: dict[str, Any] | None = None, farm_id: int | None = None
) -> None:
    if farm_id is None:
        # A farm is its own scope; other records carry farm_id directly or receive it from the caller.
        farm_id = cast(HasId, obj).id if isinstance(obj, Farm) else getattr(obj, "farm_id", None)
    db.add(
        AuditLog(
            action=f"{entity_name(type(obj))}.{action}",
            entity_type=entity_name(type(obj)),
            entity_id=str(cast(HasId, obj).id),
            farm_id=farm_id,
            changes={k: _jsonable(v) for k, v in (changes or {}).items()} or None,
            user_id=db.info.get("actor_id"),  # set by get_current_user
        )
    )


def create(
    db: Session, model: type[M], data: BaseModel, *, audit_farm_id: int | None = None, **extra: Any
) -> M:
    values = {**data.model_dump(), **extra}
    obj = model(**values)
    db.add(obj)
    db.flush()
    audit(db, "create", obj, values, audit_farm_id)
    db.commit()
    db.refresh(obj)
    return obj


def update(
    db: Session,
    obj: M,
    data: BaseModel,
    *,
    audit_farm_id: int | None = None,
    validate: Callable[[M], None] | None = None,
) -> M:
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(obj, key, value)
    if validate:
        validate(obj)
    if changes:
        db.flush()
        audit(db, "update", obj, changes, audit_farm_id)
        db.commit()
        db.refresh(obj)
    return obj


def delete(db: Session, obj: Base, *, audit_farm_id: int | None = None) -> None:
    audit(db, "delete", obj, None, audit_farm_id)
    db.delete(obj)
    db.commit()


def paginate(db: Session, stmt: Select[Any], page: PageParams) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}
