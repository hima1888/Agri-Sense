from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import AwareDatetime, Field, model_validator

from app.models.enums import DataSource, DeviceStatus, DeviceType, Protocol, ReadingQuality, SensorType
from app.schemas.common import InputModel, Lat, Lon, Name, Num, OutputModel


# --- devices ---------------------------------------------------------------
class DeviceCreate(InputModel):
    name: Name
    device_type: DeviceType
    protocol: Protocol
    zone_id: int | None = None
    hardware_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    firmware_version: Annotated[str, Field(max_length=64)] | None = None
    status: DeviceStatus = "active"


class DeviceUpdate(InputModel):
    name: Name | None = None
    zone_id: int | None = None
    firmware_version: Annotated[str, Field(max_length=64)] | None = None
    status: DeviceStatus | None = None


class DeviceRead(OutputModel):
    id: int
    farm_id: int
    zone_id: int | None
    name: str
    device_type: DeviceType
    source: DataSource
    protocol: Protocol
    hardware_id: str | None
    firmware_version: str | None
    status: DeviceStatus
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- sensors ---------------------------------------------------------------
class TwinPosition(InputModel):
    x: float
    y: float
    z: float


class SensorCreate(InputModel):
    name: Name
    sensor_type: SensorType
    source: DataSource = Field(description="'simulated' or 'hardware'. Must match the device, if any.")
    zone_id: int | None = None
    device_id: int | None = None
    unit: Annotated[str, Field(min_length=1, max_length=16)] | None = Field(
        default=None, description="Defaults to the canonical unit for the sensor type."
    )
    hardware_model: Annotated[str, Field(max_length=100)] | None = None
    status: DeviceStatus = "active"
    min_valid: float | None = None
    max_valid: float | None = None
    latitude: Lat | None = None
    longitude: Lon | None = None
    twin_position: TwinPosition | None = None
    installed_at: datetime | None = None

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.min_valid is not None and self.max_valid is not None and self.min_valid >= self.max_valid:
            raise ValueError("min_valid must be < max_valid")
        return self


class SensorUpdate(InputModel):
    name: Name | None = None
    zone_id: int | None = None
    device_id: int | None = None
    hardware_model: Annotated[str, Field(max_length=100)] | None = None
    status: DeviceStatus | None = None
    min_valid: float | None = None
    max_valid: float | None = None
    latitude: Lat | None = None
    longitude: Lon | None = None
    twin_position: TwinPosition | None = None


class SensorRead(OutputModel):
    id: int
    farm_id: int
    zone_id: int | None
    device_id: int | None
    name: str
    sensor_type: SensorType
    unit: str
    source: DataSource
    is_simulated: bool
    hardware_model: str | None
    status: DeviceStatus
    min_valid: float | None
    max_valid: float | None
    latitude: Num | None
    longitude: Num | None
    twin_position: dict[str, Any] | None
    installed_at: datetime | None
    last_reading_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- readings --------------------------------------------------------------
class ReadingIn(InputModel):
    recorded_at: AwareDatetime = Field(
        description="Must include a timezone offset, e.g. 2026-11-13T08:00:00Z"
    )
    value: Annotated[float, Field(allow_inf_nan=False)]


class ReadingBatch(InputModel):
    readings: Annotated[list[ReadingIn], Field(min_length=1, max_length=1000)]


class IngestResult(OutputModel):
    received: int
    inserted: int
    duplicates: int
    suspect: int


class ReadingRead(OutputModel):
    recorded_at: datetime
    value: float
    quality: ReadingQuality


class ReadingSeries(OutputModel):
    sensor_id: int
    sensor_type: SensorType
    unit: str
    source: DataSource
    is_simulated: bool
    start: datetime
    end: datetime
    count: int
    readings: list[ReadingRead]
