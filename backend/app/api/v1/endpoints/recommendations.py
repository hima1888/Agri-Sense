"""Explainable farm recommendations (Phase 11)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.auth import CurrentUser
from app.api.deps import DbSession, Paging
from app.api.errors import ConflictError
from app.models import AIRecommendation
from app.schemas.common import Page
from app.schemas.recommend import RecommendationSet, RespondInput, StoredRecommendation
from app.services import access, crud
from app.services import recommend as svc

router = APIRouter(tags=["recommendations"])


@router.get("/farms/{farm_id}/recommendations/preview", response_model=RecommendationSet)
def preview(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Compute recommendations now from stored data, without saving them."""
    return svc.preview(db, access.farm_for(db, user, farm_id))


@router.post("/farms/{farm_id}/recommendations/generate", response_model=RecommendationSet)
def generate(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Compute and store: new advice is created, pending advice refreshed, stale advice expired."""
    farm = access.farm_for(db, user, farm_id)
    result = svc.generate_and_store(db, user, farm)
    crud.audit(db, "create", farm, {"recommendations": result["stored"]})
    db.commit()
    return result


@router.get("/farms/{farm_id}/recommendations", response_model=Page[StoredRecommendation])
def list_recommendations(
    farm_id: int,
    user: CurrentUser,
    db: DbSession,
    page: Paging,
    status: Annotated[str | None, Query(pattern="^(pending|accepted|rejected|applied|expired)$")] = None,
) -> dict[str, object]:
    access.farm_for(db, user, farm_id)
    stmt = select(AIRecommendation).where(AIRecommendation.farm_id == farm_id)
    if status:
        stmt = stmt.where(AIRecommendation.status == status)
    return crud.paginate(
        db, stmt.order_by(AIRecommendation.created_at.desc(), AIRecommendation.id.desc()), page
    )


@router.post("/recommendations/{rec_id}/respond", response_model=StoredRecommendation)
def respond(rec_id: int, body: RespondInput, user: CurrentUser, db: DbSession) -> AIRecommendation:
    """Record the farmer's decision. Accepted advice can later be marked applied."""
    rec, _ = access.record_for(db, user, AIRecommendation, rec_id, "Recommendation")
    allowed = {"pending": {"accepted", "rejected", "applied"}, "accepted": {"applied", "rejected"}}
    if body.status not in allowed.get(rec.status, set()):
        raise ConflictError(f"A {rec.status} recommendation cannot be marked {body.status}.")
    before = rec.status
    svc.respond(db, rec, user, body.status)
    crud.audit(db, "update", rec, {"status": [before, body.status]})
    db.commit()
    db.refresh(rec)
    return rec
