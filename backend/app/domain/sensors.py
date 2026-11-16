"""Per-sensor-type defaults: canonical unit and physically plausible range.

The range is used to flag readings as `suspect` at ingestion (not to reject them),
and will drive the simulator in Phase 5. Ranges reflect what common low-cost field
sensors (DHT22, capacitive soil probes, RS485 NPK/pH probes, BH1750, tipping-bucket
rain gauges) can physically report, not agronomic optima.
"""

from dataclasses import dataclass

from app.models.enums import SensorType


@dataclass(frozen=True)
class SensorSpec:
    unit: str
    min_valid: float
    max_valid: float
    label: str


SENSOR_SPECS: dict[SensorType, SensorSpec] = {
    "temperature": SensorSpec("°C", -40, 80, "Air temperature"),
    "humidity": SensorSpec("%", 0, 100, "Relative humidity"),
    "soil_moisture": SensorSpec("%", 0, 100, "Volumetric soil moisture"),
    "soil_temperature": SensorSpec("°C", -20, 60, "Soil temperature"),
    "soil_ph": SensorSpec("pH", 3, 10, "Soil pH"),
    "nitrogen": SensorSpec("mg/kg", 0, 1999, "Soil nitrogen"),
    "phosphorus": SensorSpec("mg/kg", 0, 1999, "Soil phosphorus"),
    "potassium": SensorSpec("mg/kg", 0, 1999, "Soil potassium"),
    "light": SensorSpec("lux", 0, 120_000, "Light intensity"),
    "rainfall": SensorSpec("mm", 0, 300, "Rainfall (per interval)"),
    "leaf_wetness": SensorSpec("%", 0, 100, "Leaf wetness"),
    "water_level": SensorSpec("%", 0, 100, "Tank water level"),
}
