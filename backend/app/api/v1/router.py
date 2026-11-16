from fastapi import APIRouter

from app.api.v1.endpoints import (
    alerting,
    crops,
    dashboard,
    disease,
    farms,
    federated,
    iot,
    irrigation,
    nutrients,
    operations,
    realtime,
    recommendations,
    reports,
    soil,
    system,
    vision,
    yields,
)

api_router = APIRouter()
api_router.include_router(system.router)
for module in (
    farms,
    crops,
    iot,
    operations,
    realtime,
    dashboard,
    soil,
    vision,
    disease,
    recommendations,
    irrigation,
    nutrients,
    yields,
    federated,
    reports,
    alerting,
):
    api_router.include_router(module.router)
