from datetime import datetime
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, Field

from app.models.enums import IrrigationMethod, UserRole, ZoneType
from app.schemas.common import InputModel, Lat, Lon, Name, NonNeg, Notes, Num, OutputModel


def _valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unknown time zone; use an IANA name such as 'Asia/Kolkata'.") from exc
    return value


Timezone = Annotated[
    str, Field(min_length=1, max_length=64, examples=["Asia/Kolkata"]), AfterValidator(_valid_timezone)
]


# --- users -----------------------------------------------------------------
class MeUpdate(InputModel):
    full_name: Name | None = None


class AdminUserUpdate(InputModel):
    full_name: Name | None = None
    role: UserRole | None = None


class UserRead(OutputModel):
    id: UUID
    email: str
    full_name: str | None
    role: UserRole
    created_at: datetime
    updated_at: datetime


# --- farms -----------------------------------------------------------------
class FarmCreate(InputModel):
    name: Name
    description: Notes | None = None
    latitude: Lat | None = None
    longitude: Lon | None = None
    area_hectares: NonNeg | None = None
    timezone: Timezone = "UTC"


class FarmUpdate(InputModel):
    name: Name | None = None
    description: Notes | None = None
    latitude: Lat | None = None
    longitude: Lon | None = None
    area_hectares: NonNeg | None = None
    timezone: Timezone | None = None


class FarmRead(OutputModel):
    id: int
    owner_id: UUID
    name: str
    description: str | None
    latitude: Num | None
    longitude: Num | None
    area_hectares: Num | None
    timezone: str
    created_at: datetime
    updated_at: datetime


# --- zones -----------------------------------------------------------------
class ZoneCreate(InputModel):
    name: Name
    zone_type: ZoneType = "field"
    area_hectares: NonNeg | None = None
    irrigation_method: IrrigationMethod | None = None
    boundary: dict[str, Any] | None = Field(default=None, description="GeoJSON Polygon")


class ZoneUpdate(InputModel):
    name: Name | None = None
    zone_type: ZoneType | None = None
    area_hectares: NonNeg | None = None
    irrigation_method: IrrigationMethod | None = None
    boundary: dict[str, Any] | None = None


class ZoneRead(OutputModel):
    id: int
    farm_id: int
    name: str
    zone_type: ZoneType
    area_hectares: Num | None
    irrigation_method: IrrigationMethod | None
    boundary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
