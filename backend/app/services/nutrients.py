# ruff: noqa: E501  (compact row dictionaries)
"""Fertilizer planning and chemical-use tracking (Phase 13): data gathering around the pure domain rules."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.domain import chemicals, nutrients
from app.integrations.open_meteo import SOURCE as WEATHER_SOURCE
from app.models import (
    Crop,
    CropCycle,
    DiseaseDetection,
    FarmZone,
    FertilizerApplication,
    PesticideApplication,
    WeatherData,
)
from app.services import soil

ACTIVE = ("growing", "planned")


def current_cycle(db: Session, zone: FarmZone) -> tuple[CropCycle, Crop] | None:
    order = case((CropCycle.status == "growing", 0), else_=1)
    row = db.execute(
        select(CropCycle, Crop)
        .join(Crop, Crop.id == CropCycle.crop_id)
        .where(CropCycle.zone_id == zone.id, CropCycle.status.in_(ACTIVE))
        .order_by(order, CropCycle.id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def previous_cycle(db: Session, zone: FarmZone, before: CropCycle) -> CropCycle | None:
    return db.scalars(
        select(CropCycle)
        .where(
            CropCycle.zone_id == zone.id,
            CropCycle.status.in_(("harvested", "failed")),
            CropCycle.id != before.id,
        )
        .order_by(CropCycle.harvested_on.desc().nulls_last(), CropCycle.id.desc())
        .limit(1)
    ).first()


def _area(cycle: CropCycle | None, zone: FarmZone) -> float | None:
    a = (cycle.area_hectares if cycle else None) or zone.area_hectares
    return float(a) if a else None


def _cycle_filter(
    model: type[FertilizerApplication] | type[PesticideApplication], zone: FarmZone, cycle: CropCycle
) -> Any:
    """Records linked to the cycle, or unlinked records in the zone since planting."""
    unlinked = and_(model.crop_cycle_id.is_(None), model.zone_id == zone.id)
    if cycle.planted_on:
        start = datetime.combine(cycle.planted_on, datetime.min.time(), UTC)
        unlinked = and_(unlinked, model.applied_at >= start)
    if cycle.harvested_on:
        end = datetime.combine(cycle.harvested_on + timedelta(days=1), datetime.min.time(), UTC)
        unlinked = and_(unlinked, model.applied_at < end)
    return or_(model.crop_cycle_id == cycle.id, unlinked)


def nutrient_plan(db: Session, zone: FarmZone, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cc = current_cycle(db, zone)
    if cc is None:
        return {"zone_id": zone.id, "zone_name": zone.name, "status": "no_crop", "crop": None, "cycle_id": None,
                "message": "No planned or growing crop cycle in this zone; add one to plan fertilizer."}  # fmt: skip
    cycle, crop = cc
    area = _area(cycle, zone)
    assessment = soil.assess(db, zone, now)
    apps = db.scalars(
        select(FertilizerApplication).where(_cycle_filter(FertilizerApplication, zone, cycle))
    ).all()
    rows = [
        {"quantity_kg": a.quantity_kg, "n_pct": a.n_pct, "p_pct": a.p_pct, "k_pct": a.k_pct} for a in apps
    ]
    applied = nutrients.applied_nutrients(rows, area) if area else {"n": 0.0, "p2o5": 0.0, "k2o": 0.0}
    t = cycle.nutrient_target
    target = {k: float(t[k]) for k in ("n", "p2o5", "k2o")} if t else None
    result = nutrients.plan(
        crop=crop.common_name,
        target=target,
        target_source=(t or {}).get("source") or ("recorded for this crop cycle" if t else None),
        soil_ratings=assessment["components"],
        applied_kg_ha=applied,
        area_ha=area,
        irrigation_method=zone.irrigation_method,
    )
    if apps and not area:
        result.setdefault("limitations", []).append(
            f"{len(apps)} logged application(s) could not be converted to kg/ha: the zone area is unknown."
        )
    return {
        "zone_id": zone.id,
        "zone_name": zone.name,
        "crop": crop.common_name,
        "cycle_id": cycle.id,
        "area_hectares": area,
        "target_is_custom": t is not None,
        "applications_counted": len(apps),
        "lab_test_age_days": assessment["inputs"]["lab_test_age_days"],
        "uses_simulated_data": assessment["uses_simulated_data"],
        **result,
    }


def _pesticides(db: Session, zone: FarmZone, cycle: CropCycle) -> list[dict[str, Any]]:
    apps = db.scalars(
        select(PesticideApplication)
        .where(_cycle_filter(PesticideApplication, zone, cycle))
        .order_by(PesticideApplication.applied_at)
    ).all()
    return [
        {
            "id": a.id,
            "product_name": a.product_name,
            "pesticide_type": a.pesticide_type,
            "quantity": a.quantity,
            "quantity_unit": a.quantity_unit,
            "applied_at": a.applied_at,
            "disease_detection_id": a.disease_detection_id,
            "pre_harvest_interval_days": a.pre_harvest_interval_days,
            "target": a.target,
        }
        for a in apps
    ]


def chemical_use(db: Session, zone: FarmZone, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cc = current_cycle(db, zone)
    if cc is None:
        return {
            "zone_id": zone.id,
            "status": "no_crop",
            "message": "No planned or growing crop cycle in this zone.",
        }
    cycle, crop = cc
    area = _area(cycle, zone)
    cur_apps = _pesticides(db, zone, cycle)
    current = chemicals.use_summary(cur_apps, area, cycle.expected_harvest_on, now.date())
    prev = previous_cycle(db, zone, cycle)
    previous = None
    comparison = None
    if prev is not None:
        prev_area = _area(prev, zone)
        previous = chemicals.use_summary(
            _pesticides(db, zone, prev), prev_area, prev.harvested_on, now.date()
        )
        previous["cycle_id"] = prev.id
        comparison = chemicals.compare(current, previous, area, prev_area)
    return {
        "zone_id": zone.id,
        "zone_name": zone.name,
        "crop": crop.common_name,
        "cycle_id": cycle.id,
        "status": "ok",
        "current": current,
        "recent": cur_apps[-10:][::-1],
        "previous": previous,
        "comparison": comparison,
        "basis": "computed from this farm's pesticide logs; comparison is per hectare against the zone's previous cycle",
    }


def spray_check(
    db: Session, zone: FarmZone, pesticide_type: str, phi_days: int | None, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cc = current_cycle(db, zone)
    since = now - timedelta(days=chemicals.EVIDENCE_DAYS)
    dets = db.scalars(
        select(DiseaseDetection)
        .where(DiseaseDetection.zone_id == zone.id, DiseaseDetection.detected_at >= since)
        .order_by(DiseaseDetection.detected_at.desc())
    ).all()
    evidence = [
        {"id": d.id, "label": d.disease_label, "detected_at": d.detected_at, "outcome": (d.explanation or {}).get("outcome", "")}
        for d in dets
        if not d.is_healthy and (d.explanation or {}).get("outcome") in ("possible_disease", "uncertain")
    ]  # fmt: skip
    weather = db.scalars(
        select(WeatherData).where(
            WeatherData.farm_id == zone.farm_id, WeatherData.source == WEATHER_SOURCE, WeatherData.kind == "forecast",
            WeatherData.valid_at >= now - timedelta(hours=1), WeatherData.valid_at < now + timedelta(hours=6),
        )
    ).all()  # fmt: skip
    hourly = [
        {
            "valid_at": w.valid_at,
            "precipitation_probability_pct": None
            if w.precipitation_probability_pct is None
            else float(w.precipitation_probability_pct),
            "precipitation_mm": None if w.precipitation_mm is None else float(w.precipitation_mm),
            "wind_speed_ms": None if w.wind_speed_ms is None else float(w.wind_speed_ms),
            "temperature_c": None if w.temperature_c is None else float(w.temperature_c),
        }
        for w in weather
    ]
    recent = db.scalars(
        select(PesticideApplication.applied_at).where(
            PesticideApplication.zone_id == zone.id,
            PesticideApplication.pesticide_type == pesticide_type,
            PesticideApplication.applied_at >= now - timedelta(days=chemicals.REPEAT_DAYS),
        )
    ).all()
    result = chemicals.spray_check(
        pesticide_type=pesticide_type,
        phi_days=phi_days,
        now=now,
        expected_harvest=cc[0].expected_harvest_on if cc else None,
        evidence=evidence,
        hourly=hourly,
        recent_same_type=list(recent),
    )
    return {"zone_id": zone.id, "pesticide_type": pesticide_type, "evidence": evidence[:3], **result}
