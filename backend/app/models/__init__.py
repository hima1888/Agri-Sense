"""Importing this package registers every table on Base.metadata (used by Alembic)."""

from app.models.ai import AIPrediction, AIRecommendation, ModelVersion
from app.models.crop import Crop, CropCycle, Plant
from app.models.farm import Farm, FarmZone, User
from app.models.iot import Device, Sensor, SensorReading
from app.models.operations import FertilizerApplication, IrrigationEvent, PesticideApplication
from app.models.platform import (
    Alert,
    AuditLog,
    FederatedClient,
    FederatedClientUpdate,
    FederatedLearningRun,
    Report,
)
from app.models.soil import SoilMeasurement, SoilProfile
from app.models.vision import DiseaseDetection, PlantDetection
from app.models.weather import WeatherData

__all__ = [
    "AIPrediction",
    "AIRecommendation",
    "Alert",
    "AuditLog",
    "Crop",
    "CropCycle",
    "Device",
    "DiseaseDetection",
    "Farm",
    "FarmZone",
    "FederatedClient",
    "FederatedClientUpdate",
    "FederatedLearningRun",
    "FertilizerApplication",
    "IrrigationEvent",
    "ModelVersion",
    "PesticideApplication",
    "Plant",
    "PlantDetection",
    "Report",
    "Sensor",
    "SensorReading",
    "SoilMeasurement",
    "SoilProfile",
    "User",
    "WeatherData",
]
