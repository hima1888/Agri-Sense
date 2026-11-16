# ruff: noqa: E501  (compact result dictionaries)
"""Farm analytics over a date range (Phase 16). Everything is computed from stored records; every
section says what it covers, and indicators without data are reported as None, never as zero."""

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import irrigation as irr
from app.domain import nutrients as nut
from app.integrations.open_meteo import SOURCE as WEATHER_SOURCE
from app.models import (
    AIRecommendation,
    Alert,
    Crop,
    CropCycle,
    DiseaseDetection,
    Farm,
    FarmZone,
    FertilizerApplication,
    IrrigationEvent,
    PesticideApplication,
    Sensor,
    SensorReading,
    WeatherData,
)
from app.services import soil
from app.services.weather import daily_summary

MAX_DAYS = 400


def _bounds(farm: Farm, start: date, end: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(farm.timezone)
    return datetime.combine(start, time(0), tz).astimezone(UTC), datetime.combine(
        end + timedelta(days=1), time(0), tz
    ).astimezone(UTC)


def _pct_change(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 1)


def _per_ha(v: float | None, area: float | None) -> float | None:
    return None if v is None or not area else round(v / area, 2)


def compute(db: Session, farm: Farm, start: date, end: date) -> dict[str, Any]:
    lo, hi = _bounds(farm, start, end)
    tz = ZoneInfo(farm.timezone)
    zones = db.scalars(select(FarmZone).where(FarmZone.farm_id == farm.id).order_by(FarmZone.id)).all()
    zone_ids = [z.id for z in zones]
    areas = {z.id: float(z.area_hectares) if z.area_hectares else None for z in zones}
    total_area = sum(a for a in areas.values() if a) or None
    zones_without_area = [z.name for z in zones if not areas[z.id]]

    # ---------------------------------------------------------- water
    when = func.coalesce(IrrigationEvent.ended_at, IrrigationEvent.started_at)
    events = (
        db.scalars(
            select(IrrigationEvent).where(
                IrrigationEvent.zone_id.in_(zone_ids),
                IrrigationEvent.status == "completed",
                when >= lo,
                when < hi,
            )
        ).all()
        if zone_ids
        else []
    )
    liters = sum(float(e.volume_liters) for e in events if e.volume_liters is not None)
    by_zone_l: dict[int, float] = defaultdict(float)
    for e in events:
        if e.volume_liters is not None:
            by_zone_l[e.zone_id] += float(e.volume_liters)
    rows = db.scalars(
        select(WeatherData).where(
            WeatherData.farm_id == farm.id,
            WeatherData.source == WEATHER_SOURCE,
            WeatherData.kind == "forecast",
            WeatherData.valid_at >= lo,
            WeatherData.valid_at < hi,
        )
    ).all()
    days = daily_summary(list(rows), tz)
    period_days = (end - start).days + 1
    water = {
        "irrigation_events": len(events),
        "events_without_volume": sum(1 for e in events if e.volume_liters is None),
        "irrigation_liters": round(liters),
        "irrigation_mm": round(liters / total_area / 10_000, 1) if total_area else None,
        "irrigation_liters_per_ha": _per_ha(liters, total_area),
        "by_zone": [
            {
                "zone": z.name,
                "liters": round(by_zone_l.get(z.id, 0)),
                "mm": round(by_zone_l[z.id] / (areas[z.id] or 1) / 10_000, 1) if areas[z.id] else None,
            }
            for z in zones
        ],
        "rain_mm": round(sum(d["precipitation_mm"] for d in days), 1) if days else None,
        "effective_rain_mm": round(sum(irr.effective_rain(d["precipitation_mm"]) for d in days), 1)
        if days
        else None,
        "et0_mm": round(sum(d["et0_mm"] for d in days), 1) if days else None,
        "weather_days_covered": len(days),
        "stress": _stress_hours(db, farm, zones, lo, hi),
    }

    # ---------------------------------------------------------- fertilizer
    ferts = (
        db.scalars(
            select(FertilizerApplication).where(
                FertilizerApplication.zone_id.in_(zone_ids),
                FertilizerApplication.applied_at >= lo,
                FertilizerApplication.applied_at < hi,
            )
        ).all()
        if zone_ids
        else []
    )
    nutrients = nut.applied_nutrients(
        [{"quantity_kg": f.quantity_kg, "n_pct": f.n_pct, "p_pct": f.p_pct, "k_pct": f.k_pct} for f in ferts],
        1.0,
    )
    fertilizer = {
        "applications": len(ferts),
        "product_kg": round(sum(float(f.quantity_kg) for f in ferts), 1),
        "organic_kg": round(sum(float(f.quantity_kg) for f in ferts if f.is_organic), 1),
        "nutrients_kg": nutrients,
        "nutrients_kg_per_ha": {k: _per_ha(v, total_area) for k, v in nutrients.items()},
        "without_grade": sum(1 for f in ferts if f.n_pct is None and f.p_pct is None and f.k_pct is None),
    }

    # ---------------------------------------------------------- pesticides
    pests = (
        db.scalars(
            select(PesticideApplication).where(
                PesticideApplication.zone_id.in_(zone_ids),
                PesticideApplication.applied_at >= lo,
                PesticideApplication.applied_at < hi,
            )
        ).all()
        if zone_ids
        else []
    )
    qty: dict[str, float] = defaultdict(float)
    for p in pests:
        qty[p.quantity_unit] += float(p.quantity)
    pesticides = {
        "applications": len(pests),
        "applications_per_ha": _per_ha(len(pests), total_area),
        "by_type": dict(Counter(p.pesticide_type for p in pests)),
        "quantity_by_unit": {u: round(v, 3) for u, v in qty.items()},
        "quantity_per_ha_by_unit": {u: _per_ha(v, total_area) for u, v in qty.items()},
        "with_evidence": sum(1 for p in pests if p.disease_detection_id),
        "evidence_share": round(sum(1 for p in pests if p.disease_detection_id) / len(pests), 2)
        if pests
        else None,
    }

    # ---------------------------------------------------------- crop health & harvests
    dets = db.scalars(
        select(DiseaseDetection).where(
            DiseaseDetection.farm_id == farm.id,
            DiseaseDetection.detected_at >= lo,
            DiseaseDetection.detected_at < hi,
        )
    ).all()
    health = {
        "disease_checks": len(dets),
        "by_outcome": dict(Counter((d.explanation or {}).get("outcome", "unknown") for d in dets)),
        "possible_diseases": dict(
            Counter(
                d.disease_label for d in dets if (d.explanation or {}).get("outcome") == "possible_disease"
            )
        ),
    }
    harvested = db.execute(
        select(CropCycle, Crop, FarmZone).join(Crop, Crop.id == CropCycle.crop_id).join(FarmZone, FarmZone.id == CropCycle.zone_id)
        .where(FarmZone.farm_id == farm.id, CropCycle.status == "harvested", CropCycle.harvested_on >= start, CropCycle.harvested_on <= end)
    ).all()  # fmt: skip
    harvests = [{"zone": z.name, "crop": c.common_name, "harvested_on": cy.harvested_on, "yield_kg": None if cy.actual_yield_kg is None else float(cy.actual_yield_kg),
                 "yield_kg_ha": _per_ha(None if cy.actual_yield_kg is None else float(cy.actual_yield_kg), float(cy.area_hectares or z.area_hectares or 0) or None)} for cy, c, z in harvested]  # fmt: skip

    # ---------------------------------------------------------- advice & alerts
    recs = db.scalars(
        select(AIRecommendation).where(
            AIRecommendation.farm_id == farm.id,
            AIRecommendation.created_at >= lo,
            AIRecommendation.created_at < hi,
        )
    ).all()
    status = Counter(r.status for r in recs)
    decided = status["accepted"] + status["applied"] + status["rejected"]
    advice = {"recommendations": len(recs), "by_status": dict(status), "by_category": dict(Counter(r.category for r in recs)),
              "uptake": round((status["accepted"] + status["applied"]) / decided, 2) if decided else None}  # fmt: skip
    alerts_ = db.scalars(
        select(Alert).where(Alert.farm_id == farm.id, Alert.triggered_at >= lo, Alert.triggered_at < hi)
    ).all()
    resolve_h = [(a.resolved_at - a.triggered_at).total_seconds() / 3600 for a in alerts_ if a.resolved_at]
    alerts = {"raised": len(alerts_), "by_severity": dict(Counter(a.severity for a in alerts_)), "resolved": len(resolve_h),
              "median_hours_to_resolve": round(sorted(resolve_h)[len(resolve_h) // 2], 1) if resolve_h else None}  # fmt: skip

    # ---------------------------------------------------------- data quality
    q = db.execute(
        select(Sensor.source, SensorReading.quality, func.count())
        .join(Sensor, Sensor.id == SensorReading.sensor_id)
        .where(Sensor.farm_id == farm.id, SensorReading.recorded_at >= lo, SensorReading.recorded_at < hi)
        .group_by(Sensor.source, SensorReading.quality)
    ).all()
    total = sum(n for _, _, n in q)
    data = {
        "readings": total,
        "not_good_share": round(sum(n for _, ql, n in q if ql != "good") / total, 3) if total else None,
        "simulated_share": round(sum(n for src, _, n in q if src == "simulated") / total, 3)
        if total
        else None,
        "zones_without_area": zones_without_area,
    }

    return {
        "farm_id": farm.id,
        "farm_name": farm.name,
        "period": {"start": start, "end": end, "days": period_days, "timezone": farm.timezone},
        "area_ha": total_area,
        "zones": len(zones),
        "water": water,
        "fertilizer": fertilizer,
        "pesticides": pesticides,
        "health": health,
        "harvests": harvests,
        "advice": advice,
        "alerts": alerts,
        "data": data,
        "uses_simulated_data": bool(data["simulated_share"]),
    }


def _stress_hours(
    db: Session, farm: Farm, zones: Sequence[FarmZone], lo: datetime, hi: datetime
) -> list[dict[str, Any]]:
    """Share of measured hours each zone's moisture was below its readily-available-water threshold.
    Thresholds use the zone's CURRENT soil and crop parameters (Phase 8), applied to the whole period."""
    out = []
    hour = func.date_trunc("hour", SensorReading.recorded_at)
    for z in zones:
        w = soil.assess(db, z).get("water")
        if not w:
            out.append({"zone": z.name, "measured_hours": 0, "stress_share": None, "threshold_pct": None})
            continue
        threshold = round(
            w["field_capacity_pct"]
            - w["depletion_fraction_p"] * (w["field_capacity_pct"] - w["wilting_point_pct"]),
            1,
        )
        means = db.execute(
            select(hour, func.avg(SensorReading.value)).join(Sensor, Sensor.id == SensorReading.sensor_id)
            .where(Sensor.zone_id == z.id, Sensor.sensor_type == "soil_moisture", SensorReading.quality == "good", SensorReading.recorded_at >= lo, SensorReading.recorded_at < hi)
            .group_by(hour)
        ).all()  # fmt: skip
        n = len(means)
        out.append({"zone": z.name, "measured_hours": n, "threshold_pct": threshold,
                    "stress_share": round(sum(1 for _, v in means if float(v) < threshold) / n, 3) if n else None})  # fmt: skip
    return out


INDICATORS = [
    ("Irrigation water per ha", ("water", "irrigation_liters_per_ha"), "L/ha"),
    ("Nitrogen per ha", ("fertilizer", "nutrients_kg_per_ha", "n"), "kg N/ha"),
    ("Phosphate per ha", ("fertilizer", "nutrients_kg_per_ha", "p2o5"), "kg P2O5/ha"),
    ("Potash per ha", ("fertilizer", "nutrients_kg_per_ha", "k2o"), "kg K2O/ha"),
    ("Pesticide applications per ha", ("pesticides", "applications_per_ha"), "per ha"),
    ("Sprays linked to a disease check", ("pesticides", "evidence_share"), "share"),
    ("Advice taken up", ("advice", "uptake"), "share"),
]


def _get(d: dict[str, Any], path: tuple[str, ...]) -> Any:
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)  # type: ignore[assignment]
    return d


def analytics(db: Session, farm: Farm, start: date, end: date) -> dict[str, Any]:
    cur = compute(db, farm, start, end)
    span = end - start
    prev = compute(db, farm, start - span - timedelta(days=1), start - timedelta(days=1))
    indicators = []
    for label, path, unit in INDICATORS:
        c, p = _get(cur, path), _get(prev, path)
        indicators.append(
            {"indicator": label, "unit": unit, "current": c, "previous": p, "change_pct": _pct_change(c, p)}
        )
    stress = [s["stress_share"] for s in cur["water"]["stress"] if s["stress_share"] is not None]
    cur["indicators"] = indicators
    cur["previous_period"] = prev["period"]
    cur["mean_stress_share"] = round(sum(stress) / len(stress), 3) if stress else None
    cur["notes"] = [
        "Figures come only from records in AGRI-SENSE; anything not logged here (e.g. a spray recorded on paper) is missing.",
        "Rain and ET0 come from stored Open-Meteo hourly data and cover only days the app fetched weather.",
        "Water-stress hours use each zone's current soil and crop parameters for the whole period.",
    ] + (["Demo mode: includes simulated sensor data."] if cur["uses_simulated_data"] else [])
    return cur


def csv_rows(content: dict[str, Any]) -> list[list[Any]]:
    """Flatten a report into section,metric,value rows."""
    rows: list[list[Any]] = [["section", "metric", "value"]]

    def walk(prefix: str, v: Any) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(f"{prefix}.{k}" if prefix else str(k), x)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(f"{prefix}[{i}]", x)
        else:
            section, _, metric = prefix.partition(".")
            rows.append([section, metric or section, "" if v is None else v])

    walk("", soil.json_safe(content))
    return rows
