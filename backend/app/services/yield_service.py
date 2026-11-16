# ruff: noqa: E501  (compact result dictionaries)
"""Yield estimate (Phase 14): moisture history -> daily Ks -> FAO-33 water-limited yield; storage; back-test."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import yield_model
from app.domain.soil_reference import crop_water
from app.models import AIPrediction, Crop, CropCycle, Farm, FarmZone, Sensor, SensorReading, SoilMeasurement
from app.services import nutrients, soil


def _area(cycle: CropCycle, zone: FarmZone) -> float | None:
    a = cycle.area_hectares or zone.area_hectares
    return float(a) if a else None


def reference_from_history(db: Session, farm_id: int, crop: Crop) -> tuple[float, str] | None:
    """Best per-hectare actual yield of this crop in the farm's harvested cycles."""
    rows = db.execute(
        select(CropCycle, FarmZone)
        .join(FarmZone, FarmZone.id == CropCycle.zone_id)
        .where(
            FarmZone.farm_id == farm_id,
            CropCycle.crop_id == crop.id,
            CropCycle.status == "harvested",
            CropCycle.actual_yield_kg.is_not(None),
        )
    ).all()
    per_ha = [
        float(c.actual_yield_kg) / a for c, z in rows if (a := _area(c, z)) and c.actual_yield_kg is not None
    ]
    if not per_ha:
        return None
    return round(max(per_ha)), f"best of {len(per_ha)} past harvest(s) of {crop.common_name} on this farm"


def daily_ks(
    db: Session, zone: FarmZone, tz: ZoneInfo, start: date, end: date, water: dict[str, Any]
) -> tuple[dict[date, float], bool]:
    """Daily mean Ks from good soil-moisture readings and lab/field moisture tests. Returns (Ks by day, any simulated)."""
    fc, zr, p = water["field_capacity_pct"], water["root_depth_m"], water["depletion_fraction_p"]
    taw, raw = water["taw_mm"], water["raw_mm"]
    lo = datetime.combine(start, datetime.min.time(), tz).astimezone(UTC)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tz).astimezone(UTC)
    rows = db.execute(
        select(SensorReading.recorded_at, SensorReading.value, Sensor.source)
        .join(Sensor, Sensor.id == SensorReading.sensor_id)
        .where(Sensor.zone_id == zone.id, Sensor.sensor_type == "soil_moisture", SensorReading.quality == "good",
               SensorReading.recorded_at >= lo, SensorReading.recorded_at < hi)
    ).all()  # fmt: skip
    by_day: dict[date, list[float]] = defaultdict(list)
    simulated = False
    for at, value, source in rows:
        by_day[at.astimezone(tz).date()].append(float(value))
        simulated = simulated or source == "simulated"
    tests = db.execute(
        select(SoilMeasurement.measured_at, SoilMeasurement.moisture_pct).where(
            SoilMeasurement.zone_id == zone.id, SoilMeasurement.moisture_pct.is_not(None),
            SoilMeasurement.source != "sensor_aggregate", SoilMeasurement.measured_at >= lo, SoilMeasurement.measured_at < hi,
        )
    ).all()  # fmt: skip
    for at, m in tests:
        if m is not None:
            by_day[at.astimezone(tz).date()].append(float(m))
    out = {}
    for day, values in by_day.items():
        theta = sum(values) / len(values)
        dr = max(0.0, (fc - theta) / 100 * 1000 * zr)
        out[day] = yield_model.ks(dr, taw, raw, p)
    return out, simulated


def zone_estimate(db: Session, zone: FarmZone, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    farm = db.get(Farm, zone.farm_id)
    assert farm is not None
    tz = ZoneInfo(farm.timezone)
    today = now.astimezone(tz).date()
    base: dict[str, Any] = {
        "zone_id": zone.id,
        "zone_name": zone.name,
        "generated_at": now,
        "method": "FAO-33 water-limited yield (Ya = Ym x (1 - Ky x (1 - ETa/ETc))) with FAO-56 Ks from moisture history",
    }
    cc = nutrients.current_cycle(db, zone)
    if cc is None:
        return {**base, "status": "no_crop", "message": "No planned or growing crop cycle in this zone."}
    cycle, crop = cc
    area = _area(cycle, zone)
    base.update(
        {
            "crop": crop.common_name,
            "cycle_id": cycle.id,
            "area_hectares": area,
            "reference_is_custom": cycle.yield_reference is not None,
        }
    )
    if cycle.planted_on is None:
        return {
            **base,
            "status": "no_planting_date",
            "message": "Record the planting date of this crop cycle to estimate yield.",
        }
    harvest = cycle.expected_harvest_on or (
        cycle.planted_on + timedelta(days=crop.typical_cycle_days) if crop.typical_cycle_days else None
    )
    if harvest is None:
        return {
            **base,
            "status": "no_harvest_date",
            "message": "Record the expected harvest date (or the crop's typical cycle length).",
        }
    ref = cycle.yield_reference
    ym: float | None
    ym_source: str | None
    if ref:
        ym, ym_source = float(ref["kg_ha"]), str(ref.get("source") or "recorded for this crop cycle")
    else:
        hist = reference_from_history(db, zone.farm_id, crop)
        ym, ym_source = (hist[0], hist[1]) if hist else (None, None)

    water = soil.assess(db, zone, now).get("water")
    cw, _ = crop_water(crop.common_name, crop.category)
    ks_by_day, simulated = (
        daily_ks(db, zone, tz, cycle.planted_on, min(today, harvest), water) if water else ({}, False)
    )
    result = yield_model.estimate(crop=crop.common_name, planted=cycle.planted_on, harvest=harvest, today=today,
                                  daily_ks=ks_by_day, cw=cw, ym_kg_ha=ym, ym_source=ym_source)  # fmt: skip
    if simulated:
        result.setdefault("limitations", []).insert(
            0, "Moisture history comes from SIMULATED sensors: the estimate demonstrates the method only."
        )
        result["confidence"] = round(result.get("confidence", 0) * 0.5, 2)
    if result["status"] == "estimate" and area:
        result["total_kg"] = {k: round(v * area) for k, v in result["yield_kg_ha"].items()}
    disease_note = _recent_disease_count(db, zone, cycle.planted_on)
    if disease_note:
        result.setdefault("limitations", []).append(
            f"{disease_note} possible-disease check(s) this season are not reflected in the estimate."
        )
    return {**base, **result, "uses_simulated_data": simulated}


def _recent_disease_count(db: Session, zone: FarmZone, since: date) -> int:
    from app.models import DiseaseDetection

    return db.scalar(
        select(func.count()).select_from(DiseaseDetection).where(
            DiseaseDetection.zone_id == zone.id, DiseaseDetection.is_healthy.is_(False),
            DiseaseDetection.detected_at >= datetime.combine(since, datetime.min.time(), UTC),
        )
    ) or 0  # fmt: skip


def save(db: Session, zone: FarmZone, now: datetime | None = None) -> AIPrediction | None:
    e = zone_estimate(db, zone, now)
    if e.get("status") != "estimate":
        return None
    rec = AIPrediction(
        farm_id=zone.farm_id, zone_id=zone.id, crop_cycle_id=e["cycle_id"], prediction_type="yield",
        predicted_value=soil.json_safe({"unit": "kg/ha", **e["yield_kg_ha"], "total_kg": e.get("total_kg"), "ym_kg_ha": e["ym_kg_ha"], "ky": e["ky"]}),
        confidence=Decimal(str(e["confidence"])), factors=soil.json_safe(e["factors"]), limitations=" ".join(e["limitations"]),
        input_snapshot=soil.json_safe({"method": e["method"], "season": e["season"], "relative_et": e["relative_et"], "uses_simulated_data": e["uses_simulated_data"]}),
        valid_from=e["generated_at"], valid_until=datetime.combine(e["season"]["harvest"], datetime.min.time(), UTC),
    )  # fmt: skip
    db.add(rec)
    db.flush()
    return rec


def backtest(db: Session, farm: Farm) -> dict[str, Any]:
    """Saved estimates vs actual yields: for each harvested cycle, the last estimate saved before harvest."""
    cycles = db.execute(
        select(CropCycle, FarmZone, Crop)
        .join(FarmZone, FarmZone.id == CropCycle.zone_id)
        .join(Crop, Crop.id == CropCycle.crop_id)
        .where(
            FarmZone.farm_id == farm.id,
            CropCycle.status == "harvested",
            CropCycle.actual_yield_kg.is_not(None),
        )
    ).all()
    rows: list[dict[str, Any]] = []
    for c, z, crop in cycles:
        area = _area(c, z)
        if not area or c.actual_yield_kg is None:
            continue
        # Estimates saved up to the end of harvest day count; later ones would be hindsight.
        cutoff = (
            datetime.combine(c.harvested_on + timedelta(days=1), datetime.min.time(), UTC)
            if c.harvested_on
            else None
        )
        q = select(AIPrediction).where(
            AIPrediction.crop_cycle_id == c.id, AIPrediction.prediction_type == "yield"
        )
        if cutoff:
            q = q.where(AIPrediction.created_at < cutoff)
        pred = db.scalars(q.order_by(AIPrediction.created_at.desc()).limit(1)).first()
        if pred is None:
            continue
        actual = float(c.actual_yield_kg) / area
        central = float(pred.predicted_value["central"])
        rows.append({
            "cycle_id": c.id, "zone_name": z.name, "crop": crop.common_name, "actual_kg_ha": round(actual),
            "predicted_central_kg_ha": round(central), "predicted_low_kg_ha": round(float(pred.predicted_value["low"])),
            "predicted_high_kg_ha": round(float(pred.predicted_value["high"])), "error_pct": round((central - actual) / actual * 100, 1) if actual else None,
            "within_range": float(pred.predicted_value["low"]) <= actual <= float(pred.predicted_value["high"]), "predicted_at": pred.created_at,
        })  # fmt: skip
    errors: list[float] = [abs(float(r["error_pct"])) for r in rows if r["error_pct"] is not None]
    return {
        "cycles": rows,
        "n": len(rows),
        "mean_absolute_error_pct": round(sum(errors) / len(errors), 1) if errors else None,
        "share_within_range": round(sum(1 for r in rows if r["within_range"]) / len(rows), 2)
        if rows
        else None,
        "message": None
        if rows
        else "No harvested cycles with a recorded yield and a saved estimate yet: the accuracy of these estimates on this farm is unknown.",
    }
