"""Database-backed sensor simulator.

The engine reads the *real* application data: which simulated sensors exist, each
farm's location, each zone's soil profile and latest soil test, and any irrigation
or fertilizer applications recorded through the API. Those records change the
simulated soil (water from a logged irrigation raises soil moisture, a logged urea
application raises nitrogen). It writes readings through the same `store()` path as
real hardware, so every downstream feature treats them identically, except that the
sensors are `source='simulated'` and every reading is labelled `is_simulated`.
"""

from __future__ import annotations

import random
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Device,
    Farm,
    FarmZone,
    FertilizerApplication,
    IrrigationEvent,
    Sensor,
    SoilMeasurement,
    SoilProfile,
)
from app.services import readings as readings_service
from app.services.readings import StoredReading
from app.simulator.physics import SENSOR_NOISE, Climate, SoilState, measure, true_value

SOIL_SENSOR_TYPES = {"soil_moisture", "soil_temperature", "soil_ph", "nitrogen", "phosphorus", "potassium"}


@dataclass
class _SensorRng:
    rng: random.Random
    offset: float  # fixed calibration offset of this particular unit


class SimulatorEngine:
    def __init__(self, seed: int = 0, fault_rate: float = 0.0005) -> None:
        self.seed = seed
        self.fault_rate = fault_rate
        self._climates: dict[int, Climate] = {}
        self._soils: dict[tuple[int, int | None], SoilState] = {}
        self._sensor_rngs: dict[int, _SensorRng] = {}
        self.last_tick: datetime | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ queries
    @staticmethod
    def simulated_sensors(db: Session, farm_id: int | None = None) -> list[Sensor]:
        stmt = (
            select(Sensor)
            .outerjoin(Device, Device.id == Sensor.device_id)
            .where(Sensor.source == "simulated", Sensor.status == "active")
            .where(or_(Sensor.device_id.is_(None), Device.status == "active"))
            .order_by(Sensor.id)
        )
        if farm_id is not None:
            stmt = stmt.where(Sensor.farm_id == farm_id)
        return list(db.scalars(stmt))

    # ------------------------------------------------------------ state
    def forget_farm(self, farm_id: int) -> None:
        """Drop cached state so it is re-initialised from the database (e.g. after a backfill)."""
        with self._lock:
            self._climates.pop(farm_id, None)
            for key in [k for k in self._soils if k[0] == farm_id]:
                del self._soils[key]

    def _climate(self, farm: Farm) -> Climate:
        climate = self._climates.get(farm.id)
        if climate is None:
            lat = float(farm.latitude) if farm.latitude is not None else 0.0
            lon = float(farm.longitude) if farm.longitude is not None else 0.0
            climate = Climate(lat=lat, lon=lon, rng=random.Random(self.seed * 7_919 + farm.id * 1_009))
            self._climates[farm.id] = climate
        return climate

    def _soil(self, db: Session, farm_id: int, zone_id: int | None, sensors: list[Sensor]) -> SoilState:
        key = (farm_id, zone_id)
        soil = self._soils.get(key)
        if soil is not None:
            return soil
        soil = SoilState(rng=random.Random(self.seed * 104_729 + (zone_id or 0) * 7_907 + farm_id))
        if zone_id is not None:
            zone = db.get(FarmZone, zone_id)
            if zone is not None and zone.area_hectares:
                soil.area_m2 = float(zone.area_hectares) * 10_000
            profile = db.scalars(
                select(SoilProfile).where(SoilProfile.zone_id == zone_id).order_by(SoilProfile.id.desc())
            ).first()
            if profile is not None:
                if profile.field_capacity_pct is not None:
                    soil.field_capacity = float(profile.field_capacity_pct)
                if profile.wilting_point_pct is not None:
                    soil.wilting_point = float(profile.wilting_point_pct)
                soil.saturation = max(soil.field_capacity + 8, soil.saturation)
                soil.moisture = (soil.field_capacity + soil.wilting_point) / 2 + 5
            test = db.scalars(
                select(SoilMeasurement)
                .where(SoilMeasurement.zone_id == zone_id)
                .order_by(SoilMeasurement.measured_at.desc())
            ).first()
            if test is not None:
                for attr, col in (
                    ("ph", test.ph),
                    ("nitrogen", test.nitrogen_mg_kg),
                    ("phosphorus", test.phosphorus_mg_kg),
                    ("potassium", test.potassium_mg_kg),
                    ("moisture", test.moisture_pct),
                ):
                    if col is not None:
                        setattr(soil, attr, float(col))
        # Continue from what the sensors last reported, so restarts do not jump.
        latest = readings_service.latest_per_sensor(db, farm_id)
        for sensor in sensors:
            last = latest.get(sensor.id)
            if last is None or last.quality != "good":
                continue
            field_name = {
                "soil_moisture": "moisture",
                "soil_ph": "ph",
                "nitrogen": "nitrogen",
                "phosphorus": "phosphorus",
                "potassium": "potassium",
                "leaf_wetness": "leaf_wetness",
                "water_level": "tank_level",
                "soil_temperature": "soil_temp_c",
            }.get(sensor.sensor_type)
            if field_name:
                setattr(soil, field_name, float(last.value))
        self._soils[key] = soil
        return soil

    def _sensor_rng(self, sensor: Sensor) -> _SensorRng:
        state = self._sensor_rngs.get(sensor.id)
        if state is None:
            rng = random.Random(self.seed * 15_485_863 + sensor.id * 104_723)
            sigma = SENSOR_NOISE[sensor.sensor_type][0]
            state = _SensorRng(rng=rng, offset=rng.gauss(0, sigma * 0.5))
            self._sensor_rngs[sensor.id] = state
        return state

    # ------------------------------------------------------------ recorded field operations
    @staticmethod
    def _apply_operations(
        db: Session, zone_soils: dict[int, SoilState], start: datetime, end: datetime
    ) -> None:
        if not zone_soils:
            return
        zone_ids = list(zone_soils)
        irrigations = db.scalars(
            select(IrrigationEvent).where(
                IrrigationEvent.zone_id.in_(zone_ids),
                IrrigationEvent.status.in_(["running", "completed"]),
                IrrigationEvent.started_at > start,
                IrrigationEvent.started_at <= end,
                IrrigationEvent.volume_liters.is_not(None),
            )
        )
        for ev in irrigations:
            zone_soils[ev.zone_id].apply_irrigation(float(ev.volume_liters or 0))
        fertilizers = db.scalars(
            select(FertilizerApplication).where(
                FertilizerApplication.zone_id.in_(zone_ids),
                FertilizerApplication.applied_at > start,
                FertilizerApplication.applied_at <= end,
            )
        )
        for fa in fertilizers:
            zone_soils[fa.zone_id].apply_fertilizer(
                float(fa.quantity_kg), float(fa.n_pct or 0), float(fa.p_pct or 0), float(fa.k_pct or 0)
            )

    # ------------------------------------------------------------ simulation steps
    def _advance(
        self, db: Session, sensors: list[Sensor], when: datetime, dt: timedelta, window_start: datetime
    ) -> dict[int, float]:
        """Advance every farm/zone involved by dt and return {sensor_id: measured value}."""
        dt_h = dt.total_seconds() / 3600
        by_farm: dict[int, list[Sensor]] = defaultdict(list)
        for s in sensors:
            by_farm[s.farm_id].append(s)
        values: dict[int, float] = {}
        for farm_id, farm_sensors in by_farm.items():
            farm = db.get(Farm, farm_id)
            if farm is None:
                continue
            climate = self._climate(farm)
            climate.step(dt_h)
            zone_ids = {s.zone_id for s in farm_sensors}
            soils = {z: self._soil(db, farm_id, z, farm_sensors) for z in zone_ids}
            self._apply_operations(db, {z: s for z, s in soils.items() if z is not None}, window_start, when)
            for soil in soils.values():
                soil.step(climate, when, dt_h)
            for sensor in farm_sensors:
                truth = true_value(sensor.sensor_type, climate, soils[sensor.zone_id], when, dt_h)
                srng = self._sensor_rng(sensor)
                values[sensor.id] = measure(sensor.sensor_type, truth, srng.rng, srng.offset, self.fault_rate)
        return values

    def tick(
        self, db: Session, now: datetime | None = None, interval: timedelta | None = None
    ) -> list[StoredReading]:
        """Produce one reading per active simulated sensor at `now` (no commit)."""
        now = (now or datetime.now(UTC)).replace(microsecond=0)
        with self._lock:
            dt = (now - self.last_tick) if self.last_tick else (interval or timedelta(seconds=10))
            if dt <= timedelta(0):
                return []
            dt = min(dt, timedelta(hours=1))  # after a long pause, don't jump the model by days
            window_start = self.last_tick or now - dt
            sensors = self.simulated_sensors(db)
            values = self._advance(db, sensors, now, dt, window_start)
            self.last_tick = now
        stored: list[StoredReading] = []
        for sensor in sensors:
            if sensor.id in values:
                stored.extend(readings_service.store(db, sensor, [(now, values[sensor.id])], now))
        return stored

    def backfill(
        self, db: Session, farm_id: int, start: datetime, end: datetime, step: timedelta
    ) -> dict[str, Any]:
        """Generate history for one farm between start and end (no commit). Uses a separate model
        state so the live simulation is not disturbed; the caller should then `forget_farm()`."""
        sensors = self.simulated_sensors(db, farm_id)
        if not sensors:
            return {"inserted": 0, "sensors": 0}
        series: dict[int, list[tuple[datetime, float]]] = defaultdict(list)
        t = start.replace(microsecond=0)
        while t <= end:
            for sensor_id, value in self._advance(db, sensors, t, step, t - step).items():
                series[sensor_id].append((t, value))
            t += step
        inserted = 0
        for sensor in sensors:
            inserted += len(readings_service.store(db, sensor, series[sensor.id]))
        return {"inserted": inserted, "sensors": len(sensors)}
