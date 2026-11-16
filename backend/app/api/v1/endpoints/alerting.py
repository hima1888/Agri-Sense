"""Automatic alert endpoints (Phase 17). Listing, acknowledging and resolving alerts stay in operations."""

from typing import Annotated, Any

from fastapi import APIRouter, Request
from pydantic import Field, field_validator

from app.api.auth import CurrentUser
from app.api.deps import DbSession
from app.domain import alert_rules as rules
from app.schemas.common import InputModel
from app.services import access, alerting, crud, soil

router = APIRouter(tags=["alerts"])


class AlertSettingsInput(InputModel):
    disabled_rules: list[str] = Field(default_factory=list)
    thresholds: dict[str, Annotated[float, Field(ge=-50, le=10_000)]] = Field(default_factory=dict)

    @field_validator("disabled_rules")
    @classmethod
    def _known_rules(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - set(rules.RULES))
        if unknown:
            raise ValueError(f"unknown rules: {', '.join(unknown)}")
        return sorted(set(v))

    @field_validator("thresholds")
    @classmethod
    def _known_thresholds(cls, v: dict[str, float]) -> dict[str, float]:
        unknown = sorted(set(v) - set(rules.DEFAULTS))
        if unknown:
            raise ValueError(f"unknown thresholds: {', '.join(unknown)}")
        return v


@router.post("/farms/{farm_id}/alerts/evaluate")
def evaluate(farm_id: int, request: Request, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Run the alert rules for this farm now (the background evaluator also runs them every few minutes)."""
    farm = access.farm_for(db, user, farm_id)
    result = alerting.evaluate_farm(db, farm)
    db.commit()
    for e in result["events"]:
        request.app.state.broadcaster.publish(farm.id, alerting.ALERT_EVENT, e)
    return soil.json_safe(result)  # type: ignore[no-any-return]


@router.get("/farms/{farm_id}/alert-settings")
def get_settings(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return alerting.settings_view(access.farm_for(db, user, farm_id))


@router.put("/farms/{farm_id}/alert-settings")
def put_settings(farm_id: int, body: AlertSettingsInput, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Turn rules on/off and override thresholds. Takes effect at the next evaluation."""
    farm = access.farm_for(db, user, farm_id)
    before = farm.alert_settings
    farm.alert_settings = body.model_dump()
    crud.audit(db, "update", farm, {"alert_settings": [before, farm.alert_settings]})
    db.commit()
    return alerting.settings_view(farm)
