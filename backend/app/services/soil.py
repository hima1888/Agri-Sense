"""Soil intelligence: an explainable, rule-based assessment of one zone.

Method (not a trained model):
  * Soil water: FAO-56 single-coefficient root-zone water balance. Total available water
    TAW = (FC - WP) * Zr, readily available water RAW = p * TAW, root-zone depletion
    Dr = (FC - theta) * Zr. Daily projection Dr += Kc * ET0 - effective rain.
  * Chemistry: pH against the crop's optimal range (crop catalogue); N, P, K and organic
    carbon against Soil Health Card ratings; salinity from electrical conductivity.
  * Index: weighted sub-scores (pH, N, P, K, organic carbon, salinity, water) over the
    components that could actually be assessed. Missing inputs are excluded, never guessed.

Every output carries the inputs it used, their sources, a confidence with reasons,
the contributing factors, guidance and limitations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.domain.irrigation import net_mm_from_volume
from app.domain.soil_reference import (
    DEFAULT_TEXTURE,
    EC_CLASSES,
    MG_KG_TO_KG_HA,
    NPK_LIMITS_KG_HA,
    ORGANIC_CARBON_LIMITS_PCT,
    TEXTURE_WATER,
    crop_water,
    kc_for_growth,
    rate,
)
from app.models import (
    Crop,
    CropCycle,
    Farm,
    FarmZone,
    IrrigationEvent,
    Sensor,
    SensorReading,
    SoilMeasurement,
    SoilProfile,
    WeatherData,
)
from app.services.weather import daily_summary


def irrigation_since(db: Session, zone: FarmZone, since: datetime, now: datetime) -> tuple[float, int]:
    """Net mm reaching the root zone from completed irrigation after ``since``; and how many events
    could not be converted (no volume, or no zone area)."""
    events = db.scalars(
        select(IrrigationEvent).where(
            IrrigationEvent.zone_id == zone.id,
            IrrigationEvent.status == "completed",
            func.coalesce(IrrigationEvent.ended_at, IrrigationEvent.started_at) > since,
            func.coalesce(IrrigationEvent.ended_at, IrrigationEvent.started_at) <= now,
        )
    ).all()
    area = float(zone.area_hectares) if zone.area_hectares else None
    total, skipped = 0.0, 0
    for e in events:
        if e.volume_liters is None or not area:
            skipped += 1
            continue
        total += net_mm_from_volume(float(e.volume_liters), area, e.method)
    return total, skipped


METHOD = "rule-based: FAO-56 water balance + Soil Health Card ratings"
SENSOR_WINDOW = timedelta(hours=24)
TREND_WINDOW = timedelta(days=7)
LAB_FRESH_DAYS = 180
LAB_MAX_DAYS = 365
WEIGHTS = {
    "ph": 0.20,
    "nitrogen": 0.15,
    "phosphorus": 0.15,
    "potassium": 0.15,
    "organic_carbon": 0.15,
    "salinity": 0.10,
    "water": 0.10,
}
LABELS = {
    "ph": "Soil pH",
    "nitrogen": "Available nitrogen",
    "phosphorus": "Available phosphorus",
    "potassium": "Available potassium",
    "organic_carbon": "Organic carbon",
    "salinity": "Salinity (EC)",
    "water": "Soil water",
}
RATING_SCORE = {"low": 35.0, "medium": 75.0, "high": 95.0}


@dataclass
class SensorStat:
    mean: float
    latest: float
    latest_at: datetime
    count: int
    simulated: bool


@dataclass
class Inputs:
    zone: FarmZone
    farm: Farm
    crop: Crop | None
    cycle: CropCycle | None
    growth: float | None
    profile: SoilProfile | None
    lab: SoilMeasurement | None
    lab_age_days: int | None
    sensors: dict[str, SensorStat] = field(default_factory=dict)
    trends: dict[str, float] = field(default_factory=dict)  # slope per day
    forecast: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------- data gathering
def gather(db: Session, zone: FarmZone, now: datetime) -> Inputs:
    farm = db.get(Farm, zone.farm_id)
    assert farm is not None
    row = db.execute(
        select(CropCycle, Crop)
        .join(Crop, Crop.id == CropCycle.crop_id)
        .where(CropCycle.zone_id == zone.id, CropCycle.status.in_(["growing", "planned"]))
        .order_by(case((CropCycle.status == "growing", 0), else_=1), CropCycle.id.desc())
    ).first()
    cycle, crop = (row[0], row[1]) if row else (None, None)
    growth = None
    if cycle and crop and cycle.status == "growing" and cycle.planted_on and crop.typical_cycle_days:
        growth = max(0.0, min(1.0, (now.date() - cycle.planted_on).days / crop.typical_cycle_days))

    profile = db.scalars(
        select(SoilProfile).where(SoilProfile.zone_id == zone.id).order_by(SoilProfile.id.desc())
    ).first()
    lab = db.scalars(
        select(SoilMeasurement)
        .where(SoilMeasurement.zone_id == zone.id, SoilMeasurement.source != "sensor_aggregate")
        .order_by(SoilMeasurement.measured_at.desc())
    ).first()
    lab_age = (now - lab.measured_at).days if lab else None
    if lab_age is not None and lab_age > LAB_MAX_DAYS:
        lab, lab_age = None, None  # too old to rely on

    stats = db.execute(
        select(
            Sensor.sensor_type,
            func.avg(SensorReading.value),
            func.count(),
            func.bool_or(Sensor.source == "simulated"),
            func.max(SensorReading.recorded_at),
        )
        .join(Sensor, Sensor.id == SensorReading.sensor_id)
        .where(
            Sensor.zone_id == zone.id,
            SensorReading.quality == "good",
            SensorReading.recorded_at >= now - SENSOR_WINDOW,
            SensorReading.recorded_at <= now,
        )
        .group_by(Sensor.sensor_type)
    ).all()
    sensors: dict[str, SensorStat] = {}
    for sensor_type, avg, count, simulated, latest_at in stats:
        latest = db.scalar(
            select(func.avg(SensorReading.value))
            .join(Sensor, Sensor.id == SensorReading.sensor_id)
            .where(
                Sensor.zone_id == zone.id,
                Sensor.sensor_type == sensor_type,
                SensorReading.quality == "good",
                SensorReading.recorded_at >= latest_at - timedelta(minutes=15),
                SensorReading.recorded_at <= latest_at,
            )
        )
        sensors[sensor_type] = SensorStat(
            float(avg), float(latest if latest is not None else avg), latest_at, int(count), bool(simulated)
        )

    # Linear trend per day over the last 7 days (Postgres regr_slope).
    day = func.extract("epoch", SensorReading.recorded_at) / 86_400.0
    trends = {
        t: float(slope)
        for t, slope, n in db.execute(
            select(Sensor.sensor_type, func.regr_slope(SensorReading.value, day), func.count())
            .join(Sensor, Sensor.id == SensorReading.sensor_id)
            .where(
                Sensor.zone_id == zone.id,
                SensorReading.quality == "good",
                SensorReading.recorded_at >= now - TREND_WINDOW,
                Sensor.sensor_type.in_(["soil_moisture", "nitrogen", "soil_ph"]),
            )
            .group_by(Sensor.sensor_type)
        ).all()
        if slope is not None and n >= 12
    }

    # Daily ET0 and rain from the stored Open-Meteo forecast (no network call here).
    tz = ZoneInfo(farm.timezone)
    local_midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    hourly = list(
        db.scalars(
            select(WeatherData)
            .where(
                WeatherData.farm_id == farm.id,
                WeatherData.kind == "forecast",
                WeatherData.valid_at >= local_midnight.astimezone(UTC),
            )
            .order_by(WeatherData.valid_at)
            .limit(24 * 8)
        )
    )
    today: date = now.astimezone(tz).date()
    forecast = [d for d in daily_summary(hourly, tz) if d["date"] >= today]

    return Inputs(zone, farm, crop, cycle, growth, profile, lab, lab_age, sensors, trends, forecast)


# ---------------------------------------------------------------- water balance (FAO-56)
def water_balance(
    fc: float,
    wp: float,
    theta: float,
    root_depth_m: float,
    p: float,
    kc: float,
    forecast: list[dict[str, Any]],
) -> dict[str, Any]:
    taw = (fc - wp) / 100 * 1000 * root_depth_m  # mm
    raw = p * taw
    depletion = max(0.0, (fc - theta) / 100 * 1000 * root_depth_m)
    if theta > fc + 1:
        status = "above_field_capacity"
    elif depletion <= raw:
        status = "adequate"
    elif depletion < taw:
        status = "stress"
    else:
        status = "severe"
    projection = []
    dr = depletion
    days_to_stress: int | None = 0 if depletion > raw else None
    for i, d in enumerate(forecast):
        et0 = float(d.get("et0_mm") or 0.0)
        rain = float(d.get("precipitation_mm") or 0.0)
        effective_rain = 0.8 * rain if rain > 2 else 0.0  # light showers mostly evaporate
        etc = kc * et0
        dr = min(taw, max(0.0, dr + etc - effective_rain))
        projection.append(
            {
                "date": d["date"],
                "et0_mm": round(et0, 2),
                "etc_mm": round(etc, 2),
                "effective_rain_mm": round(effective_rain, 2),
                "depletion_mm": round(dr, 1),
            }
        )
        if days_to_stress is None and dr > raw:
            days_to_stress = i + 1
    return {
        "field_capacity_pct": fc,
        "wilting_point_pct": wp,
        "moisture_pct": round(theta, 1),
        "root_depth_m": root_depth_m,
        "depletion_fraction_p": p,
        "kc": round(kc, 2),
        "taw_mm": round(taw, 1),
        "raw_mm": round(raw, 1),
        "depletion_mm": round(depletion, 1),
        "available_fraction": round(max(0.0, 1 - depletion / taw), 3) if taw > 0 else None,
        "status": status,
        "days_to_stress": days_to_stress,
        "forecast_days": len(forecast),
        "projection": projection,
    }


def water_score(status: str, available: float | None) -> float:
    if status == "above_field_capacity":
        return 70.0  # waterlogging risk, nutrient leaching
    if status == "adequate":
        return 100.0
    if status == "stress":
        return 30.0 + 40.0 * (available or 0.0)
    return 10.0


# ---------------------------------------------------------------- assessment
def _source_label(source: str, simulated: bool = False) -> str:
    return f"{source} (simulated)" if simulated else source


def assess(db: Session, zone: FarmZone, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    inp = gather(db, zone, now)
    crop_name = inp.crop.common_name if inp.crop else None
    components: dict[str, dict[str, Any]] = {}
    guidance: list[dict[str, str]] = []
    limitations: list[str] = [
        "Rule-based assessment using published reference values; it is not a trained model and does not "
        "replace a soil test interpreted by a local agronomist.",
    ]
    not_assessed: list[str] = []

    # ---- pH
    ph_val, ph_src, ph_conf = None, None, 0.0
    if inp.lab and inp.lab.ph is not None:
        ph_val, ph_src = float(inp.lab.ph), f"lab test ({inp.lab_age_days} days old)"
        ph_conf = 0.9 if (inp.lab_age_days or 0) <= LAB_FRESH_DAYS else 0.7
    elif "soil_ph" in inp.sensors:
        s = inp.sensors["soil_ph"]
        ph_val, ph_src = s.mean, _source_label("sensor 24 h mean", s.simulated)
        ph_conf = 0.35 if s.simulated else 0.6
    if ph_val is not None:
        lo = float(inp.crop.optimal_ph_min) if inp.crop and inp.crop.optimal_ph_min is not None else 6.0
        hi = float(inp.crop.optimal_ph_max) if inp.crop and inp.crop.optimal_ph_max is not None else 7.5
        optimum_src = (
            f"{crop_name} optimum" if inp.crop and inp.crop.optimal_ph_min is not None else "general range"
        )
        gap = lo - ph_val if ph_val < lo else (ph_val - hi if ph_val > hi else 0.0)
        status = "in_range" if gap == 0 else ("acidic" if ph_val < lo else "alkaline")
        components["ph"] = {
            "value": round(ph_val, 2),
            "unit": "pH",
            "status": status,
            "target": [lo, hi],
            "target_source": optimum_src,
            "source": ph_src,
            "confidence": ph_conf,
            "score": max(10.0, 100.0 - 35.0 * gap),
        }
        if status != "in_range":
            direction = "below" if status == "acidic" else "above"
            guidance.append(
                {
                    "level": "warning",
                    "text": f"pH {ph_val:.1f} is {direction} the {optimum_src} ({lo:.1f} to {hi:.1f}); "
                    "nutrient "
                    "availability is reduced. Confirm with a lab test before any lime or gypsum application.",
                }
            )
    else:
        not_assessed.append("ph")

    # ---- N, P, K
    for nutrient in ("nitrogen", "phosphorus", "potassium"):
        col = {
            "nitrogen": "nitrogen_mg_kg",
            "phosphorus": "phosphorus_mg_kg",
            "potassium": "potassium_mg_kg",
        }[nutrient]
        mg_kg, src, conf = None, None, 0.0
        lab_value = getattr(inp.lab, col) if inp.lab else None
        if lab_value is not None:
            mg_kg, src = float(lab_value), f"lab test ({inp.lab_age_days} days old)"
            conf = 0.9 if (inp.lab_age_days or 0) <= LAB_FRESH_DAYS else 0.7
        elif nutrient in inp.sensors:
            s = inp.sensors[nutrient]
            mg_kg, src = s.mean, _source_label("NPK probe 24 h mean", s.simulated)
            conf = 0.3 if s.simulated else 0.5
        if mg_kg is None:
            not_assessed.append(nutrient)
            continue
        kg_ha = mg_kg * MG_KG_TO_KG_HA
        lo, hi = NPK_LIMITS_KG_HA[nutrient]
        rating = rate(kg_ha, lo, hi)
        components[nutrient] = {
            "value": round(kg_ha, 1),
            "unit": "kg/ha",
            "value_mg_kg": round(mg_kg, 1),
            "status": rating,
            "target": [lo, hi],
            "target_source": "Soil Health Card rating limits",
            "source": src,
            "confidence": conf,
            "score": RATING_SCORE[rating],
        }
        if rating == "low":
            guidance.append(
                {
                    "level": "warning",
                    "text": f"{LABELS[nutrient]} is rated low ({kg_ha:.0f} kg/ha, below {lo:.0f}). Base any "
                    "fertilizer dose on a lab soil-test recommendation (fertilizer planning: Phase 13).",
                }
            )

    # ---- organic carbon & salinity (lab only: field probes do not measure these reliably)
    if inp.lab and inp.lab.organic_carbon_pct is not None:
        oc = float(inp.lab.organic_carbon_pct)
        rating = rate(oc, *ORGANIC_CARBON_LIMITS_PCT)
        components["organic_carbon"] = {
            "value": round(oc, 2),
            "unit": "%",
            "status": rating,
            "target": list(ORGANIC_CARBON_LIMITS_PCT),
            "target_source": "Soil Health Card rating limits",
            "source": f"lab test ({inp.lab_age_days} days old)",
            "confidence": 0.9,
            "score": RATING_SCORE[rating],
        }
        if rating == "low":
            guidance.append(
                {
                    "level": "info",
                    "text": f"Organic carbon is low ({oc:.2f} %). Residue retention, compost or green manure "
                    "improve water holding and nutrient supply over seasons.",
                }
            )
    else:
        not_assessed.append("organic_carbon")
    if inp.lab and inp.lab.electrical_conductivity_ds_m is not None:
        ec = float(inp.lab.electrical_conductivity_ds_m)
        cls = next((label for limit, label in EC_CLASSES if ec < limit), "strongly saline")
        components["salinity"] = {
            "value": round(ec, 2),
            "unit": "dS/m",
            "status": cls.replace(" ", "_"),
            "target": [0, 1.0],
            "target_source": "general salinity classes",
            "source": f"lab test ({inp.lab_age_days} days old)",
            "confidence": 0.85,
            "score": {"normal": 100.0, "slightly saline": 70.0, "moderately saline": 40.0}.get(cls, 15.0),
        }
        if cls != "normal":
            guidance.append(
                {
                    "level": "warning",
                    "text": f"Soil is {cls} (EC {ec:.2f} dS/m): sensitive crops may lose yield.",
                }
            )
    else:
        not_assessed.append("salinity")

    # ---- water
    water: dict[str, Any] | None = None
    moisture = inp.sensors.get("soil_moisture")
    lab_moisture = float(inp.lab.moisture_pct) if inp.lab and inp.lab.moisture_pct is not None else None
    if moisture or lab_moisture is not None:
        if (
            inp.profile
            and inp.profile.field_capacity_pct is not None
            and inp.profile.wilting_point_pct is not None
        ):
            fc, wp = float(inp.profile.field_capacity_pct), float(inp.profile.wilting_point_pct)
            profile_src, profile_conf = "measured soil profile", 1.0
        elif inp.profile and inp.profile.texture:
            fc, wp = TEXTURE_WATER[inp.profile.texture]
            profile_src, profile_conf = (
                f"estimated from texture ({inp.profile.texture.replace('_', ' ')}, FAO-56)",
                0.8,
            )
        else:
            fc, wp = TEXTURE_WATER[DEFAULT_TEXTURE]
            profile_src, profile_conf = "assumed loam (no soil profile recorded)", 0.55
            limitations.append("No soil profile: field capacity and wilting point assume a loam soil.")
        cw, cw_src = crop_water(crop_name, inp.crop.category if inp.crop else None)
        kc = kc_for_growth(cw, inp.growth) if inp.crop else 1.0
        theta = moisture.latest if moisture else float(lab_moisture or 0)
        measured_at = moisture.latest_at if moisture else (inp.lab.measured_at if inp.lab else now)
        moisture_src = (
            _source_label("soil-moisture sensors (latest)", moisture.simulated)
            if moisture
            else "lab/field test"
        )
        # Irrigation logged after the moisture measurement has not been seen by it yet: add it back.
        applied_mm, unconverted = irrigation_since(db, zone, measured_at, now)
        if applied_mm > 0:
            theta = min(fc, theta + applied_mm / (cw.root_depth_m * 10))
            moisture_src += f" + {applied_mm:.1f} mm irrigation logged since"
        if unconverted:
            limitations.append(
                f"{unconverted} irrigation event(s) since the last moisture reading could not be counted "
                "(no volume or no zone area)."
            )
        water = water_balance(fc, wp, theta, cw.root_depth_m, cw.p, kc, inp.forecast)
        water["measured_at"] = measured_at
        water["irrigation_since_mm"] = round(applied_mm, 1)
        moisture_conf = 1.0 if (moisture and not moisture.simulated) else (0.5 if moisture else 0.6)
        conf = round(profile_conf * moisture_conf * (1.0 if inp.forecast else 0.85), 2)
        water.update(
            {
                "sources": {
                    "moisture": moisture_src,
                    "soil_water_limits": profile_src,
                    "crop_parameters": {
                        "crop": f"FAO-56 values for {crop_name}",
                        "category": "FAO-56 category average",
                        "default": "generic values (no crop cycle)",
                    }[cw_src],
                    "evapotranspiration": "Open-Meteo ET0 forecast" if inp.forecast else "no forecast stored",
                },
                "confidence": conf,
            }
        )
        components["water"] = {
            "value": water["moisture_pct"],
            "unit": "% vol",
            "status": water["status"],
            "target": [round(fc - cw.p * (fc - wp), 1), fc],
            "target_source": "readily available water band",
            "source": moisture_src,
            "confidence": conf,
            "score": water_score(water["status"], water["available_fraction"]),
        }
        if water["status"] in ("stress", "severe"):
            guidance.append(
                {
                    "level": "warning",
                    "text": f"Root-zone depletion ({water['depletion_mm']:.0f} mm) exceeds the readily "
                    "available "
                    f"water ({water['raw_mm']:.0f} mm): the crop is likely under water stress now.",
                }
            )
        elif water["days_to_stress"] is not None:
            guidance.append(
                {
                    "level": "info" if water["days_to_stress"] > 2 else "warning",
                    "text": f"At forecast evapotranspiration, readily available water runs out in about "
                    f"{water['days_to_stress']} day(s). Smart irrigation scheduling arrives in Phase 12.",
                }
            )
        elif water["status"] == "above_field_capacity":
            guidance.append(
                {
                    "level": "info",
                    "text": "Soil is wetter than field capacity: hold irrigation; watch for waterlogging.",
                }
            )
        if not inp.forecast:
            limitations.append(
                "No stored weather forecast: open the dashboard to fetch one for the "
                "days-to-stress projection."
            )
    else:
        not_assessed.append("water")

    # ---- index, confidence, factors
    scored = {k: v for k, v in components.items() if k in WEIGHTS}
    total_w = sum(WEIGHTS[k] for k in scored)
    index = round(sum(WEIGHTS[k] * v["score"] for k, v in scored.items()) / total_w, 1) if total_w else None
    confidence = (
        round(sum(WEIGHTS[k] * v["confidence"] for k, v in scored.items()) / total_w, 2) if total_w else 0.0
    )
    coverage = round(total_w / sum(WEIGHTS.values()), 2)
    confidence = round(confidence * (0.6 + 0.4 * coverage), 2)  # fewer assessed components = less certain
    factors = sorted(
        (
            {
                "key": k,
                "label": LABELS[k],
                "status": v["status"],
                "score": round(v["score"], 1),
                "weight": WEIGHTS[k],
                "impact": round(WEIGHTS[k] / total_w * (100 - v["score"]), 1),  # index points lost
            }
            for k, v in scored.items()
        ),
        key=lambda f: -f["impact"],
    )

    reasons = []
    if not inp.lab:
        reasons.append("no lab soil test in the last year")
        guidance.append(
            {
                "level": "info",
                "text": "No lab soil test on record. Sensor-based nutrient values are indicative only; "
                "record a "
                "lab test (pH, N, P, K, organic carbon, EC) for a reliable assessment.",
            }
        )
    elif (inp.lab_age_days or 0) > LAB_FRESH_DAYS:
        reasons.append(f"lab test is {inp.lab_age_days} days old")
    simulated = any(s.simulated for s in inp.sensors.values())
    if simulated:
        reasons.append("uses simulated sensor data")
        limitations.append("Demo mode: includes simulated sensor data.")
    if not_assessed:
        reasons.append("not assessed: " + ", ".join(LABELS[k].lower() for k in not_assessed))
    if inp.sensors.get("nitrogen") and not (inp.lab and inp.lab.nitrogen_mg_kg is not None):
        limitations.append(
            "Low-cost NPK probes estimate nutrients from conductivity; they do not measure plant-available "
            "nutrients the way lab methods do."
        )
    limitations.append(
        "Nutrient conversion mg/kg → kg/ha assumes a 0 to 15 cm layer at bulk density "
        "≈ 1.49 g/cm³ (factor 2.24)."
    )

    return {
        "zone_id": zone.id,
        "zone_name": zone.name,
        "assessed_at": now,
        "method": METHOD,
        "crop": (
            {
                "name": crop_name,
                "category": inp.crop.category,
                "growth_fraction": round(inp.growth, 3) if inp.growth is not None else None,
                "status": inp.cycle.status if inp.cycle else None,
            }
            if inp.crop
            else None
        ),
        "index": index,
        "rating": None if index is None else ("good" if index >= 75 else "fair" if index >= 50 else "poor"),
        "confidence": confidence,
        "confidence_reasons": reasons,
        "components": components,
        "not_assessed": not_assessed,
        "factors": factors,
        "water": water,
        "trends": {k: round(v, 4) for k, v in inp.trends.items()},
        "guidance": guidance,
        "limitations": limitations,
        "uses_simulated_data": simulated,
        "inputs": {
            "lab_test_id": inp.lab.id if inp.lab else None,
            "lab_test_age_days": inp.lab_age_days,
            "soil_profile_id": inp.profile.id if inp.profile else None,
            "sensor_types": sorted(inp.sensors),
            "sensor_window_hours": int(SENSOR_WINDOW.total_seconds() // 3600),
            "forecast_days": len(inp.forecast),
        },
    }


def summarize_for_farm(db: Session, farm: Farm, now: datetime | None = None) -> list[dict[str, Any]]:
    zones = db.scalars(select(FarmZone).where(FarmZone.farm_id == farm.id).order_by(FarmZone.id))
    out = []
    for z in zones:
        a = assess(db, z, now)
        out.append(
            {
                "zone_id": z.id,
                "zone_name": z.name,
                "index": a["index"],
                "rating": a["rating"],
                "confidence": a["confidence"],
                "water_status": a["water"]["status"] if a["water"] else None,
                "days_to_stress": a["water"]["days_to_stress"] if a["water"] else None,
                "top_factor": a["factors"][0]["label"] if a["factors"] else None,
                "uses_simulated_data": a["uses_simulated_data"],
            }
        )
    return out


def snapshot_values(a: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-safe summary stored with a saved assessment."""
    return {
        "index": a["index"],
        "rating": a["rating"],
        "water_status": a["water"]["status"] if a["water"] else None,
        "days_to_stress": a["water"]["days_to_stress"] if a["water"] else None,
        "components": {
            k: {"value": v["value"], "unit": v["unit"], "status": v["status"]}
            for k, v in a["components"].items()
        },
    }


def json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    return obj
