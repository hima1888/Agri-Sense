"""Allowed values for constrained text columns.

Each set is declared once as a typing.Literal (used by Pydantic API schemas and mypy)
and exposed as a tuple (used to build the database CHECK constraints).
"""

from typing import Literal, get_args

UserRole = Literal["farmer", "agronomist", "admin"]

ZoneType = Literal["field", "greenhouse", "orchard", "nursery", "pasture", "other"]
IrrigationMethod = Literal["drip", "sprinkler", "flood", "pivot", "furrow", "manual", "none"]

# USDA soil texture classes.
SoilTexture = Literal[
    "sand", "loamy_sand", "sandy_loam", "loam", "silt_loam", "silt", "sandy_clay_loam",
    "clay_loam", "silty_clay_loam", "sandy_clay", "silty_clay", "clay",
]  # fmt: skip
SoilMeasurementSource = Literal["lab", "field_kit", "manual", "sensor_aggregate"]

CropCategory = Literal[
    "cereal", "vegetable", "fruit", "legume", "oilseed", "fiber", "fodder", "spice", "other"
]
CropCycleStatus = Literal["planned", "growing", "harvested", "failed"]
PlantHealth = Literal["healthy", "stressed", "diseased", "dead", "unknown"]

DeviceType = Literal["esp32", "gateway", "weather_station", "simulator", "other"]
Protocol = Literal["http", "mqtt", "simulator"]
DataSource = Literal["simulated", "hardware"]
DeviceStatus = Literal["active", "inactive", "maintenance", "faulty"]
SensorType = Literal[
    "temperature", "humidity", "soil_moisture", "soil_temperature", "soil_ph", "nitrogen",
    "phosphorus", "potassium", "light", "rainfall", "leaf_wetness", "water_level",
]  # fmt: skip
ReadingQuality = Literal["good", "suspect", "bad"]

WeatherKind = Literal["observation", "forecast"]

IrrigationTrigger = Literal["manual", "scheduled", "ai_recommendation", "sensor_threshold"]
IrrigationStatus = Literal["scheduled", "running", "completed", "cancelled", "failed"]
FertilizerMethod = Literal["broadcast", "banding", "fertigation", "foliar", "top_dressing", "other"]
PesticideType = Literal[
    "insecticide", "fungicide", "herbicide", "bactericide", "nematicide", "biological", "other",
]  # fmt: skip
QuantityUnit = Literal["kg", "l"]

DetectionSubject = Literal["plant", "leaf", "fruit", "vegetable"]
DiseaseSeverity = Literal["none", "low", "moderate", "high"]

ModelTask = Literal[
    "plant_recognition", "disease_detection", "yield_prediction", "irrigation",
    "fertilizer", "soil_health", "anomaly_detection", "other",
]  # fmt: skip
ModelStatus = Literal["training", "staging", "production", "archived"]
PredictionType = Literal[
    "yield", "irrigation_need", "disease_risk", "nutrient_deficiency", "soil_health", "weather_risk", "other",
]  # fmt: skip
RecommendationCategory = Literal[
    "irrigation", "fertilizer", "pesticide", "soil", "crop", "harvest", "general"
]
Priority = Literal["low", "medium", "high", "critical"]
RecommendationStatus = Literal["pending", "accepted", "rejected", "applied", "expired"]

AlertSeverity = Literal["info", "warning", "critical"]
AlertCategory = Literal["sensor", "soil", "weather", "disease", "irrigation", "nutrient", "device", "system"]
AlertStatus = Literal["open", "acknowledged", "resolved"]

ReportType = Literal[
    "farm_summary", "sustainability", "yield", "soil", "irrigation", "chemical_usage", "custom"
]
ReportStatus = Literal["pending", "generating", "ready", "failed"]

FlRunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
FlClientStatus = Literal["active", "inactive", "revoked"]

USER_ROLES = get_args(UserRole)
ZONE_TYPES = get_args(ZoneType)
IRRIGATION_METHODS = get_args(IrrigationMethod)
SOIL_TEXTURES = get_args(SoilTexture)
SOIL_MEASUREMENT_SOURCES = get_args(SoilMeasurementSource)
CROP_CATEGORIES = get_args(CropCategory)
CROP_CYCLE_STATUSES = get_args(CropCycleStatus)
PLANT_HEALTH = get_args(PlantHealth)
DEVICE_TYPES = get_args(DeviceType)
PROTOCOLS = get_args(Protocol)
DATA_SOURCES = get_args(DataSource)
DEVICE_STATUSES = get_args(DeviceStatus)
SENSOR_TYPES = get_args(SensorType)
READING_QUALITY = get_args(ReadingQuality)
WEATHER_KINDS = get_args(WeatherKind)
IRRIGATION_TRIGGERS = get_args(IrrigationTrigger)
IRRIGATION_STATUSES = get_args(IrrigationStatus)
FERTILIZER_METHODS = get_args(FertilizerMethod)
PESTICIDE_TYPES = get_args(PesticideType)
QUANTITY_UNITS = get_args(QuantityUnit)
DETECTION_SUBJECTS = get_args(DetectionSubject)
DISEASE_SEVERITY = get_args(DiseaseSeverity)
MODEL_TASKS = get_args(ModelTask)
MODEL_STATUSES = get_args(ModelStatus)
PREDICTION_TYPES = get_args(PredictionType)
RECOMMENDATION_CATEGORIES = get_args(RecommendationCategory)
PRIORITIES = get_args(Priority)
RECOMMENDATION_STATUSES = get_args(RecommendationStatus)
ALERT_SEVERITIES = get_args(AlertSeverity)
ALERT_CATEGORIES = get_args(AlertCategory)
ALERT_STATUSES = get_args(AlertStatus)
REPORT_TYPES = get_args(ReportType)
REPORT_STATUSES = get_args(ReportStatus)
FL_RUN_STATUSES = get_args(FlRunStatus)
FL_CLIENT_STATUSES = get_args(FlClientStatus)
