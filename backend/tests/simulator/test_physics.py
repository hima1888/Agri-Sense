"""The simulator's physical models behave plausibly and deterministically."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.simulator.physics import Climate, SoilState, measure, solar_elevation_deg, true_value

LAT, LON = 17.385, 78.4867  # Hyderabad; local solar noon ~ 06:45 UTC
DAY = datetime(2026, 11, 13, tzinfo=UTC)


def at_ist(hour: float) -> datetime:
    return DAY + timedelta(hours=hour - 5.5)


def clear_climate() -> Climate:
    return Climate(lat=LAT, lon=LON, rng=random.Random(1), cloud=0.0)


def test_sun_is_up_at_noon_and_down_at_night() -> None:
    assert solar_elevation_deg(LAT, LON, at_ist(12.25)) > 45
    assert solar_elevation_deg(LAT, LON, at_ist(0)) < -30
    c = clear_climate()
    assert c.light_lux(at_ist(0)) == 0
    assert 70_000 < c.light_lux(at_ist(12.25)) < 120_000


def test_diurnal_temperature_and_humidity_cycle() -> None:
    c = clear_climate()
    dawn, afternoon = at_ist(4), at_ist(15)
    assert c.air_temperature_c(afternoon) - c.air_temperature_c(dawn) > 8
    assert c.relative_humidity(dawn) > c.relative_humidity(afternoon) + 20
    for h in range(24):
        assert 15 <= c.relative_humidity(at_ist(h)) <= 100


def test_seasons_flip_between_hemispheres() -> None:
    july = datetime(2026, 7, 15, tzinfo=UTC)
    north = Climate(lat=45, lon=0, rng=random.Random(0))
    south = Climate(lat=-45, lon=0, rng=random.Random(0))
    assert north.seasonal_mean_c(july) > south.seasonal_mean_c(july) + 10


def test_soil_dries_in_sun_and_wets_with_rain_and_irrigation() -> None:
    c = clear_climate()
    sunny = SoilState(rng=random.Random(0), moisture=28)
    for i in range(48):  # a sunny day, 15-minute steps from 07:00
        sunny.step(c, at_ist(7 + i / 4), 0.25)
    # ~4-5 mm/day reference ET (typical for the Deccan in November) = ~1.5 % of a 300 mm root zone.
    assert 25.5 < sunny.moisture < 27.2

    rainy_climate = clear_climate()
    rainy_climate.raining, rainy_climate.rain_mm_per_h = True, 10.0
    wet = SoilState(rng=random.Random(0), moisture=20)
    wet.step(rainy_climate, at_ist(10), 1.0)
    assert wet.moisture > 22  # 8 mm infiltrated into a 300 mm root zone ~ +2.7 %

    irrigated = SoilState(rng=random.Random(0), moisture=20, tank_level=80)
    irrigated.apply_irrigation(10_000)  # 10 m³ on 1 ha = 1 mm, half of a 20 m³ tank
    assert irrigated.tank_level == 80  # nothing has flowed yet
    irrigated.step(c, at_ist(2), 1.0)  # night: no evaporation; a 1 h step delivers it all
    assert irrigated.tank_level == pytest.approx(30)
    assert irrigated.moisture == pytest.approx(20 + 1 / 300 * 100, abs=0.02)


def test_irrigation_is_delivered_gradually_with_the_tank() -> None:
    soil = SoilState(rng=random.Random(0), moisture=20, tank_level=90)
    soil.apply_irrigation(10_000)
    for _ in range(6):  # one minute of 10 s ticks
        soil.step(clear_climate(), at_ist(2), 10 / 3600)
    delivered_pct = soil.moisture - 20
    drawn_pct = 90 - soil.tank_level
    assert 0 < delivered_pct < 0.02  # ~1.6 % of the water in the first minute
    assert drawn_pct == pytest.approx(delivered_pct * 300 / 100 * 10_000 / 20_000 * 100, rel=1e-6)


def test_drainage_pulls_saturated_soil_back_toward_field_capacity() -> None:
    soil = SoilState(rng=random.Random(0), moisture=44, field_capacity=30)
    for _ in range(24):
        soil.step(clear_climate(), at_ist(1), 1.0)
    assert 30 <= soil.moisture < 33


def test_fertilizer_raises_nutrients_in_proportion() -> None:
    soil = SoilState(rng=random.Random(0))
    n0, p0, k0 = soil.nitrogen, soil.phosphorus, soil.potassium
    soil.apply_fertilizer(quantity_kg=500, n_pct=46, p_pct=0, k_pct=0)  # urea on 1 ha
    assert soil.nitrogen - n0 == pytest.approx(500e6 / soil.soil_mass_kg * 0.46 * 0.6)
    assert (soil.phosphorus, soil.potassium) == (p0, k0)


def test_sensor_readout_noise_resolution_and_bounds() -> None:
    rng = random.Random(3)
    assert measure("rainfall", 0.53, rng, 0.0, fault_rate=0) == pytest.approx(0.6)  # 0.2 mm tipping bucket
    assert measure("nitrogen", 140.4, rng, 0.0, fault_rate=0) % 1 == 0
    assert measure("humidity", 99.9, random.Random(0), 5.0, fault_rate=0) <= 100
    assert measure("light", 0.0, rng, 0.0, fault_rate=0) == 0
    # Percentages never leave 0..100 and amounts never go negative, whatever the noise.
    assert all(measure("water_level", 0.0, rng, -0.3, fault_rate=0) >= 0 for _ in range(200))
    assert all(measure("leaf_wetness", 100.0, rng, 1.0, fault_rate=0) <= 100 for _ in range(200))
    # Noise is small relative to the signal.
    temps = [measure("temperature", 25.0, rng, 0.0, fault_rate=0) for _ in range(500)]
    assert 24.4 < sum(temps) / len(temps) < 25.6
    assert max(abs(t - 25) for t in temps) < 1.0


def test_rare_faults_produce_outliers() -> None:
    rng = random.Random(9)
    values = [measure("temperature", 25.0, rng, 0.0, fault_rate=0.5) for _ in range(200)]
    assert any(v > 80 or v < -40 for v in values)  # outside the DHT22 range -> flagged suspect at ingest


def test_same_seed_same_series() -> None:
    def run(seed: int) -> list[float]:
        c = Climate(lat=LAT, lon=LON, rng=random.Random(seed))
        s = SoilState(rng=random.Random(seed))
        out = []
        t = DAY
        for _ in range(200):
            c.step(0.25)
            s.step(c, t, 0.25)
            out.append(round(true_value("soil_moisture", c, s, t, 0.25), 6))
            t += timedelta(minutes=15)
        return out

    assert run(42) == run(42)
    assert run(42) != run(43)
