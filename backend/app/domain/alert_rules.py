# ruff: noqa: E501  (user-facing messages)
"""Automatic alert rules (Phase 17). Pure functions over a snapshot of the farm.

Each rule returns *conditions* that are true right now. The alerting service turns them into alerts:
one open alert per condition key (no duplicates), severity updated if it changes, and the alert
auto-resolved when its condition is no longer true. Thresholds have defaults and can be changed per farm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

DEFAULTS: dict[str, float] = {
    "heat_c": 35.0,  # forecast max temperature (warning); +5 deg C = critical
    "frost_c": 2.0,  # forecast min temperature
    "heavy_rain_mm": 50.0,  # forecast rain in one day
    "wind_ms": 12.0,  # forecast hourly wind speed (~43 km/h)
    "silent_hours": 2.0,  # sensor without a reading
    "bad_quality_share": 0.2,  # share of last-hour readings flagged not good
    "disease_days": 3.0,  # how long a possible-disease check keeps its alert open
}
RULES = {
    "soil_dry": "Root zone past the stress threshold (FAO-56 water balance)",
    "soil_saturated": "Soil wetter than field capacity (waterlogging risk)",
    "sensor_silent": "Sensor stopped reporting",
    "sensor_bad_quality": "Sensor sending many flagged readings",
    "heat_forecast": "Extreme heat forecast",
    "frost_forecast": "Frost risk forecast",
    "heavy_rain_forecast": "Heavy rain forecast",
    "wind_forecast": "Strong wind forecast",
    "disease_suspected": "Possible disease flagged by a leaf check",
}
FORECAST_HOURS = 48


def _dates(days: list[dict[str, Any]]) -> str:
    return ", ".join(d["date"].strftime("%d %b") for d in days)


@dataclass
class Condition:
    rule: str
    key: str
    severity: str
    category: str
    title: str
    message: str
    zone_id: int | None = None
    sensor_id: int | None = None
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class Snapshot:
    now: datetime
    zones: list[dict[str, Any]]  # {id, name, water: Phase 8 water dict or None, simulated}
    sensors: list[dict[str, Any]]  # {id, name, zone_id, last_at, recent_total, recent_bad, simulated}
    hourly: list[dict[str, Any]]  # forecast rows: valid_at, temperature_c, precipitation_mm, wind_speed_ms
    daily: list[dict[str, Any]]  # date, temp_min_c, temp_max_c, precipitation_mm
    disease: list[dict[str, Any]]  # {id, zone_id, label, detected_at, model}


def evaluate(s: Snapshot, settings: dict[str, Any] | None = None) -> list[Condition]:
    cfg = {
        **DEFAULTS,
        **{k: float(v) for k, v in ((settings or {}).get("thresholds") or {}).items() if k in DEFAULTS},
    }
    disabled = set((settings or {}).get("disabled_rules") or [])
    out: list[Condition] = []

    for z in s.zones:
        w = z.get("water")
        if not w:
            continue
        sim = " (simulated sensors)" if z.get("simulated") else ""
        if w["status"] in ("stress", "severe"):
            severe = w["status"] == "severe"
            out.append(Condition(
                "soil_dry", f"soil_dry:zone:{z['id']}", "critical" if severe else "warning", "irrigation",
                f"{z['name']}: {'soil at wilting point' if severe else 'crop under water stress'}",
                f"Root-zone depletion {w['depletion_mm']} mm is past the {w['raw_mm']} mm stress threshold (moisture {w['moisture_pct']} %){sim}. See the Irrigation page for how much to apply.",
                zone_id=z["id"], values={"depletion_mm": w["depletion_mm"], "raw_mm": w["raw_mm"], "moisture_pct": w["moisture_pct"]},
            ))  # fmt: skip
        elif w["status"] == "above_field_capacity":
            out.append(Condition(
                "soil_saturated", f"soil_saturated:zone:{z['id']}", "info", "soil",
                f"{z['name']}: soil wetter than field capacity",
                f"Moisture {w['moisture_pct']} % is above field capacity ({w['field_capacity_pct']} %){sim}. Hold irrigation; check drainage if it persists.",
                zone_id=z["id"], values={"moisture_pct": w["moisture_pct"], "field_capacity_pct": w["field_capacity_pct"]},
            ))  # fmt: skip

    silent_after = s.now - timedelta(hours=cfg["silent_hours"])
    for sn in s.sensors:
        if sn["last_at"] is None or sn["last_at"] < silent_after:
            since = (
                "never reported"
                if sn["last_at"] is None
                else f"no reading since {sn['last_at']:%d %b %H:%M} UTC"
            )
            out.append(Condition("sensor_silent", f"sensor_silent:sensor:{sn['id']}", "warning", "device",
                                 f"Sensor '{sn['name']}' is silent", f"{since.capitalize()}. Check power, connectivity and the device.",
                                 zone_id=sn["zone_id"], sensor_id=sn["id"], values={"last_at": sn["last_at"]}))  # fmt: skip
        elif sn["recent_total"] >= 3 and sn["recent_bad"] / sn["recent_total"] >= cfg["bad_quality_share"]:
            share = sn["recent_bad"] / sn["recent_total"]
            out.append(Condition("sensor_bad_quality", f"sensor_bad_quality:sensor:{sn['id']}", "warning", "sensor",
                                 f"Sensor '{sn['name']}' sending flagged readings", f"{share:.0%} of its readings in the last hour were flagged (out of range or suspect). Check calibration and placement.",
                                 zone_id=sn["zone_id"], sensor_id=sn["id"], values={"flagged_share": round(share, 2), "readings": sn["recent_total"]}))  # fmt: skip

    end = s.now + timedelta(hours=FORECAST_HOURS)
    days = [d for d in s.daily if s.now.date() <= d["date"] <= end.date()]
    hot = [d for d in days if d["temp_max_c"] is not None and d["temp_max_c"] >= cfg["heat_c"]]
    if hot:
        peak = max(d["temp_max_c"] for d in hot)
        out.append(Condition("heat_forecast", "heat_forecast:farm", "critical" if peak >= cfg["heat_c"] + 5 else "warning", "weather",
                             f"Heat forecast: up to {peak:.0f} °C", f"Forecast highs reach {peak:.0f} °C ({_dates(hot)}). Irrigate early, avoid spraying in the heat.",
                             values={"peak_c": peak, "threshold_c": cfg["heat_c"]}))  # fmt: skip
    cold = [d for d in days if d["temp_min_c"] is not None and d["temp_min_c"] <= cfg["frost_c"]]
    if cold:
        low = min(d["temp_min_c"] for d in cold)
        out.append(Condition("frost_forecast", "frost_forecast:farm", "critical" if low <= 0 else "warning", "weather",
                             f"Frost risk: down to {low:.0f} °C", f"Forecast lows reach {low:.0f} °C. Protect sensitive crops overnight.",
                             values={"low_c": low, "threshold_c": cfg["frost_c"]}))  # fmt: skip
    wet = [d for d in days if d["precipitation_mm"] >= cfg["heavy_rain_mm"]]
    if wet:
        most = max(d["precipitation_mm"] for d in wet)
        out.append(Condition("heavy_rain_forecast", "heavy_rain_forecast:farm", "warning", "weather",
                             f"Heavy rain forecast: {most:.0f} mm in a day", "Hold irrigation and fertilizer top-dressing; check drainage.",
                             values={"max_daily_mm": most, "threshold_mm": cfg["heavy_rain_mm"]}))  # fmt: skip
    windy = [
        h for h in s.hourly if s.now <= h["valid_at"] < end and (h["wind_speed_ms"] or 0) >= cfg["wind_ms"]
    ]
    if windy:
        top = max(h["wind_speed_ms"] for h in windy)
        out.append(Condition("wind_forecast", "wind_forecast:farm", "warning", "weather",
                             f"Strong wind forecast: {top:.0f} m/s", f"{len(windy)} forecast hour(s) at or above {cfg['wind_ms']:.0f} m/s. Postpone spraying; secure covers.",
                             values={"max_ms": top, "hours": len(windy)}))  # fmt: skip

    recent = s.now - timedelta(days=cfg["disease_days"])
    for d in s.disease:
        if d["detected_at"] >= recent:
            out.append(Condition("disease_suspected", f"disease_suspected:check:{d['id']}", "warning", "disease",
                                 f"Possible {d['label']} flagged", f"A leaf check ({d['model']}) flagged a possible {d['label']}. Scout and confirm before any treatment; the models are screening aids.",
                                 zone_id=d["zone_id"], values={"disease_check_id": d["id"]}))  # fmt: skip

    return [c for c in out if c.rule not in disabled]
