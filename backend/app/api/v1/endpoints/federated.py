"""Federated learning endpoints (Phase 15)."""

from typing import Annotated, Any

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select

from app.api.auth import AdminUser, CurrentUser
from app.api.deps import DbSession
from app.api.errors import NotFoundError
from app.models import FederatedLearningRun
from app.schemas.common import InputModel
from app.services import access, crud, soil
from app.services import federated as svc

router = APIRouter(tags=["federated learning"])


class RunConfig(InputModel):
    rounds: Annotated[int, Field(ge=1, le=200)] = 20
    local_steps: Annotated[int, Field(ge=1, le=100)] = 5
    lr: Annotated[float, Field(gt=0, le=1)] = 0.05
    l2: Annotated[float, Field(ge=0, le=1)] = 0.001


@router.get("/farms/{farm_id}/federated")
def farm_federated(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """This farm's enrollment, what it shares, its local sample count and its results in recent runs."""
    farm = access.farm_for(db, user, farm_id)
    return soil.json_safe(svc.farm_view(db, farm, user.role == "admin"))  # type: ignore[no-any-return]


@router.post("/farms/{farm_id}/federated/enroll")
def enroll(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Opt the farm in: future runs train on its data locally and receive only its model update."""
    farm = access.farm_for(db, user, farm_id)
    c = svc.enroll(db, farm)
    crud.audit(db, "update", farm, {"federated": "enrolled"})
    db.commit()
    return {"farm_id": farm.id, "status": c.status}


@router.post("/farms/{farm_id}/federated/leave")
def leave(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Opt out of future runs. Past runs keep the aggregated model; no raw data was ever collected."""
    farm = access.farm_for(db, user, farm_id)
    c = svc.leave(db, farm)
    crud.audit(db, "update", farm, {"federated": "left"})
    db.commit()
    return {"farm_id": farm.id, "status": c.status if c else "not_enrolled"}


@router.post("/federated/runs", status_code=201)
def start_run(body: RunConfig, admin: AdminUser, db: DbSession) -> dict[str, Any]:
    """Admin: FedAvg over all active enrolled farms; fails (and says why) with < 2 eligible farms."""
    run = svc.start_run(db, body.model_dump())
    crud.audit(db, "create", run, {"status": run.status})
    db.commit()
    db.refresh(run)
    return soil.json_safe(svc.run_summary(run, admin=True))  # type: ignore[no-any-return]


@router.get("/federated/runs")
def list_runs(admin: AdminUser, db: DbSession) -> list[dict[str, Any]]:
    runs = db.scalars(select(FederatedLearningRun).order_by(FederatedLearningRun.id.desc()).limit(50)).all()
    return soil.json_safe([svc.run_summary(r, admin=True) for r in runs])  # type: ignore[no-any-return]


@router.get("/federated/runs/{run_id}")
def get_run(run_id: int, admin: AdminUser, db: DbSession) -> dict[str, Any]:
    run = db.get(FederatedLearningRun, run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} not found.")
    return soil.json_safe(svc.run_summary(run, admin=True))  # type: ignore[no-any-return]


@router.get("/zones/{zone_id}/federated/forecast")
def zone_forecast(zone_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """6-h moisture forecast from the latest federated model, with its error vs a no-change baseline."""
    return soil.json_safe(svc.zone_forecast(db, access.zone_for(db, user, zone_id)))  # type: ignore[no-any-return]
