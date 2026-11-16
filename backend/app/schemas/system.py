"""Response contracts for system endpoints. Mirrored by Zod schemas in the frontend."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ServiceState = Literal["ok", "degraded", "not_configured", "planned"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    timestamp: datetime


class DataMode(BaseModel):
    sensors: Literal["none", "simulated", "hardware", "mixed"]
    note: str


class ServiceStatus(BaseModel):
    key: str
    label: str
    state: ServiceState
    detail: str


class SystemInfoResponse(BaseModel):
    name: str
    version: str
    environment: str
    api_prefix: str
    data_mode: DataMode
    services: list[ServiceStatus]
