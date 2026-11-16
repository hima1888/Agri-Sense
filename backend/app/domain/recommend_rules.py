"""Explainable recommendation rules (Phase 11).

Every rule is a transparent IF-THEN over values the app already holds: the Phase 8 soil assessment
(FAO-56 water balance, Soil Health Card ratings), the stored Open-Meteo forecast, Phase 10 disease
checks and sensor reporting status. Nothing here is a trained model.

Each recommendation carries: what to do, why (factors with values and sources), a confidence, and
limitations. Confidence = confidence of the data the rule used x a fixed rule-certainty factor
(RULE_CERTAINTY), which states how directly the rule's evidence supports its action.
"""

# ruff: noqa: E501  (long, user-facing rationale strings)
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.domain.irrigation import efficiency

# How directly each rule's evidence supports the advice (documented, not fitted).
RULE_CERTAINTY: dict[str, float] = {
    "irrigate_now": 0.95,  # measured/estimated depletion already beyond the FAO-56 threshold
    "irrigation_soon": 0.85,  # projection; depends on forecast ET0
    "hold_irrigation_rain": 0.7,  # depends on forecast rain actually falling
    "skip_irrigation_wet": 0.9,  # soil above field capacity
    "nutrient_low": 0.8,  # rating against Soil Health Card limits
    "organic_matter_low": 0.8,
    "ph_out_of_range": 0.8,
    "salinity": 0.8,
    "soil_test_needed": 1.0,  # a fact: no recent lab test
    "confirm_suspected_disease": 0.9,  # a fact: a model flagged a possible disease
    "humid_weather_scouting": 0.5,  # generic humidity proxy, not a validated disease model
    "heat_stress": 0.75,
    "sensors_silent": 1.0,  # a fact: no recent readings
}

RAIN_HOLD_MM = 10.0  # forecast rain in the next 48 h large enough to delay irrigation
HUMID_RH = 90.0  # % relative humidity
HUMID_T = (15.0, 30.0)  # deg C band favourable to many foliar fungi
HUMID_HOURS = 12  # hours in the next 72 h meeting both
HEAT_C = 35.0
# FAO-33 (Doorenbos & Kassam, 1979): water stress during flowering and yield formation costs the most yield.
SENSITIVE_STAGES = {"flowering", "formation"}
SILENT_HOURS = 2

COMMON_LIMITATIONS = [
    "Rule-based guidance from published reference values and this farm's data; not a trained model.",
    "Check local conditions and extension guidance before acting.",
]


@dataclass
class ZoneContext:
    zone_id: int
    zone_name: str
    area_ha: float | None
    irrigation_method: str | None
    soil: dict[str, Any]  # Phase 8 assessment
    recent_disease: list[dict[str, Any]] = field(default_factory=list)  # possible_disease checks, last 14 d
    stage: dict[str, Any] | None = (
        None  # FAO-56 based growth stage of the growing crop (app/domain/growth.py)
    )
    silent_sensors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FarmContext:
    farm_id: int
    now: datetime
    hourly: list[dict[str, Any]]  # forecast rows for the next 72 h
    daily: list[dict[str, Any]]
    weather_fetched_at: datetime | None
    zones: list[ZoneContext]


def _f(name: str, value: Any, unit: str = "", source: str = "", simulated: bool = False) -> dict[str, Any]:
    return {"name": name, "value": value, "unit": unit, "source": source, "simulated": simulated}


def _rec(
    rule: str, ctx: FarmContext, zone: ZoneContext | None, *, category: str, priority: str, title: str,
    rationale: str, action: dict[str, Any], factors: list[dict[str, Any]], data_conf: float,
    limitations: list[str], valid_hours: int, expected_impact: dict[str, Any] | None = None,
    variant: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    simulated = any(f["simulated"] for f in factors)
    lims = list(limitations)
    if simulated:
        lims.insert(0, "Demo mode: based partly on simulated sensor data.")
    conf = round(max(0.0, min(1.0, data_conf * RULE_CERTAINTY[rule])), 2)
    return {
        # One stored recommendation per (zone, rule[:variant]); the variant separates e.g. N from K.
        "rule": f"{rule}:{variant}" if variant else rule,
        "zone_id": zone.zone_id if zone else None,
        "zone_name": zone.zone_name if zone else None,
        "category": category,
        "priority": priority,
        "title": title,
        "rationale": rationale,
        "action": action,
        "factors": factors,
        "confidence": conf,
        "confidence_basis": f"data confidence {data_conf:.2f} x rule certainty {RULE_CERTAINTY[rule]:.2f}",
        "expected_impact": expected_impact,
        "limitations": lims + COMMON_LIMITATIONS,
        "uses_simulated_data": simulated,
        "expires_at": ctx.now + timedelta(hours=valid_hours),
    }


def _rain_next(ctx: FarmContext, hours: int) -> float:
    end = ctx.now + timedelta(hours=hours)
    return round(sum(h["precipitation_mm"] or 0 for h in ctx.hourly if ctx.now <= h["valid_at"] < end), 1)


def _is_sim(source: str) -> bool:
    return "simulated" in source


# ------------------------------------------------------------------ water
def water_rules(ctx: FarmContext, z: ZoneContext) -> list[dict[str, Any]]:
    w = z.soil.get("water")
    if not w:
        return []
    src = w["sources"]
    sim = _is_sim(src.get("moisture", ""))
    base = [
        _f("Soil moisture", w["moisture_pct"], "% vol", src.get("moisture", ""), sim),
        _f("Root-zone depletion", w["depletion_mm"], "mm", "FAO-56 water balance", sim),
        _f("Readily available water (stress threshold)", w["raw_mm"], "mm", src.get("soil_water_limits", "")),
    ]
    crop = (z.soil.get("crop") or {}).get("name", "the crop")
    sensitive = bool(z.stage and z.stage["key"] in SENSITIVE_STAGES)
    if z.stage:
        base.append(
            _f(
                "Growth stage",
                f"{z.stage['name']} (day {z.stage['day']})",
                "",
                "FAO-56 stages from the sowing date",
            )
        )
    rain48 = _rain_next(ctx, 48)
    has_forecast = bool(ctx.hourly)
    if has_forecast:
        base.append(_f("Forecast rain, next 48 h", rain48, "mm", "Open-Meteo forecast"))
    data_conf = w["confidence"] * (1.0 if has_forecast else 0.85)
    eff = efficiency(z.irrigation_method)
    net_mm = round(w["depletion_mm"], 1)
    gross_mm = round(net_mm / eff, 1)
    volume = round(gross_mm * z.area_ha * 10_000) if z.area_ha else None  # 1 mm over 1 m2 = 1 L
    action = {"type": "irrigate", "net_mm": net_mm, "gross_mm": gross_mm, "application_efficiency": eff,
              "volume_liters": volume, "timing": "early morning or evening to reduce evaporation"}  # fmt: skip
    amount = f"about {gross_mm} mm" + (f" (~{volume:,} L for {z.area_ha} ha)" if volume else "")
    lims = [
        "Amount refills the root zone to field capacity; completed irrigation logged since the last moisture reading is counted. See the Irrigation page for a multi-day plan."
    ]
    if not z.area_ha:
        lims.append("Zone area unknown, so no volume in litres; add the area in zone settings.")

    if w["status"] == "above_field_capacity":
        return [_rec("skip_irrigation_wet", ctx, z, category="irrigation", priority="low",
                     title=f"Skip irrigation in {z.zone_name}: soil is wetter than field capacity",
                     rationale=f"Moisture {w['moisture_pct']} % is above field capacity ({w['field_capacity_pct']} %). "
                     "Extra water would drain below the roots.",
                     action={"type": "skip_irrigation"}, factors=base, data_conf=data_conf, limitations=[],
                     valid_hours=24, expected_impact={"water_saved": "avoids drainage losses"})]  # fmt: skip
    if w["status"] in ("stress", "severe"):
        if has_forecast and rain48 * 0.8 >= w["depletion_mm"] and rain48 >= RAIN_HOLD_MM:
            return [_rec("hold_irrigation_rain", ctx, z, category="irrigation", priority="medium",
                         title=f"Hold irrigation in {z.zone_name}: {rain48} mm of rain forecast in 48 h",
                         rationale=f"The root zone is past the stress threshold, but about 80 % of the forecast rain "
                         f"({rain48 * 0.8:.1f} mm effective) would cover the {net_mm} mm deficit. Re-check if it does not fall.",
                         action={"type": "hold_irrigation", "recheck_after_hours": 24}, factors=base,
                         data_conf=data_conf, limitations=["Forecast rain is uncertain; light showers mostly evaporate."],
                         valid_hours=24, expected_impact={"water_saved_mm": gross_mm, "water_saved_liters": volume})]  # fmt: skip
        severe = w["status"] == "severe"
        return [_rec("irrigate_now", ctx, z, category="irrigation", priority="critical" if severe else "high",
                     title=f"Irrigate {z.zone_name} now: {amount}",
                     rationale=f"Root-zone depletion {w['depletion_mm']} mm is past the {w['raw_mm']} mm stress threshold "
                     f"for {crop}" + (" and at the wilting point" if severe else "") + ".",
                     action=action, factors=base, data_conf=data_conf, limitations=lims, valid_hours=12)]  # fmt: skip
    d = w.get("days_to_stress")
    if d is not None and d <= 2:
        stage_note = (
            f" The crop is at {z.stage['name'].lower()}, the stage where water stress costs the most yield (FAO-33)."
            if sensitive and z.stage
            else ""
        )
        return [_rec("irrigation_soon", ctx, z, category="irrigation", priority="high" if sensitive else "medium",
                     title=f"Plan irrigation for {z.zone_name} within {max(d, 1)} day(s)",
                     rationale=f"At forecast evapotranspiration, depletion passes the {w['raw_mm']} mm threshold in "
                     f"about {d} day(s) for {crop}.{stage_note}",
                     action={**action, "type": "plan_irrigation", "within_days": max(d, 1)},
                     factors=[*base, _f("Days to stress", d, "days", "FAO-56 projection with forecast ET0", sim)],
                     data_conf=data_conf, limitations=lims, valid_hours=24)]  # fmt: skip
    return []


# ------------------------------------------------------------------ soil chemistry
def soil_rules(ctx: FarmContext, z: ZoneContext) -> list[dict[str, Any]]:
    out = []
    comps = z.soil.get("components", {})
    crop = (z.soil.get("crop") or {}).get("name")
    lab_age = (z.soil.get("inputs") or {}).get("lab_test_age_days")
    for key, label in (("nitrogen", "nitrogen"), ("phosphorus", "phosphorus"), ("potassium", "potassium")):
        c = comps.get(key)
        if not c or c["status"] != "low":
            continue
        sim, from_lab = _is_sim(c["source"]), c["source"].startswith("lab")
        out.append(_rec("nutrient_low", ctx, z, category="fertilizer", variant=key,
            priority="medium" if from_lab else "low",
            title=f"{label.capitalize()} is low in {z.zone_name}" + ("" if from_lab else ": confirm with a lab test"),
            rationale=f"{label.capitalize()} {c['value']} {c['unit']} is below the Soil Health Card 'low' limit "
            f"({c['target'][0]} {c['unit']}).",
            action={"type": "nutrient_review", "nutrient": key,
                    "next_step": f"Apply {label} per the Soil Health Card / local extension recommendation for "
                    f"{crop or 'your crop'}" if from_lab else "Send a soil sample to a lab before fertilising"},
            factors=[_f(label.capitalize(), c["value"], c["unit"], c["source"], sim),
                     _f("Low limit", c["target"][0], c["unit"], c["target_source"])],
            data_conf=c["confidence"],
            limitations=["No fertilizer dose is given here; dose optimisation arrives in Phase 13."]
            + ([] if from_lab else ["Low-cost NPK probes are indicative only."]),
            valid_hours=24 * 7))  # fmt: skip
    oc = comps.get("organic_carbon")
    if oc and oc["status"] == "low":
        out.append(_rec("organic_matter_low", ctx, z, category="soil", priority="medium" if oc["source"].startswith("lab") else "low",
            title=f"Organic carbon is low in {z.zone_name}: build soil organic matter",
            rationale=f"Organic carbon {oc['value']} % is below the Soil Health Card 'low' limit ({oc['target'][0]} %). "
            "Low organic matter reduces water holding and nutrient supply.",
            action={"type": "organic_matter", "next_step": "Add well-decomposed compost or farmyard manure, "
                    "retain crop residues, or grow a green-manure crop"},
            factors=[_f("Organic carbon", oc["value"], "%", oc["source"], _is_sim(oc["source"])),
                     _f("Low limit", oc["target"][0], "%", oc["target_source"])],
            data_conf=oc["confidence"],
            limitations=["Organic carbon changes slowly (seasons to years); no application rate is given."],
            valid_hours=24 * 30))  # fmt: skip
    ph = comps.get("ph")
    if ph and ph["status"] in ("acidic", "alkaline"):
        lo, hi = ph["target"]
        acidic = ph["status"] == "acidic"
        from_lab = ph["source"].startswith("lab")
        out.append(_rec("ph_out_of_range", ctx, z, category="soil", priority="medium" if from_lab else "low",
            title=f"Soil pH {ph['value']} is {'below' if acidic else 'above'} the {ph['target_source']} in {z.zone_name}",
            rationale=f"Target {lo} to {hi}. " + ("Acidic soils are usually corrected with agricultural lime; the rate "
            "depends on a lime-requirement (buffer pH) test." if acidic else "Alkaline soils are managed with organic "
            "matter and, for sodic soils, gypsum, based on a lab test."),
            action={"type": "ph_correction_review", "direction": "raise" if acidic else "lower",
                    "next_step": "Ask the lab for lime requirement" if acidic else "Ask the lab for ESP / gypsum requirement"},
            factors=[_f("pH", ph["value"], "", ph["source"], _is_sim(ph["source"])), _f("Target", f"{lo} to {hi}", "", ph["target_source"])],
            data_conf=ph["confidence"], limitations=["No amendment rate is given without a lab requirement test."],
            valid_hours=24 * 14))  # fmt: skip
    sal = comps.get("salinity")
    if sal and sal["status"] not in ("normal",):
        out.append(_rec("salinity", ctx, z, category="soil", priority="high" if "moderately" in sal["status"] or "strongly" in sal["status"] else "medium",
            title=f"Salinity ({sal['status']}) in {z.zone_name}",
            rationale=f"EC {sal['value']} dS/m. Salts reduce water uptake; check irrigation-water EC and allow leaching "
            "where drainage permits.",
            action={"type": "salinity_review", "next_step": "Test irrigation water EC; consider a leaching irrigation"},
            factors=[_f("EC", sal["value"], "dS/m", sal["source"], _is_sim(sal["source"]))],
            data_conf=sal["confidence"], limitations=["Crop salt tolerance differs; thresholds are general classes."],
            valid_hours=24 * 14))  # fmt: skip
    if lab_age is None:
        out.append(_rec("soil_test_needed", ctx, z, category="soil", priority="low",
            title=f"Get a lab soil test for {z.zone_name}",
            rationale="There is no lab soil test from the last 12 months, so nutrient and pH advice relies on sensors "
            "or is missing.",
            action={"type": "soil_test", "parameters": ["pH", "N", "P", "K", "organic carbon", "EC"]},
            factors=[_f("Latest lab test", "none in 365 days", "", "soil measurements")],
            data_conf=1.0, limitations=[], valid_hours=24 * 30))  # fmt: skip
    return out


# ------------------------------------------------------------------ crop health & weather
def health_rules(ctx: FarmContext, z: ZoneContext) -> list[dict[str, Any]]:
    out = []
    for d in z.recent_disease[:1]:  # most recent only
        out.append(_rec("confirm_suspected_disease", ctx, z, category="crop", priority="medium",
            title=f"Scout {z.zone_name} to confirm suspected {d['label']}",
            rationale=f"A leaf photo on {d['detected_at']:%d %b} was flagged as a possible {d['label']} by "
            f"{d['model']} ({d['confidence']:.0%} model confidence). These models were wrong on most field photos in "
            "testing, so confirm in the field before any treatment.",
            action={"type": "scout", "what": d["label"], "spray_windows": spray_windows(ctx)},
            factors=[_f("Disease check", d["label"], "", f"disease check #{d['id']} ({d['model']})"),
                     _f("Model confidence", round(d["confidence"], 3), "", d["model"])],
            data_conf=1.0, limitations=["Do not treat on the model's result alone; confirm with an agronomist."],
            valid_hours=24 * 3))  # fmt: skip
    humid = [h for h in ctx.hourly if h["valid_at"] < ctx.now + timedelta(hours=72)
             and (h["relative_humidity_pct"] or 0) >= HUMID_RH
             and h["temperature_c"] is not None and HUMID_T[0] <= h["temperature_c"] <= HUMID_T[1]]  # fmt: skip
    if len(humid) >= HUMID_HOURS and (z.soil.get("crop") or z.recent_disease):
        out.append(_rec("humid_weather_scouting", ctx, z, category="crop", priority="low",
            title=f"Humid spell ahead: scout {z.zone_name} for foliar disease",
            rationale=f"{len(humid)} of the next 72 forecast hours have RH >= {HUMID_RH:.0f} % at {HUMID_T[0]:.0f} to "
            f"{HUMID_T[1]:.0f} deg C, conditions that favour many leaf diseases.",
            action={"type": "scout", "when": "after the humid spell"},
            factors=[_f("Humid hours (next 72 h)", len(humid), "h", "Open-Meteo forecast")],
            data_conf=0.8, limitations=["Generic humidity rule, not a validated disease-risk model for this crop."],
            valid_hours=72))  # fmt: skip
    return out


def spray_windows(ctx: FarmContext) -> list[str]:
    """Hours in the next 48 h with wind < 4 m/s, temp < 30 deg C and rain chance < 40 % for the next 6 h."""
    rows = [h for h in ctx.hourly if ctx.now <= h["valid_at"] < ctx.now + timedelta(hours=48)]
    ok = []
    for i, h in enumerate(rows):
        nxt = rows[i : i + 6]
        if ((h["wind_speed_ms"] or 0) < 4 and (h["temperature_c"] or 0) < 30 and 6 <= h["local_hour"] <= 18
                and all((n["precipitation_probability_pct"] or 0) < 40 for n in nxt)):  # fmt: skip
            ok.append(h["valid_at"].isoformat())
    return ok[:6]


def farm_rules(ctx: FarmContext) -> list[dict[str, Any]]:
    out = []
    hot = [d for d in ctx.daily[:3] if d["temp_max_c"] is not None and d["temp_max_c"] >= HEAT_C]
    if hot:
        peak = max(d["temp_max_c"] for d in hot)
        out.append(_rec("heat_stress", ctx, None, category="crop", priority="medium",
            title=f"Heat ahead: up to {peak:.0f} deg C in the next 3 days",
            rationale="Daytime highs at or above 35 deg C raise crop water use and can damage flowers and fruit set.",
            action={"type": "heat_preparation", "steps": ["Irrigate in the early morning", "Avoid spraying in the heat",
                    "Check soil moisture daily"], "days": [d["date"].isoformat() for d in hot]},
            factors=[_f("Max temperature", peak, "deg C", "Open-Meteo forecast")],
            data_conf=0.8, limitations=["Crop heat tolerance varies with variety and stage."], valid_hours=72))  # fmt: skip
    silent = [(z, s) for z in ctx.zones for s in z.silent_sensors]
    if silent:
        names = ", ".join(f"{s['name']} ({z.zone_name})" for z, s in silent[:5])
        out.append(_rec("sensors_silent", ctx, None, category="general", priority="medium",
            title=f"{len(silent)} sensor(s) have not reported for {SILENT_HOURS}+ hours",
            rationale=f"Advice for these zones may use stale data: {names}.",
            action={"type": "check_sensors", "sensor_ids": [s["id"] for _, s in silent]},
            factors=[_f("Silent sensors", len(silent), "", "sensor readings")],
            data_conf=1.0, limitations=[], valid_hours=12))  # fmt: skip
    return out


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate(ctx: FarmContext) -> list[dict[str, Any]]:
    recs = farm_rules(ctx)
    for z in ctx.zones:
        recs += water_rules(ctx, z) + soil_rules(ctx, z) + health_rules(ctx, z)
    return sorted(recs, key=lambda r: (PRIORITY_ORDER[r["priority"]], -r["confidence"]))
