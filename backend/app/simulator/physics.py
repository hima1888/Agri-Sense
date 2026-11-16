"""Physically-motivated, deterministic models behind the sensor simulator.

These are deliberately simple, documented approximations, NOT agronomic truth:
  * solar position: NOAA-style declination / hour-angle approximation;
  * air temperature: seasonal mean by latitude + diurnal sinusoid damped by cloud;
  * humidity: Magnus formula from a dew point that tracks the daily mean;
  * light: clear-sky illuminance from solar elevation, reduced by cloud;
  * rain: two-state Markov chain (dry/wet) with random intensity;
  * soil water: single-bucket model (ET out, rain/irrigation in, drainage above field capacity);
  * nutrients: slow crop uptake, step increases from recorded fertilizer applications.

All randomness comes from `random.Random` instances seeded from farm/zone/sensor ids,
so the same inputs always produce the same series (testable, reproducible).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------- sun & sky


def _declination_and_hour_angle(lon: float, when: datetime) -> tuple[float, float]:
    """Solar declination and hour angle (radians), NOAA approximation."""
    doy = when.timetuple().tm_yday
    hours_utc = when.hour + when.minute / 60 + when.second / 3600
    gamma = 2 * math.pi / 365 * (doy - 1 + (hours_utc - 12) / 24)
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
    )
    eq_time_min = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    solar_time_min = hours_utc * 60 + eq_time_min + 4 * lon
    return decl, math.radians(solar_time_min / 4 - 180)


def solar_elevation_deg(lat: float, lon: float, when: datetime) -> float:
    """Approximate solar elevation angle (degrees) at a UTC instant."""
    decl, hour_angle = _declination_and_hour_angle(lon, when)
    phi = math.radians(lat)
    cos_zenith = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(hour_angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, cos_zenith))))


def solar_azimuth_deg(lat: float, lon: float, when: datetime) -> float:
    """Solar azimuth in degrees clockwise from true north (90 = east, 180 = south)."""
    decl, hour_angle = _declination_and_hour_angle(lon, when)
    phi = math.radians(lat)
    az_from_south = math.atan2(
        math.sin(hour_angle), math.cos(hour_angle) * math.sin(phi) - math.tan(decl) * math.cos(phi)
    )
    return (math.degrees(az_from_south) + 180) % 360


def local_solar_hour(lon: float, when: datetime) -> float:
    return (when.hour + when.minute / 60 + lon / 15) % 24


def clear_sky_lux(elevation_deg: float) -> float:
    if elevation_deg <= 0:
        return 0.0
    return float(115_000 * math.sin(math.radians(elevation_deg)) ** 1.15)


def saturation_vapour_pressure(temp_c: float) -> float:
    """Magnus formula, hPa."""
    return 6.1094 * math.exp(17.625 * temp_c / (temp_c + 243.04))


# ---------------------------------------------------------------- farm climate


@dataclass
class Climate:
    """Weather shared by every sensor on one farm."""

    lat: float
    lon: float
    rng: random.Random
    cloud: float = 0.3  # 0 clear .. 1 overcast
    raining: bool = False
    rain_mm_per_h: float = 0.0
    temp_anomaly: float = 0.0  # slow AR(1) departure from the climatological curve, °C

    def seasonal_mean_c(self, when: datetime) -> float:
        abs_lat = abs(self.lat)
        annual_mean = 27.5 - 0.0055 * abs_lat**2  # ~26 °C at 17°N, ~13 °C at 51°N
        amplitude = 0.22 * abs_lat  # larger seasons away from the equator
        peak_doy = 200 if self.lat >= 0 else 17  # mid-July north, mid-January south
        doy = when.timetuple().tm_yday
        return annual_mean + amplitude * math.cos(2 * math.pi * (doy - peak_doy) / 365)

    def air_temperature_c(self, when: datetime) -> float:
        hour = local_solar_hour(self.lon, when)
        diurnal_amp = 6.0 * (1 - 0.6 * self.cloud)
        diurnal = diurnal_amp * math.sin(2 * math.pi * (hour - 9) / 24)  # min ~03:00, max ~15:00
        rain_cooling = 2.5 if self.raining else 0.0
        return self.seasonal_mean_c(when) + diurnal + self.temp_anomaly - rain_cooling

    def dew_point_c(self, when: datetime) -> float:
        # Dew point follows the daily mean; wetter air while raining.
        return self.seasonal_mean_c(when) + self.temp_anomaly - (2.0 if self.raining else 6.5)

    def relative_humidity(self, when: datetime) -> float:
        t = self.air_temperature_c(when)
        td = min(self.dew_point_c(when), t)
        return max(15.0, min(100.0, 100 * saturation_vapour_pressure(td) / saturation_vapour_pressure(t)))

    def light_lux(self, when: datetime) -> float:
        transmittance = 1 - 0.75 * float(self.cloud**2.5)
        if self.raining:
            transmittance *= 0.6
        return clear_sky_lux(solar_elevation_deg(self.lat, self.lon, when)) * transmittance

    def step(self, dt_hours: float) -> None:
        r = self.rng
        # Rain: Markov chain, more likely to start under cloud.
        if self.raining:
            if r.random() < 1 - math.exp(-0.35 * dt_hours):
                self.raining = False
                self.rain_mm_per_h = 0.0
        elif r.random() < 1 - math.exp(-0.04 * self.cloud * dt_hours):
            self.raining = True
            self.rain_mm_per_h = min(40.0, r.lognormvariate(0.6, 0.8))
        # Cloud: mean-reverting, overcast while raining.
        target = 0.9 if self.raining else 0.3
        self.cloud += (target - self.cloud) * min(1.0, dt_hours / 3) + r.gauss(0, 0.05 * math.sqrt(dt_hours))
        self.cloud = max(0.0, min(1.0, self.cloud))
        # Temperature anomaly: AR(1) with ~2-day memory.
        phi = math.exp(-dt_hours / 48)
        self.temp_anomaly = phi * self.temp_anomaly + r.gauss(0, 1.2 * math.sqrt(1 - phi**2))


# ---------------------------------------------------------------- zone soil & water


@dataclass
class SoilState:
    """Soil water, temperature and chemistry for one zone."""

    field_capacity: float = 30.0  # % volumetric
    wilting_point: float = 12.0
    saturation: float = 45.0
    root_depth_mm: float = 300.0
    area_m2: float = 10_000.0
    moisture: float = 26.0
    soil_temp_c: float | None = None
    ph: float = 6.5
    nitrogen: float = 140.0  # mg/kg
    phosphorus: float = 40.0
    potassium: float = 180.0
    leaf_wetness: float = 10.0  # %
    tank_level: float = 80.0  # % of tank capacity
    tank_capacity_l: float = 20_000.0
    pending_irrigation_l: float = 0.0
    rng: random.Random = field(default_factory=random.Random)

    @property
    def soil_mass_kg(self) -> float:
        return self.area_m2 * (self.root_depth_mm / 1000) * 1300  # bulk density ~1.3 t/m³

    def add_water_mm(self, mm: float) -> None:
        self.moisture = min(self.saturation, self.moisture + mm / self.root_depth_mm * 100)

    def apply_irrigation(self, liters: float) -> None:
        """Water reaches the root zone over the following ~hour, drawn from the tank as it flows."""
        self.pending_irrigation_l += liters

    def apply_fertilizer(self, quantity_kg: float, n_pct: float, p_pct: float, k_pct: float) -> None:
        mg_per_kg = quantity_kg * 1_000_000 / self.soil_mass_kg
        # Not all applied nutrient is plant-available in the root zone at once.
        self.nitrogen += mg_per_kg * n_pct / 100 * 0.6
        self.phosphorus += mg_per_kg * p_pct / 100 * 0.3
        self.potassium += mg_per_kg * k_pct / 100 * 0.5

    def step(self, climate: Climate, when: datetime, dt_hours: float) -> None:
        r = self.rng
        air = climate.air_temperature_c(when)
        lux = climate.light_lux(when)

        # Irrigation arrives over ~1 h (exponential), drawn from the tank at the same rate.
        if self.pending_irrigation_l > 0:
            delivered = self.pending_irrigation_l * min(1.0, dt_hours)
            self.pending_irrigation_l -= delivered
            self.add_water_mm(delivered / self.area_m2)
            self.tank_level = max(0.0, self.tank_level - delivered / self.tank_capacity_l * 100)
        # Rain (80% infiltrates).
        self.add_water_mm(climate.rain_mm_per_h * dt_hours * 0.8)
        # Evapotranspiration: driven by radiation and warmth, slowed as soil dries.
        dryness = max(0.0, (self.moisture - self.wilting_point) / (self.field_capacity - self.wilting_point))
        et_mm = 0.7 * (lux / 100_000) * (0.5 + max(air, 0) / 40) * min(1.0, dryness) * dt_hours
        self.moisture -= et_mm / self.root_depth_mm * 100
        # Drainage above field capacity.
        if self.moisture > self.field_capacity:
            self.moisture -= (self.moisture - self.field_capacity) * min(1.0, 0.15 * dt_hours)
        self.moisture = max(self.wilting_point * 0.6, self.moisture)

        # Soil temperature: lagged, damped air temperature.
        daily_mean = climate.seasonal_mean_c(when) + climate.temp_anomaly
        target = daily_mean + 0.35 * (air - daily_mean)
        self.soil_temp_c = target if self.soil_temp_c is None else self.soil_temp_c
        self.soil_temp_c += (target - self.soil_temp_c) * min(1.0, dt_hours / 6)

        # Chemistry: very slow drift, uptake of N/K by the crop.
        self.ph += r.gauss(0, 0.004 * math.sqrt(dt_hours)) + (6.5 - self.ph) * 0.001 * dt_hours
        self.nitrogen = max(0.0, self.nitrogen * (1 - 0.0015 * dt_hours))
        self.phosphorus = max(0.0, self.phosphorus * (1 - 0.0003 * dt_hours))
        self.potassium = max(0.0, self.potassium * (1 - 0.0008 * dt_hours))

        # Leaf wetness: wets with rain or dew (RH >= 92%), dries in sun.
        rh = climate.relative_humidity(when)
        wet_target = 100.0 if climate.raining else (85.0 if rh >= 92 else 0.0)
        rate = 1.5 if wet_target > self.leaf_wetness else 0.4 + lux / 40_000
        self.leaf_wetness += (wet_target - self.leaf_wetness) * min(1.0, rate * dt_hours)

        # Tank: automatic refill valve below 25%.
        if self.tank_level < 25:
            self.tank_level = min(95.0, self.tank_level + 30 * dt_hours)


# ---------------------------------------------------------------- sensor read-out


# (noise sigma, resolution) per sensor type, roughly matching common low-cost sensors.
SENSOR_NOISE: dict[str, tuple[float, float]] = {
    "temperature": (0.15, 0.1),  # DHT22
    "humidity": (1.2, 0.1),  # DHT22
    "soil_moisture": (0.25, 0.1),  # capacitive probe (stable once installed)
    "soil_temperature": (0.1, 0.1),  # DS18B20
    "soil_ph": (0.03, 0.01),
    "nitrogen": (3.0, 1.0),  # RS485 NPK probe (integer mg/kg)
    "phosphorus": (1.5, 1.0),
    "potassium": (3.0, 1.0),
    "light": (0.0, 1.0),  # BH1750 (relative noise applied separately)
    "rainfall": (0.0, 0.2),  # tipping bucket, 0.2 mm per tip
    "leaf_wetness": (2.0, 1.0),
    "water_level": (0.4, 0.1),  # ultrasonic
}


def true_value(sensor_type: str, climate: Climate, soil: SoilState, when: datetime, dt_hours: float) -> float:
    match sensor_type:
        case "temperature":
            return climate.air_temperature_c(when)
        case "humidity":
            return climate.relative_humidity(when)
        case "light":
            return climate.light_lux(when)
        case "rainfall":
            return climate.rain_mm_per_h * dt_hours
        case "soil_moisture":
            return soil.moisture
        case "soil_temperature":
            return soil.soil_temp_c if soil.soil_temp_c is not None else climate.air_temperature_c(when)
        case "soil_ph":
            return soil.ph
        case "nitrogen":
            return soil.nitrogen
        case "phosphorus":
            return soil.phosphorus
        case "potassium":
            return soil.potassium
        case "leaf_wetness":
            return soil.leaf_wetness
        case "water_level":
            return soil.tank_level
    raise ValueError(f"Unknown sensor type {sensor_type!r}")


PERCENT_SENSORS = {"humidity", "soil_moisture", "leaf_wetness", "water_level"}
NON_NEGATIVE_SENSORS = {"light", "rainfall", "nitrogen", "phosphorus", "potassium"}


def measure(
    sensor_type: str, truth: float, rng: random.Random, offset: float, fault_rate: float = 0.0005
) -> float:
    """Apply calibration offset, noise and the sensor's physical limits and resolution.
    Rare faults are injected AFTER the limits, so they stay out of range and get flagged suspect."""
    sigma, resolution = SENSOR_NOISE[sensor_type]
    if sensor_type == "light":
        value = truth * (1 + rng.gauss(0, 0.03))
    elif sensor_type == "rainfall":
        value = truth
    else:
        value = truth + offset + rng.gauss(0, sigma)
    if sensor_type in PERCENT_SENSORS:
        value = min(max(value, 0.0), 100.0)
    elif sensor_type in NON_NEGATIVE_SENSORS:
        value = max(value, 0.0)
    if fault_rate and rng.random() < fault_rate:
        # Occasional glitch (loose wire, EMI): a spike that ingestion should flag as suspect.
        value = truth * rng.choice([3.0, -1.0]) + rng.choice([150.0, -60.0])
    return round(round(value / resolution) * resolution, 4)
