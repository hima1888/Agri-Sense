# ruff: noqa: E501  (compact result dictionaries)
"""Smart irrigation (Phase 12): multi-day plans per zone, scheduling, and water-use accounting."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import irrigation as engine
from app.integrations.open_meteo import SOURCE as WEATHER_SOURCE
from app.models import Farm, FarmZone, IrrigationEvent, User, WeatherData
from app.services import soil
from app.services.weather import daily_summary

HORIZON_DAYS = 7
LIMITATIONS = [
    "FAO-56 water balance with published crop and soil values; not a trained model.",
    "Assumes uniform soil across the zone and that each irrigation wets the whole root zone.",
    "Forecast rain and ET0 are uncertain beyond 2 to 3 days; re-plan daily.",
    "Volumes need the zone area; durations need your system's flow rate (not recorded).",
]


def _forecast(
    db: Session, farm: Farm, now: datetime
) -> tuple[list[dict[str, Any]], dict[date, list[dict[str, Any]]]]:
    tz = ZoneInfo(farm.timezone)
    midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.scalars(
        select(WeatherData)
        .where(
            WeatherData.farm_id == farm.id,
            WeatherData.source == WEATHER_SOURCE,
            WeatherData.kind == "forecast",
            WeatherData.valid_at >= midnight.astimezone(UTC),
            WeatherData.valid_at < (midnight + timedelta(days=HORIZON_DAYS)).astimezone(UTC),
        )
        .order_by(WeatherData.valid_at)
    ).all()
    hourly: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        local = r.valid_at.astimezone(tz)
        hourly[local.date()].append(
            {
                "local_hour": local.hour,
                "wind_speed_ms": None if r.wind_speed_ms is None else float(r.wind_speed_ms),
            }
        )
    daily = [d for d in daily_summary(list(rows), tz) if d["date"] >= midnight.date()]
    return daily, hourly


def zone_plan(db: Session, zone: FarmZone, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    farm = db.get(Farm, zone.farm_id)
    assert farm is not None
    tz = ZoneInfo(farm.timezone)
    a = soil.assess(db, zone, now)
    w = a["water"]
    area = float(zone.area_hectares) if zone.area_hectares else None
    base: dict[str, Any] = {
        "zone_id": zone.id,
        "zone_name": zone.name,
        "crop": (a.get("crop") or {}).get("name"),
        "irrigation_method": zone.irrigation_method,
        "area_hectares": area,
        "generated_at": now,
        "method": "FAO-56 daily root-zone water balance with forecast ET0 and rain",
        "uses_simulated_data": a["uses_simulated_data"],
        "limitations": list(LIMITATIONS),
        "scheduled": _scheduled(db, zone, now),
    }
    if not w:
        return {**base, "status": "no_moisture_data", "water": None, "plan": None, "confidence": 0.0,
                "message": "No soil-moisture reading: add a soil test with moisture or provision moisture sensors."}  # fmt: skip
    daily, hourly = _forecast(db, farm, now)
    if not daily:
        base["limitations"].insert(0, "No stored forecast: refresh weather on the dashboard to plan ahead.")
    args = {"depletion_mm": w["depletion_mm"], "taw_mm": w["taw_mm"], "raw_mm": w["raw_mm"], "kc": w["kc"],
            "forecast": daily, "method": zone.irrigation_method, "area_ha": area}  # fmt: skip
    p = engine.plan(**args)
    ignoring_rain = engine.plan(**args, rain_aware=False)
    scheduled_dates = {s["local_date"] for s in base["scheduled"]}
    for e in p["events"]:
        e["window"] = engine.best_window(hourly.get(e["date"], []), zone.irrigation_method)
        start = datetime.combine(e["date"], time(e["window"]["start_local_hour"]), tz)
        e["scheduled_for"] = start.astimezone(UTC)
        e["already_scheduled"] = e["date"].isoformat() in scheduled_dates
    saved_mm = round(max(0.0, ignoring_rain["total_gross_mm"] - p["total_gross_mm"]), 1)
    if a["uses_simulated_data"]:
        base["limitations"].insert(
            0, "Moisture comes from SIMULATED sensors: the plan demonstrates the method only."
        )
    if not area:
        base["limitations"].append(
            "Zone area unknown: amounts are in mm only. Add the area in zone settings."
        )
    return {
        **base,
        "status": "irrigate_today" if p["events"] and p["events"][0]["day_index"] == 0 else ("planned" if p["events"] else "no_irrigation_needed"),
        "water": {k: w[k] for k in ("moisture_pct", "field_capacity_pct", "wilting_point_pct", "taw_mm", "raw_mm", "depletion_mm",
                                     "status", "kc", "root_depth_m", "measured_at", "irrigation_since_mm", "sources")},
        "plan": p,
        "rain_aware_saving": {
            "gross_mm": saved_mm,
            "volume_liters": round(saved_mm * area * 10_000) if area else None,
            "basis": "same rules with forecast rain ignored, over the forecast horizon (an estimate, not a measurement)",
        },
        "confidence": w["confidence"],
    }  # fmt: skip


def _scheduled(db: Session, zone: FarmZone, now: datetime) -> list[dict[str, Any]]:
    farm = db.get(Farm, zone.farm_id)
    assert farm is not None
    tz = ZoneInfo(farm.timezone)
    rows = db.scalars(
        select(IrrigationEvent)
        .where(
            IrrigationEvent.zone_id == zone.id,
            IrrigationEvent.status == "scheduled",
            IrrigationEvent.scheduled_for >= now - timedelta(days=1),
        )
        .order_by(IrrigationEvent.scheduled_for)
    ).all()
    return [
        {
            "id": e.id,
            "scheduled_for": e.scheduled_for,
            "local_date": e.scheduled_for.astimezone(tz).date().isoformat(),
            "volume_liters": None if e.volume_liters is None else float(e.volume_liters),
            "trigger": e.trigger,
        }
        for e in rows
        if e.scheduled_for is not None
    ]


def schedule(
    db: Session, user: User, zone: FarmZone, day: date, now: datetime | None = None
) -> IrrigationEvent | None:
    """Turn the plan's irrigation for ``day`` into a scheduled irrigation event; None if the plan has none."""
    p = zone_plan(db, zone, now)
    event = next((e for e in (p["plan"] or {}).get("events", []) if e["date"] == day), None)
    if event is None or event["already_scheduled"]:
        return None
    method = zone.irrigation_method if zone.irrigation_method in engine.APPLICATION_EFFICIENCY else "manual"
    row = IrrigationEvent(
        zone_id=zone.id,
        created_by=user.id,
        method=method,
        trigger="scheduled",
        status="scheduled",
        scheduled_for=event["scheduled_for"],
        volume_liters=None if event["volume_liters"] is None else Decimal(event["volume_liters"]),
        notes=f"Smart irrigation plan: {event['net_mm']} mm net / {event['gross_mm']} mm gross. {event['reason']}.",
    )
    db.add(row)
    db.flush()
    return row


def water_use(db: Session, zone: FarmZone, days: int, now: datetime | None = None) -> dict[str, Any]:
    """Applied water (completed events) vs an estimate of crop need from stored weather for the same days."""
    now = now or datetime.now(UTC)
    farm = db.get(Farm, zone.farm_id)
    assert farm is not None
    tz = ZoneInfo(farm.timezone)
    today = now.astimezone(tz).date()
    start_day = today - timedelta(days=days)
    start = datetime.combine(start_day, time(0), tz).astimezone(UTC)
    end = datetime.combine(today, time(0), tz).astimezone(UTC)
    area = float(zone.area_hectares) if zone.area_hectares else None
    when = func.coalesce(IrrigationEvent.ended_at, IrrigationEvent.started_at)
    events = db.scalars(
        select(IrrigationEvent).where(
            IrrigationEvent.zone_id == zone.id,
            IrrigationEvent.status == "completed",
            when >= start,
            when < end,
        )
    ).all()
    liters = sum(float(e.volume_liters) for e in events if e.volume_liters is not None)
    no_volume = sum(1 for e in events if e.volume_liters is None)
    net_mm = (
        sum(
            engine.net_mm_from_volume(float(e.volume_liters), area, e.method)
            for e in events
            if e.volume_liters is not None
        )
        if area
        else None
    )

    rows = db.scalars(
        select(WeatherData).where(
            WeatherData.farm_id == farm.id, WeatherData.source == WEATHER_SOURCE, WeatherData.kind == "forecast",
            WeatherData.valid_at >= start, WeatherData.valid_at < end,
        )
    ).all()  # fmt: skip
    weather_days = daily_summary(list(rows), tz)
    kc = (soil.assess(db, zone, now).get("water") or {}).get("kc") or 1.0
    need = sum(
        max(0.0, kc * d["et0_mm"] - engine.effective_rain(d["precipitation_mm"])) for d in weather_days
    )
    covered = len(weather_days)
    ratio = round(net_mm / need, 2) if net_mm is not None and need > 0 and covered == days else None
    return {
        "zone_id": zone.id,
        "days": days,
        "from": start_day,
        "to": today - timedelta(days=1),
        "events": len(events),
        "events_without_volume": no_volume,
        "applied_liters": round(liters),
        "applied_gross_mm": round(liters / (area * 10_000), 1) if area else None,
        "applied_net_mm": None if net_mm is None else round(net_mm, 1),
        "estimated_need_mm": round(need, 1),
        "weather_days_covered": covered,
        "applied_to_need_ratio": ratio,
        "kc": kc,
        "basis": "need = sum over days of Kc x ET0 minus effective rain, from stored Open-Meteo hourly data; "
        "the ratio is shown only when every day in the window has weather",
    }  # fmt: skip


def farm_overview(db: Session, farm: Farm, now: datetime | None = None) -> list[dict[str, Any]]:
    zones = db.scalars(select(FarmZone).where(FarmZone.farm_id == farm.id).order_by(FarmZone.id)).all()
    out = []
    for z in zones:
        p = zone_plan(db, z, now)
        nxt = (p["plan"] or {}).get("events", [])
        out.append(
            {
                "zone_id": z.id,
                "zone_name": z.name,
                "status": p["status"],
                "depletion_mm": (p["water"] or {}).get("depletion_mm"),
                "raw_mm": (p["water"] or {}).get("raw_mm"),
                "next_irrigation": nxt[0]["date"] if nxt else None,
                "next_gross_mm": nxt[0]["gross_mm"] if nxt else None,
                "horizon_volume_liters": (p["plan"] or {}).get("total_volume_liters"),
                "uses_simulated_data": p["uses_simulated_data"],
                "confidence": p["confidence"],
            }
        )
    return out
