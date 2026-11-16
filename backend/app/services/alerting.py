# ruff: noqa: E501  (compact dictionaries)
"""Automatic alerts (Phase 17): snapshot a farm, evaluate the rules, reconcile with open alerts.

Reconciliation (only for alerts this service created, marked context.source == "rule"):
* condition true, no open alert with its key  -> raise a new alert
* condition true, open alert exists           -> keep it; update severity/message if they changed
* open rule alert whose condition is now false -> resolve it automatically (context.auto_resolved)
Manual alerts are never touched. Acknowledged alerts stay acknowledged while the condition persists.
"""

from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.domain import alert_rules as rules
from app.integrations.open_meteo import SOURCE as WEATHER_SOURCE
from app.models import (
    Alert,
    DiseaseDetection,
    Farm,
    FarmZone,
    ModelVersion,
    Sensor,
    SensorReading,
    WeatherData,
)
from app.services import soil
from app.services.weather import daily_summary

ALERT_EVENT = "alert"


def _safe(obj: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], soil.json_safe(obj))


OPEN = ("open", "acknowledged")


def snapshot(db: Session, farm: Farm, now: datetime) -> rules.Snapshot:
    zones: Sequence[FarmZone] = db.scalars(
        select(FarmZone).where(FarmZone.farm_id == farm.id).order_by(FarmZone.id)
    ).all()
    zone_rows = []
    for z in zones:
        a = soil.assess(db, z, now)
        zone_rows.append(
            {"id": z.id, "name": z.name, "water": a.get("water"), "simulated": a["uses_simulated_data"]}
        )

    hour_ago = now - timedelta(hours=1)
    last = (
        select(SensorReading.sensor_id, func.max(SensorReading.recorded_at).label("last_at"))
        .group_by(SensorReading.sensor_id)
        .subquery()
    )
    recent = (
        select(
            SensorReading.sensor_id,
            func.count().label("total"),
            func.count().filter(SensorReading.quality != "good").label("bad"),
        )
        .where(SensorReading.recorded_at >= hour_ago)
        .group_by(SensorReading.sensor_id)
        .subquery()
    )
    sensor_rows = db.execute(
        select(Sensor, last.c.last_at, recent.c.total, recent.c.bad)
        .outerjoin(last, last.c.sensor_id == Sensor.id)
        .outerjoin(recent, recent.c.sensor_id == Sensor.id)
        .where(Sensor.farm_id == farm.id, Sensor.status == "active")
    ).all()
    sensors = [{"id": s.id, "name": s.name, "zone_id": s.zone_id, "last_at": last_at, "recent_total": total or 0, "recent_bad": bad or 0,
                "simulated": s.source == "simulated"} for s, last_at, total, bad in sensor_rows]  # fmt: skip

    tz = ZoneInfo(farm.timezone)
    midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    weather = db.scalars(
        select(WeatherData).where(WeatherData.farm_id == farm.id, WeatherData.source == WEATHER_SOURCE, WeatherData.kind == "forecast",
                                  WeatherData.valid_at >= midnight.astimezone(UTC), WeatherData.valid_at < now + timedelta(days=3))
        .order_by(WeatherData.valid_at)
    ).all()  # fmt: skip
    hourly = [{"valid_at": w.valid_at, "temperature_c": None if w.temperature_c is None else float(w.temperature_c),
               "precipitation_mm": float(w.precipitation_mm or 0), "wind_speed_ms": None if w.wind_speed_ms is None else float(w.wind_speed_ms)} for w in weather]  # fmt: skip
    daily = daily_summary(list(weather), tz)

    dets = db.execute(
        select(DiseaseDetection, ModelVersion.model_name)
        .outerjoin(ModelVersion, ModelVersion.id == DiseaseDetection.model_version_id)
        .where(
            DiseaseDetection.farm_id == farm.id,
            DiseaseDetection.is_healthy.is_(False),
            DiseaseDetection.detected_at >= now - timedelta(days=14),
        )
    ).all()
    disease = [{"id": d.id, "zone_id": d.zone_id, "label": d.disease_label, "detected_at": d.detected_at, "model": name or "disease model"}
               for d, name in dets if (d.explanation or {}).get("outcome") == "possible_disease"]  # fmt: skip
    return rules.Snapshot(now, zone_rows, sensors, hourly, daily, disease)


def _context(c: rules.Condition) -> dict[str, Any]:
    return _safe(
        {
            "source": "rule",
            "rule": c.rule,
            "key": c.key,
            "values": c.values,
            "rule_description": rules.RULES[c.rule],
        }
    )


def evaluate_farm(db: Session, farm: Farm, now: datetime | None = None) -> dict[str, Any]:
    """Reconcile rule alerts for one farm. Caller commits, then publishes ``result['events']``."""
    now = now or datetime.now(UTC)
    conditions = rules.evaluate(snapshot(db, farm, now), farm.alert_settings)
    existing = db.scalars(
        select(Alert).where(
            Alert.farm_id == farm.id, Alert.status.in_(OPEN), Alert.context["source"].astext == "rule"
        )
    ).all()
    by_key = {(a.context or {}).get("key"): a for a in existing}
    events: list[dict[str, Any]] = []
    raised = updated = resolved = 0
    seen = set()
    for c in conditions:
        seen.add(c.key)
        a = by_key.get(c.key)
        if a is None:
            a = Alert(farm_id=farm.id, zone_id=c.zone_id, sensor_id=c.sensor_id, severity=c.severity, category=c.category,
                      status="open", title=c.title, message=c.message, context=_context(c), triggered_at=now)  # fmt: skip
            db.add(a)
            db.flush()
            raised += 1
            events.append({"type": "raised", "alert": _summary(a)})
        elif a.severity != c.severity or a.message != c.message or a.title != c.title:
            escalated = rules_rank(c.severity) > rules_rank(a.severity)
            a.severity, a.title, a.message, a.context = c.severity, c.title, c.message, _context(c)
            updated += 1
            if escalated:
                events.append({"type": "escalated", "alert": _summary(a)})
    for key, a in by_key.items():
        if key not in seen:
            a.status = "resolved"
            a.resolved_at = now
            a.context = {
                **(a.context or {}),
                "auto_resolved": True,
                "resolved_reason": "condition no longer true",
            }
            resolved += 1
            events.append({"type": "resolved", "alert": _summary(a)})
    db.flush()
    return {"farm_id": farm.id, "evaluated_at": now, "conditions": [asdict(c) for c in conditions], "raised": raised, "updated": updated,
            "resolved": resolved, "events": events}  # fmt: skip


def rules_rank(severity: str) -> int:
    return {"info": 0, "warning": 1, "critical": 2}.get(severity, 0)


def _summary(a: Alert) -> dict[str, Any]:
    return _safe({"id": a.id, "severity": a.severity, "category": a.category, "status": a.status, "title": a.title,
                           "message": a.message, "zone_id": a.zone_id, "triggered_at": a.triggered_at})  # fmt: skip


def settings_view(farm: Farm) -> dict[str, Any]:
    s = farm.alert_settings or {}
    return {
        "rules": [
            {"rule": k, "description": v, "enabled": k not in set(s.get("disabled_rules") or [])}
            for k, v in rules.RULES.items()
        ],
        "thresholds": {k: float((s.get("thresholds") or {}).get(k, v)) for k, v in rules.DEFAULTS.items()},
        "defaults": rules.DEFAULTS,
    }


def farms_to_evaluate(db: Session) -> Sequence[Farm]:
    """Farms with at least one zone or sensor (nothing to watch otherwise)."""
    has_zone = select(FarmZone.id).where(FarmZone.farm_id == Farm.id).exists()
    has_sensor = select(Sensor.id).where(and_(Sensor.farm_id == Farm.id, Sensor.status == "active")).exists()
    return db.scalars(select(Farm).where(has_zone | has_sensor).order_by(Farm.id)).all()
