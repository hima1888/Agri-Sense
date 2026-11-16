"""Digital-twin scene description for one farm, computed from stored records.

Coordinate system: metres, origin at the farm reference point, x = east, z = south
(three.js convention: y is up; north is -z).

What comes from data vs. what is schematic:
  * DATA: zones (GeoJSON boundary when present, otherwise sized from area_hectares),
    crop type and growth stage (crop cycle + catalogue cycle length), sensors and their
    latest readings, tank level (water_level sensors), irrigation in progress
    (irrigation events), weather (Open-Meteo observations), sun position (computed).
  * SCHEMATIC: buildings, roads, pump, pipe routes, gateway and solar positions are not
    stored anywhere yet, so they are laid out deterministically and flagged
    `schematic: true` so the UI can label them as such.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import growth as growth_model
from app.knowledge.diseases import key_for_label
from app.models import (
    Crop,
    CropCycle,
    Device,
    DiseaseDetection,
    Farm,
    FarmZone,
    IrrigationEvent,
    Sensor,
    WeatherData,
)
from app.services import readings as readings_service
from app.simulator.physics import solar_azimuth_deg, solar_elevation_deg

DEFAULT_ZONE_HA = 0.5
ROAD_GAP_M = 14.0
ZONE_ASPECT = 1.6  # width : depth for auto-laid-out zones
IRRIGATION_ACTIVE_WINDOW = timedelta(minutes=60)
# A saved disease check colours its zone for this long; after that the zone shows "no recent check".
DISEASE_RECENT_WINDOW = timedelta(days=30)
EARTH_M_PER_DEG = 111_320.0

# Row spacing (m) and plant form by crop category; used to draw crop rows.
CROP_FORM: dict[str, tuple[float, str]] = {
    "cereal": (0.25, "grass"),
    "fodder": (0.3, "grass"),
    "vegetable": (0.75, "bush"),
    "spice": (0.6, "bush"),
    "legume": (0.45, "bush"),
    "oilseed": (0.45, "bush"),
    "fiber": (0.9, "bush"),
    "fruit": (5.0, "tree"),
    "other": (0.6, "bush"),
}


def _project(lon: float, lat: float, ref_lon: float, ref_lat: float) -> tuple[float, float]:
    """Equirectangular projection to local metres (x east, z south). Fine at farm scale."""
    x = (lon - ref_lon) * EARTH_M_PER_DEG * math.cos(math.radians(ref_lat))
    z = -(lat - ref_lat) * EARTH_M_PER_DEG
    return x, z


def _polygon_from_boundary(boundary: dict[str, Any] | None, farm: Farm) -> list[tuple[float, float]] | None:
    if not boundary or farm.latitude is None or farm.longitude is None:
        return None
    geom = boundary.get("geometry", boundary) if boundary.get("type") == "Feature" else boundary
    try:
        if geom.get("type") != "Polygon":
            return None
        ring = geom["coordinates"][0]
        pts = [_project(float(p[0]), float(p[1]), float(farm.longitude), float(farm.latitude)) for p in ring]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts if len(pts) >= 3 else None


def _auto_layout(zones: list[FarmZone]) -> dict[int, list[tuple[float, float]]]:
    """Shelf-pack rectangles sized by area, separated by road gaps, centred on the origin."""
    sizes = []
    for z in zones:
        area = float(z.area_hectares) * 10_000 if z.area_hectares else DEFAULT_ZONE_HA * 10_000
        depth = math.sqrt(area / ZONE_ASPECT)
        sizes.append((z.id, depth * ZONE_ASPECT, depth))
    total = sum(w * d for _, w, d in sizes) or 1.0
    max_row = max(math.sqrt(total) * 1.8, max((w for _, w, _ in sizes), default=0))
    rects: dict[int, tuple[float, float, float, float]] = {}
    x = y = row_h = 0.0
    for zid, w, d in sizes:
        if x > 0 and x + w > max_row:
            x, y, row_h = 0.0, y + row_h + ROAD_GAP_M, 0.0
        rects[zid] = (x, y, w, d)
        x += w + ROAD_GAP_M
        row_h = max(row_h, d)
    if not rects:
        return {}
    min_x = min(r[0] for r in rects.values())
    max_x = max(r[0] + r[2] for r in rects.values())
    min_y = min(r[1] for r in rects.values())
    max_y = max(r[1] + r[3] for r in rects.values())
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    return {
        zid: [(rx - cx, ry - cy), (rx + w - cx, ry - cy), (rx + w - cx, ry + d - cy), (rx - cx, ry + d - cy)]
        for zid, (rx, ry, w, d) in rects.items()
    }


def _bbox(poly: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs, zs = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(zs), max(xs), max(zs)


def _r(v: float) -> float:
    return round(v, 2)


def build(db: Session, farm: Farm, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    zones = list(db.scalars(select(FarmZone).where(FarmZone.farm_id == farm.id).order_by(FarmZone.id)))
    sensors = list(db.scalars(select(Sensor).where(Sensor.farm_id == farm.id).order_by(Sensor.id)))
    latest = readings_service.latest_per_sensor(db, farm.id)

    auto = _auto_layout([z for z in zones if _polygon_from_boundary(z.boundary, farm) is None])
    polygons = {z.id: _polygon_from_boundary(z.boundary, farm) or auto[z.id] for z in zones}

    # Active crop per zone, with growth stage from planting date and catalogue cycle length.
    cycles = db.execute(
        select(CropCycle, Crop)
        .join(Crop, Crop.id == CropCycle.crop_id)
        .where(CropCycle.zone_id.in_([z.id for z in zones]), CropCycle.status.in_(["growing", "planned"]))
        .order_by(CropCycle.zone_id, CropCycle.id.desc())
    ).all()
    crop_by_zone: dict[int, dict[str, Any]] = {}
    today: date = now.date()
    for cycle, crop in cycles:
        if cycle.zone_id in crop_by_zone:
            continue
        growth = None
        if cycle.status == "growing" and cycle.planted_on and crop.typical_cycle_days:
            growth = max(0.0, min(1.0, (today - cycle.planted_on).days / crop.typical_cycle_days))
        spacing, form = CROP_FORM.get(crop.category, CROP_FORM["other"])
        stage_key = stage_name = None
        if cycle.status == "growing" and cycle.planted_on:
            try:
                days = (
                    (cycle.expected_harvest_on - cycle.planted_on).days
                    if cycle.expected_harvest_on and cycle.expected_harvest_on > cycle.planted_on
                    else crop.typical_cycle_days
                )
                model = growth_model.stages(crop.common_name, days)
                at = growth_model.current(model, cycle.planted_on, today)
                stage_key = at["stage_key"] if at else None
                stage_name = next((st["name"] for st in model["stages"] if st["key"] == stage_key), None)
            except growth_model.UnsupportedCropError:
                pass
        crop_by_zone[cycle.zone_id] = {
            "stage_key": stage_key,
            "stage_name": stage_name,
            "cycle_id": cycle.id,
            "crop_name": crop.common_name,
            "variety": cycle.variety,
            "category": crop.category,
            "status": cycle.status,
            "planted_on": cycle.planted_on,
            "expected_harvest_on": cycle.expected_harvest_on,
            "growth_fraction": round(growth, 3) if growth is not None else None,
            "row_spacing_m": spacing,
            "form": form,
        }

    irrigating = {
        ev.zone_id: ev
        for ev in db.scalars(
            select(IrrigationEvent)
            .where(
                IrrigationEvent.zone_id.in_([z.id for z in zones]),
                IrrigationEvent.started_at.is_not(None),
                IrrigationEvent.started_at >= now - IRRIGATION_ACTIVE_WINDOW,
                IrrigationEvent.started_at <= now,
                IrrigationEvent.status.in_(["running", "completed"]),
            )
            .order_by(IrrigationEvent.started_at)
        )
        if ev.status == "running" or (ev.ended_at is None or ev.ended_at >= now)
    }

    # Latest saved disease check per zone (stored results only: possible disease / healthy / uncertain).
    health_by_zone: dict[int, dict[str, Any]] = {}
    for det in db.scalars(
        select(DiseaseDetection)
        .where(
            DiseaseDetection.zone_id.in_([z.id for z in zones]),
            DiseaseDetection.detected_at >= now - DISEASE_RECENT_WINDOW,
        )
        .order_by(DiseaseDetection.detected_at.desc(), DiseaseDetection.id.desc())
    ):
        if det.zone_id is None or det.zone_id in health_by_zone:
            continue
        outcome = (det.explanation or {}).get(
            "outcome", "possible_disease" if not det.is_healthy else "possible_healthy"
        )
        state = {"possible_disease": "disease", "possible_healthy": "healthy"}.get(outcome, "uncertain")
        health_by_zone[det.zone_id] = {
            "state": state,
            "detection_id": det.id,
            "label": det.disease_label,
            "confidence": float(det.confidence),
            "severity": det.severity,
            "knowledge_key": key_for_label(det.disease_label) if state == "disease" else None,
            "detected_at": det.detected_at,
        }

    def zone_latest(zone_id: int, sensor_type: str) -> float | None:
        vals = [
            latest[s.id].value
            for s in sensors
            if s.zone_id == zone_id
            and s.sensor_type == sensor_type
            and s.id in latest
            and latest[s.id].quality == "good"
        ]
        return round(sum(vals) / len(vals), 2) if vals else None

    zone_out: list[dict[str, Any]] = []
    for z in zones:
        poly = polygons[z.id]
        x0, z0, x1, z1 = _bbox(poly)
        ev = irrigating.get(z.id)
        zone_out.append(
            {
                "id": z.id,
                "name": z.name,
                "zone_type": z.zone_type,
                "area_hectares": float(z.area_hectares) if z.area_hectares is not None else None,
                "irrigation_method": z.irrigation_method,
                "polygon": [[_r(px), _r(pz)] for px, pz in poly],
                "center": [_r((x0 + x1) / 2), _r((z0 + z1) / 2)],
                "size": [_r(x1 - x0), _r(z1 - z0)],
                "layout": "boundary" if _polygon_from_boundary(z.boundary, farm) else "auto",
                "crop": crop_by_zone.get(z.id),
                "soil_moisture": zone_latest(z.id, "soil_moisture"),
                "temperature": zone_latest(z.id, "temperature"),
                "irrigating": ev is not None,
                "irrigation_started_at": ev.started_at if ev else None,
                "health": health_by_zone.get(z.id),
            }
        )

    # Sensors: twin_position is zone-local (provisioning grid x in [-4.5, 4.5], z in [-3, 3]).
    zone_geom = {z["id"]: z for z in zone_out}
    sensor_out = []
    for i, s in enumerate(sensors):
        zg = zone_geom.get(s.zone_id) if s.zone_id is not None else None
        tp = s.twin_position or {}
        if zg is not None:
            hx, hz = zg["size"][0] / 2, zg["size"][1] / 2
            nx = max(-0.85, min(0.85, float(tp.get("x", 0.0)) / 6))
            nz = max(-0.85, min(0.85, float(tp.get("z", 0.0)) / 4))
            pos = [zg["center"][0] + nx * hx, 0.0, zg["center"][1] + nz * hz]
        else:
            pos = [float(tp.get("x", i * 3.0)), 0.0, float(tp.get("z", 0.0))]
        last = latest.get(s.id)
        sensor_out.append(
            {
                "id": s.id,
                "name": s.name,
                "zone_id": s.zone_id,
                "device_id": s.device_id,
                "sensor_type": s.sensor_type,
                "unit": s.unit,
                "source": s.source,
                "is_simulated": s.is_simulated,
                "status": s.status,
                "position": [_r(v) for v in pos],
                "latest": (
                    {"value": last.value, "quality": last.quality, "recorded_at": last.recorded_at}
                    if last
                    else None
                ),
            }
        )

    # Farm extent (zones) and schematic infrastructure placed just outside it, to the south.
    all_pts = [p for z in zone_out for p in z["polygon"]] or [[0.0, 0.0]]
    min_x, max_x = min(p[0] for p in all_pts), max(p[0] for p in all_pts)
    min_z, max_z = min(p[1] for p in all_pts), max(p[1] for p in all_pts)
    yard_z = max_z + ROAD_GAP_M + 18
    yard_x = min_x + 20

    level_vals = [
        latest[s.id].value
        for s in sensors
        if s.sensor_type == "water_level" and s.id in latest and latest[s.id].quality == "good"
    ]
    tank_level = round(sum(level_vals) / len(level_vals), 1) if level_vals else None
    has_devices = db.scalar(select(Device.id).where(Device.farm_id == farm.id).limit(1)) is not None
    weather_types = {"temperature", "humidity", "rainfall", "light"}
    obs = db.scalars(
        select(WeatherData)
        .where(WeatherData.farm_id == farm.id, WeatherData.kind == "observation")
        .order_by(WeatherData.valid_at.desc())
        .limit(1)
    ).first()

    infra: list[dict[str, Any]] = [
        {
            "kind": "farmhouse",
            "id": "farmhouse",
            "position": [yard_x, 0, yard_z + 10],
            "rotation": 0,
            "schematic": True,
        },
        {
            "kind": "shed",
            "id": "shed",
            "position": [yard_x + 24, 0, yard_z + 12],
            "rotation": 0,
            "schematic": True,
        },
        {
            "kind": "road",
            "id": "road-main",
            "from": [min_x - 10, yard_z - 6],
            "to": [max_x + 10, yard_z - 6],
            "width": 5,
            "schematic": True,
        },
        {
            "kind": "road",
            "id": "road-access",
            "from": [yard_x + 12, yard_z - 6],
            "to": [yard_x + 12, yard_z + 30],
            "width": 4,
            "schematic": True,
        },
        {
            "kind": "channel",
            "id": "channel",
            "from": [min_x - 16, min_z - 6],
            "to": [min_x - 16, yard_z + 26],
            "width": 3,
            "schematic": True,
        },
    ]
    irrigated = [z for z in zone_out if z["irrigation_method"] not in (None, "none")]
    if tank_level is not None or irrigated:
        tank_pos = [yard_x + 46, 0, yard_z + 6]
        pump_pos = [tank_pos[0] + 8, 0, tank_pos[2]]
        infra.append(
            {
                "kind": "tank",
                "id": "tank",
                "position": tank_pos,
                "level_pct": tank_level,
                "capacity_l": 20_000,
                "schematic": tank_level is None,
            }
        )
        infra.append(
            {
                "kind": "pump",
                "id": "pump",
                "position": pump_pos,
                "schematic": True,
                "running": any(iz["irrigating"] for iz in irrigated),
            }
        )
        for pipe_zone in irrigated:
            edge = [pipe_zone["center"][0], max(p[1] for p in pipe_zone["polygon"])]
            infra.append(
                {
                    "kind": "pipe",
                    "id": f"pipe-{pipe_zone['id']}",
                    "zone_id": pipe_zone["id"],
                    "path": [
                        [pump_pos[0], pump_pos[2]],
                        [pump_pos[0], yard_z - 10],
                        [edge[0], yard_z - 10],
                        edge,
                    ],
                    "flowing": pipe_zone["irrigating"],
                    "schematic": True,
                }
            )
    if any(s.sensor_type in weather_types for s in sensors) or obs is not None:
        infra.append(
            {
                "kind": "weather_station",
                "id": "weather-station",
                "position": [max_x + 12, 0, min_z + 10],
                "schematic": True,
            }
        )
    if has_devices:
        infra.append(
            {"kind": "gateway", "id": "gateway", "position": [yard_x + 6, 0, yard_z + 2], "schematic": True}
        )
    infra.append(
        {
            "kind": "solar",
            "id": "solar",
            "position": [yard_x + 70, 0, yard_z + 14],
            "schematic": True,
            "optional": True,
        }
    )

    lat = float(farm.latitude) if farm.latitude is not None else None
    lon = float(farm.longitude) if farm.longitude is not None else None
    sun = (
        {
            "elevation_deg": round(solar_elevation_deg(lat, lon, now), 1),
            "azimuth_deg": round(solar_azimuth_deg(lat, lon, now), 1),
        }
        if lat is not None and lon is not None
        else None
    )
    weather = (
        {
            "observed_at": obs.valid_at,
            "temperature_c": float(obs.temperature_c) if obs.temperature_c is not None else None,
            "wind_speed_ms": float(obs.wind_speed_ms) if obs.wind_speed_ms is not None else None,
            "wind_direction_deg": float(obs.wind_direction_deg)
            if obs.wind_direction_deg is not None
            else None,
            "cloud_cover_pct": float(obs.cloud_cover_pct) if obs.cloud_cover_pct is not None else None,
            "precipitation_mm": float(obs.precipitation_mm) if obs.precipitation_mm is not None else None,
        }
        if obs
        else None
    )
    return {
        "farm_id": farm.id,
        "farm_name": farm.name,
        "generated_at": now,
        "units": "metres; x east, z south, y up",
        "extent": {"min": [_r(min_x), _r(min_z)], "max": [_r(max_x), _r(max_z)]},
        "sun": sun,
        "weather": weather,
        "zones": zone_out,
        "sensors": sensor_out,
        "infrastructure": infra,
    }
