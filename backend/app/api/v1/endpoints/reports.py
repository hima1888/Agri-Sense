# ruff: noqa: E501  (compact dictionaries)
"""Analytics and reports (Phase 16)."""

import csv
import io
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Response
from pydantic import Field, model_validator
from sqlalchemy import select

from app.api.auth import CurrentUser
from app.api.deps import DbSession, Paging, no_content
from app.api.errors import UnprocessableError
from app.models import Report
from app.schemas.common import InputModel
from app.services import access, crud, soil
from app.services import analytics as svc

router = APIRouter(tags=["analytics & reports"])

SUSTAINABILITY_KEYS = (
    "farm_id",
    "farm_name",
    "period",
    "previous_period",
    "area_ha",
    "indicators",
    "mean_stress_share",
    "notes",
    "uses_simulated_data",
)


def _check_range(start: date, end: date) -> None:
    if end < start:
        raise UnprocessableError("end must be on or after start.")
    if (end - start).days + 1 > svc.MAX_DAYS:
        raise UnprocessableError(f"A period can be at most {svc.MAX_DAYS} days.")


@router.get("/farms/{farm_id}/analytics")
def farm_analytics(
    farm_id: int,
    user: CurrentUser,
    db: DbSession,
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
) -> dict[str, Any]:
    """Metrics for the period (default: last 30 days) with the previous period of equal length for comparison."""
    farm = access.farm_for(db, user, farm_id)
    end = end or datetime.now(ZoneInfo(farm.timezone)).date()  # the farm's "today", not UTC's
    start = start or end - timedelta(days=29)
    _check_range(start, end)
    return soil.json_safe(svc.analytics(db, farm, start, end))  # type: ignore[no-any-return]


class ReportCreate(InputModel):
    report_type: Literal["farm_summary", "sustainability"]
    period_start: date
    period_end: date
    title: Annotated[str, Field(min_length=3, max_length=120)] | None = None

    @model_validator(mode="after")
    def _order(self) -> "ReportCreate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


def _report_out(r: Report, with_content: bool = True) -> dict[str, Any]:
    out = {"id": r.id, "farm_id": r.farm_id, "report_type": r.report_type, "title": r.title, "status": r.status,
           "period_start": r.period_start, "period_end": r.period_end, "created_at": r.created_at, "completed_at": r.completed_at}  # fmt: skip
    if with_content:
        out["content"] = r.content
    return soil.json_safe(out)  # type: ignore[no-any-return]


@router.post("/farms/{farm_id}/reports", status_code=201)
def create_report(farm_id: int, body: ReportCreate, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Generate and store a report snapshot. Later edits to records do not change a saved report."""
    farm = access.farm_for(db, user, farm_id)
    _check_range(body.period_start, body.period_end)
    data = svc.analytics(db, farm, body.period_start, body.period_end)
    content = data if body.report_type == "farm_summary" else {k: data[k] for k in SUSTAINABILITY_KEYS}
    label = "Farm summary" if body.report_type == "farm_summary" else "Sustainability indicators"
    r = Report(
        farm_id=farm.id, created_by=user.id, report_type=body.report_type,
        title=body.title or f"{label}: {farm.name}, {body.period_start:%d %b %Y} to {body.period_end:%d %b %Y}",
        period_start=body.period_start, period_end=body.period_end, status="ready",
        content=soil.json_safe(content), completed_at=datetime.now(UTC),
    )  # fmt: skip
    db.add(r)
    db.flush()
    crud.audit(db, "create", r, {"report_type": r.report_type})
    db.commit()
    db.refresh(r)
    return _report_out(r)


@router.get("/farms/{farm_id}/reports")
def list_reports(farm_id: int, user: CurrentUser, db: DbSession, page: Paging) -> dict[str, object]:
    access.farm_for(db, user, farm_id)
    stmt = (
        select(Report).where(Report.farm_id == farm_id).order_by(Report.created_at.desc(), Report.id.desc())
    )
    p = crud.paginate(db, stmt, page)
    p["items"] = [_report_out(r, with_content=False) for r in p["items"]]
    return p


def _report(db: DbSession, user: CurrentUser, report_id: int) -> Report:
    r, _ = access.record_for(db, user, Report, report_id, "Report")
    return r


@router.get("/reports/{report_id}")
def get_report(report_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return _report_out(_report(db, user, report_id))


@router.get("/reports/{report_id}/csv")
def report_csv(report_id: int, user: CurrentUser, db: DbSession) -> Response:
    """The report as CSV (section, metric, value), for spreadsheets."""
    r = _report(db, user, report_id)
    buf = io.StringIO()
    csv.writer(buf).writerows(svc.csv_rows(r.content or {}))
    name = f"agri-sense-report-{r.id}-{r.period_start}-{r.period_end}.csv"
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: int, user: CurrentUser, db: DbSession) -> Response:
    r = _report(db, user, report_id)
    crud.audit(db, "delete", r)
    db.delete(r)
    db.commit()
    return no_content()
