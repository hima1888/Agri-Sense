"""Recommendations: gather this farm's data, run the rules, persist with de-duplication and expiry."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import growth as growth_model
from app.domain import recommend_rules as rules
from app.models import (
    AIRecommendation,
    DiseaseDetection,
    Farm,
    FarmZone,
    ModelVersion,
    Sensor,
    SensorReading,
    User,
    WeatherData,
)
from app.services import soil, weather

DISEASE_LOOKBACK = timedelta(days=14)


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def gather(db: Session, farm: Farm, now: datetime) -> rules.FarmContext:
    tz = ZoneInfo(farm.timezone)
    rows = db.scalars(
        select(WeatherData)
        .where(
            WeatherData.farm_id == farm.id,
            WeatherData.kind == "forecast",
            WeatherData.valid_at >= now - timedelta(hours=1),
            WeatherData.valid_at < now + timedelta(hours=72),
        )
        .order_by(WeatherData.valid_at)
    ).all()
    hourly = [
        {
            "valid_at": r.valid_at,
            "local_hour": r.valid_at.astimezone(tz).hour,
            "temperature_c": _f(r.temperature_c),
            "relative_humidity_pct": _f(r.relative_humidity_pct),
            "precipitation_mm": _f(r.precipitation_mm),
            "precipitation_probability_pct": _f(r.precipitation_probability_pct),
            "wind_speed_ms": _f(r.wind_speed_ms),
        }
        for r in rows
    ]
    daily = [d for d in weather.daily_summary(list(rows), tz) if d["date"] >= now.astimezone(tz).date()]

    zones = db.scalars(select(FarmZone).where(FarmZone.farm_id == farm.id).order_by(FarmZone.id)).all()
    disease = db.execute(
        select(DiseaseDetection, ModelVersion.model_name)
        .outerjoin(ModelVersion, ModelVersion.id == DiseaseDetection.model_version_id)
        .where(
            DiseaseDetection.farm_id == farm.id,
            DiseaseDetection.is_healthy.is_(False),
            DiseaseDetection.detected_at >= now - DISEASE_LOOKBACK,
        )
        .order_by(DiseaseDetection.detected_at.desc())
    ).all()
    last = (
        select(SensorReading.sensor_id, func.max(SensorReading.recorded_at).label("last_at"))
        .group_by(SensorReading.sensor_id)
        .subquery()
    )
    sensors = db.execute(
        select(Sensor, last.c.last_at)
        .outerjoin(last, last.c.sensor_id == Sensor.id)
        .where(Sensor.farm_id == farm.id, Sensor.status == "active")
    ).all()
    silent_cut = now - timedelta(hours=rules.SILENT_HOURS)

    ctx_zones = []
    for z in zones:
        ctx_zones.append(
            rules.ZoneContext(
                zone_id=z.id,
                zone_name=z.name,
                area_ha=_f(z.area_hectares),
                irrigation_method=z.irrigation_method,
                soil=soil.assess(db, z, now),
                recent_disease=[
                    {
                        "id": d.id,
                        "label": d.disease_label,
                        "confidence": float(d.confidence),
                        "detected_at": d.detected_at,
                        "model": name or "disease model",
                    }
                    for d, name in disease
                    if d.zone_id == z.id and (d.explanation or {}).get("outcome") == "possible_disease"
                ],
                stage=zone_stage(db, z.id, now.date()),
                silent_sensors=[
                    {"id": s.id, "name": s.name, "last_at": last_at}
                    for s, last_at in sensors
                    if s.zone_id == z.id and (last_at is None or last_at < silent_cut)
                ],
            )
        )
    return rules.FarmContext(farm.id, now, hourly, daily, weather.last_fetched_at(db, farm.id), ctx_zones)


def zone_stage(db: Session, zone_id: int, today: Any) -> dict[str, Any] | None:
    """Growth stage of the zone's growing crop cycle (FAO-56 based), or None if unknown/unsupported."""
    from app.models import Crop, CropCycle  # local: keeps this module's import list unchanged

    row = db.execute(
        select(CropCycle, Crop)
        .join(Crop, Crop.id == CropCycle.crop_id)
        .where(CropCycle.zone_id == zone_id, CropCycle.status == "growing", CropCycle.planted_on.is_not(None))
        .order_by(CropCycle.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    cycle, crop = row
    start, end = cycle.planted_on, cycle.expected_harvest_on
    if start is None:
        return None
    days = (end - start).days if end and end > start else crop.typical_cycle_days
    try:
        model = growth_model.stages(crop.common_name, days)
    except growth_model.UnsupportedCropError:
        return None
    at = growth_model.current(model, start, today)
    if not at or not at["stage_key"]:
        return None
    name = next(st["name"] for st in model["stages"] if st["key"] == at["stage_key"])
    return {"key": at["stage_key"], "name": name, "day": at["day"]}


def preview(db: Session, farm: Farm, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    ctx = gather(db, farm, now)
    recs = rules.generate(ctx)
    return {
        "farm_id": farm.id,
        "generated_at": now,
        "method": "rule-based (see docs/RECOMMENDATIONS.md); not a trained model",
        "weather_fetched_at": ctx.weather_fetched_at,
        "forecast_hours": len(ctx.hourly),
        "zones_assessed": len(ctx.zones),
        "recommendations": recs,
        "uses_simulated_data": any(r["uses_simulated_data"] for r in recs),
    }


def generate_and_store(db: Session, user: User, farm: Farm, now: datetime | None = None) -> dict[str, Any]:
    """Store new advice; refresh an identical pending one instead of duplicating; expire advice that no
    longer applies. Accepted/rejected/applied rows are history and are never changed."""
    now = now or datetime.now(UTC)
    result = preview(db, farm, now)
    pending = db.scalars(
        select(AIRecommendation).where(
            AIRecommendation.farm_id == farm.id, AIRecommendation.status == "pending"
        )
    ).all()
    by_key = {(r.zone_id, r.rule): r for r in pending if r.rule}
    seen: set[tuple[int | None, str | None]] = set()
    created = refreshed = 0
    for rec in result["recommendations"]:
        key = (rec["zone_id"], rec["rule"])
        seen.add(key)
        row = by_key.get(key)
        fields = {
            "category": rec["category"],
            "priority": rec["priority"],
            "title": rec["title"],
            "rationale": rec["rationale"],
            "action": soil.json_safe(rec["action"]),
            "expected_impact": soil.json_safe(rec["expected_impact"]),
            "confidence": Decimal(str(rec["confidence"])),
            "limitations": " ".join(rec["limitations"]),
            "factors": soil.json_safe(rec["factors"]),
            "expires_at": rec["expires_at"],
        }
        if row is None:
            row = AIRecommendation(farm_id=farm.id, zone_id=rec["zone_id"], rule=rec["rule"], **fields)
            db.add(row)
            created += 1
        else:
            for k, v in fields.items():
                setattr(row, k, v)
            refreshed += 1
        db.flush()
        rec["id"] = row.id
    expired = 0
    for key, row in by_key.items():
        if key not in seen or (row.expires_at and row.expires_at < now):
            row.status = "expired"
            expired += 1
    db.flush()
    return {**result, "stored": {"created": created, "refreshed": refreshed, "expired": expired}}


def respond(db: Session, rec: AIRecommendation, user: User, status: str, now: datetime | None = None) -> None:
    rec.status = status
    rec.responded_at = now or datetime.now(UTC)
    rec.responded_by = user.id
