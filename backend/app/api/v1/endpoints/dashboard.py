"""Farm dashboard: summary, time series and weather."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.auth import CurrentUser
from app.api.deps import DbSession
from app.integrations.open_meteo import OpenMeteoClient
from app.models.enums import SensorType
from app.schemas.dashboard import DashboardSummary, FarmSeries, FarmWeather
from app.schemas.twin import FarmTwin
from app.services import access, dashboard, twin, weather

router = APIRouter(tags=["dashboard"])


def get_weather_client() -> OpenMeteoClient:
    return weather.default_client()


WeatherClient = Annotated[OpenMeteoClient, Depends(get_weather_client)]


@router.get("/farms/{farm_id}/dashboard", response_model=DashboardSummary)
def farm_dashboard(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Everything the dashboard's first paint needs, in one request."""
    return dashboard.summary(db, access.farm_for(db, user, farm_id))


@router.get("/farms/{farm_id}/series", response_model=FarmSeries)
def farm_series(
    farm_id: int,
    user: CurrentUser,
    db: DbSession,
    sensor_type: SensorType,
    hours: Annotated[int, Query(ge=1, le=24 * 31)] = 24,
    bucket_minutes: Annotated[int | None, Query(ge=1, le=1440)] = None,
) -> dict[str, Any]:
    """Per-zone averages of one sensor type in time buckets (good-quality readings only)."""
    farm = access.farm_for(db, user, farm_id)
    return dashboard.series(db, farm, sensor_type, hours, bucket_minutes)


@router.get("/farms/{farm_id}/weather", response_model=FarmWeather)
def farm_weather(
    farm_id: int,
    user: CurrentUser,
    db: DbSession,
    client: WeatherClient,
    refresh: Annotated[
        bool, Query(description="Fetch from Open-Meteo now, ignoring the 30 min cache")
    ] = False,
) -> dict[str, Any]:
    """Current conditions, the next 48 h and a 7-day outlook from Open-Meteo, stored per farm."""
    farm = access.farm_for(db, user, farm_id)
    return weather.farm_weather(db, farm, client, force=refresh)


@router.get("/farms/{farm_id}/twin", response_model=FarmTwin, tags=["digital twin"])
def farm_twin(farm_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Scene description for the 3D digital twin, built from stored records.
    Items with `schematic: true` are placed by layout rules, not surveyed positions."""
    return twin.build(db, access.farm_for(db, user, farm_id))
