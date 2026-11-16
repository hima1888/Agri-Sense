"""Aggregations for the farm dashboard. Everything is computed from stored records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, literal, select, text, union_all
from sqlalchemy.orm import Session

from app.api.errors import UnprocessableError
from app.models import (
    Alert,
    Crop,
    CropCycle,
    Farm,
    FarmZone,
    FertilizerApplication,
    IrrigationEvent,
    PesticideApplication,
    Sensor,
    SensorReading,
)
from app.services import readings as readings_service

REPORTING_WINDOW = timedelta(minutes=15)
ZONE_KEY_TYPES = ("soil_moisture", "temperature", "humidity", "soil_ph")


def summary(db: Session, farm: Farm, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    day_ago, week_ago = now - timedelta(hours=24), now - timedelta(days=7)

    zones = list(db.scalars(select(FarmZone).where(FarmZone.farm_id == farm.id).order_by(FarmZone.id)))
    sensors = list(db.scalars(select(Sensor).where(Sensor.farm_id == farm.id)))
    latest = readings_service.latest_per_sensor(db, farm.id)

    # Active crop cycle per zone (most recent growing/planned).
    cycles = db.execute(
        select(CropCycle, Crop.common_name)
        .join(Crop, Crop.id == CropCycle.crop_id)
        .join(FarmZone, FarmZone.id == CropCycle.zone_id)
        .where(FarmZone.farm_id == farm.id, CropCycle.status.in_(["growing", "planned"]))
        .order_by(CropCycle.zone_id, case((CropCycle.status == "growing", 0), else_=1), CropCycle.id.desc())
    ).all()
    cycle_by_zone: dict[int, dict[str, Any]] = {}
    for cycle, crop_name in cycles:
        cycle_by_zone.setdefault(
            cycle.zone_id,
            {
                "id": cycle.id,
                "crop_name": crop_name,
                "variety": cycle.variety,
                "status": cycle.status,
                "planted_on": cycle.planted_on,
                "expected_harvest_on": cycle.expected_harvest_on,
            },
        )

    zone_out = []
    for z in zones:
        zone_sensors = [s for s in sensors if s.zone_id == z.id]
        key_values: dict[str, Any] = {}
        for t in ZONE_KEY_TYPES:
            vals = [latest[s.id] for s in zone_sensors if s.sensor_type == t and s.id in latest]
            good = [r for r in vals if r.quality == "good"]
            if good:
                newest = max(good, key=lambda r: r.recorded_at)
                key_values[t] = {
                    "value": round(sum(r.value for r in good) / len(good), 2),
                    "recorded_at": newest.recorded_at,
                    "unit": next(s.unit for s in zone_sensors if s.sensor_type == t),
                }
        zone_out.append(
            {
                "id": z.id,
                "name": z.name,
                "zone_type": z.zone_type,
                "area_hectares": float(z.area_hectares) if z.area_hectares is not None else None,
                "irrigation_method": z.irrigation_method,
                "sensor_count": len(zone_sensors),
                "active_cycle": cycle_by_zone.get(z.id),
                "latest": key_values,
            }
        )

    reporting = sum(1 for s in sensors if s.last_reading_at and now - s.last_reading_at <= REPORTING_WINDOW)
    sensor_out = {
        "total": len(sensors),
        "active": sum(1 for s in sensors if s.status == "active"),
        "simulated": sum(1 for s in sensors if s.source == "simulated"),
        "hardware": sum(1 for s in sensors if s.source == "hardware"),
        "reporting": reporting,
    }

    sev_rows = db.execute(
        select(Alert.severity, func.count())
        .where(Alert.farm_id == farm.id, Alert.status != "resolved")
        .group_by(Alert.severity)
    ).all()
    by_severity = {"info": 0, "warning": 0, "critical": 0} | {str(s): int(n) for s, n in sev_rows}
    recent_alerts = list(
        db.scalars(
            select(Alert)
            .where(Alert.farm_id == farm.id, Alert.status != "resolved")
            .order_by(
                case((Alert.severity == "critical", 0), (Alert.severity == "warning", 1), else_=2),
                Alert.triggered_at.desc(),
            )
            .limit(5)
        )
    )

    zone_ids = select(FarmZone.id).where(FarmZone.farm_id == farm.id).scalar_subquery()
    irrigation = select(
        literal("irrigation").label("kind"),
        IrrigationEvent.id,
        IrrigationEvent.zone_id,
        func.coalesce(
            IrrigationEvent.started_at, IrrigationEvent.scheduled_for, IrrigationEvent.created_at
        ).label("at"),
        IrrigationEvent.method.label("title"),
        IrrigationEvent.volume_liters.label("amount"),
        literal("L").label("unit"),
        IrrigationEvent.status.label("status"),
    ).where(IrrigationEvent.zone_id.in_(zone_ids))
    fertilizer = select(
        literal("fertilizer"),
        FertilizerApplication.id,
        FertilizerApplication.zone_id,
        FertilizerApplication.applied_at,
        FertilizerApplication.product_name,
        FertilizerApplication.quantity_kg,
        literal("kg"),
        literal("applied"),
    ).where(FertilizerApplication.zone_id.in_(zone_ids))
    pesticide = select(
        literal("pesticide"),
        PesticideApplication.id,
        PesticideApplication.zone_id,
        PesticideApplication.applied_at,
        PesticideApplication.product_name,
        PesticideApplication.quantity,
        PesticideApplication.quantity_unit,
        literal("applied"),
    ).where(PesticideApplication.zone_id.in_(zone_ids))
    activity_q = union_all(irrigation, fertilizer, pesticide).subquery()
    activity = [
        {
            "kind": r.kind,
            "id": r.id,
            "zone_id": r.zone_id,
            "at": r.at,
            "title": r.title,
            "amount": float(r.amount) if r.amount is not None else None,
            "unit": r.unit,
            "status": r.status,
        }
        for r in db.execute(select(activity_q).order_by(activity_q.c.at.desc().nulls_last()).limit(8)).all()
    ]

    water = db.execute(
        select(func.coalesce(func.sum(IrrigationEvent.volume_liters), 0), func.count()).where(
            IrrigationEvent.zone_id.in_(zone_ids),
            IrrigationEvent.status.in_(["running", "completed"]),
            IrrigationEvent.started_at >= week_ago,
        )
    ).one()

    sensor_ids = select(Sensor.id).where(Sensor.farm_id == farm.id).scalar_subquery()
    counts = db.execute(
        select(func.count(), func.count().filter(SensorReading.quality != "good")).where(
            SensorReading.sensor_id.in_(sensor_ids), SensorReading.recorded_at >= day_ago
        )
    ).one()
    stats = db.execute(
        select(
            Sensor.sensor_type,
            func.min(Sensor.unit),
            func.min(SensorReading.value),
            func.max(SensorReading.value),
            func.avg(SensorReading.value),
            func.count(),
        )
        .join(Sensor, Sensor.id == SensorReading.sensor_id)
        .where(
            Sensor.farm_id == farm.id, SensorReading.recorded_at >= day_ago, SensorReading.quality == "good"
        )
        .group_by(Sensor.sensor_type)
        .order_by(Sensor.sensor_type)
    ).all()

    return {
        "farm_id": farm.id,
        "generated_at": now,
        "zones": zone_out,
        "sensors": sensor_out,
        "alerts": {"open": sum(by_severity.values()), "by_severity": by_severity, "recent": recent_alerts},
        "activity": activity,
        "water_7d": {"liters": float(water[0] or 0), "events": int(water[1])},
        "readings_24h": {"count": int(counts[0]), "not_good": int(counts[1])},
        "stats_24h": [
            {"sensor_type": t, "unit": u, "min": mn, "max": mx, "avg": round(float(av), 3), "count": n}
            for t, u, mn, mx, av, n in stats
        ],
    }


def auto_bucket_minutes(hours: int) -> int:
    if hours <= 6:
        return 5
    if hours <= 48:
        return 15
    if hours <= 7 * 24:
        return 60
    return 180


def series(
    db: Session,
    farm: Farm,
    sensor_type: str,
    hours: int,
    bucket_minutes: int | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Per-zone bucketed averages (min/max envelope) for one sensor type. Good-quality readings only."""
    now = now or datetime.now(UTC)
    bucket = bucket_minutes or auto_bucket_minutes(hours)
    if hours * 60 / bucket > 2_000:
        raise UnprocessableError("Too many points: use a larger bucket or a shorter range.")
    start = now - timedelta(hours=hours)
    bucket_expr = func.date_bin(
        text(f"interval '{int(bucket)} minutes'"), SensorReading.recorded_at, text("TIMESTAMPTZ '2000-01-01'")
    )
    rows = db.execute(
        select(
            Sensor.zone_id,
            bucket_expr.label("t"),
            func.avg(SensorReading.value),
            func.min(SensorReading.value),
            func.max(SensorReading.value),
            func.count(),
        )
        .join(Sensor, Sensor.id == SensorReading.sensor_id)
        .where(
            and_(
                Sensor.farm_id == farm.id,
                Sensor.sensor_type == sensor_type,
                SensorReading.recorded_at >= start,
                SensorReading.recorded_at <= now,
                SensorReading.quality == "good",
            )
        )
        .group_by(Sensor.zone_id, "t")
        .order_by(Sensor.zone_id, "t")
    ).all()
    meta = db.execute(
        select(func.min(Sensor.unit), func.bool_or(Sensor.source == "simulated")).where(
            Sensor.farm_id == farm.id, Sensor.sensor_type == sensor_type
        )
    ).one()
    names = dict(db.execute(select(FarmZone.id, FarmZone.name).where(FarmZone.farm_id == farm.id)).all())
    zones: dict[int | None, list[dict[str, Any]]] = {}
    for zone_id, t, avg, mn, mx, n in rows:
        zones.setdefault(zone_id, []).append(
            {"t": t, "avg": round(float(avg), 3), "min": float(mn), "max": float(mx), "n": int(n)}
        )
    return {
        "sensor_type": sensor_type,
        "unit": meta[0],
        "includes_simulated": bool(meta[1]),
        "bucket_minutes": bucket,
        "start": start,
        "end": now,
        "zones": [
            {
                "zone_id": z,
                "zone_name": names.get(z, "Unassigned") if z is not None else "Unassigned",
                "points": pts,
            }
            for z, pts in zones.items()
        ],
    }
