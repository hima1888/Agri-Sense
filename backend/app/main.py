"""AGRI-SENSE API entrypoint. Run with: uvicorn app.main:app --reload"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from app.api.errors import install_error_handlers
from app.api.v1.router import api_router
from app.core.config import APP_NAME, APP_VERSION, Settings, get_settings
from app.core.hardening import RateLimiter, RequestLimits, SecurityHeaders
from app.core.logging import configure_logging
from app.db.session import make_engine
from app.realtime.broadcaster import Broadcaster
from app.services.alert_runner import AlertRunner
from app.simulator.runner import SimulatorRunner

logger = logging.getLogger("agri_sense")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.broadcaster.bind_loop(asyncio.get_running_loop())
        runner: SimulatorRunner | None = None
        sim_engine = None
        if settings.simulator_enabled and settings.database_configured:
            sim_engine = make_engine(settings.database_url)
            runner = SimulatorRunner(
                sessionmaker(bind=sim_engine, expire_on_commit=False),
                app.state.broadcaster,
                settings.simulator_interval_seconds,
            )
            app.state.simulator = runner
            runner.start()
        alerts: AlertRunner | None = None
        if settings.alerts_enabled and settings.database_configured:
            sim_engine = sim_engine or make_engine(settings.database_url)
            alerts = AlertRunner(
                sessionmaker(bind=sim_engine, expire_on_commit=False),
                app.state.broadcaster,
                settings.alert_interval_seconds,
            )
            app.state.alerts = alerts
            alerts.start()
        yield
        if alerts is not None:
            await alerts.stop()
        if runner is not None:
            await runner.stop()
        if sim_engine is not None:
            sim_engine.dispose()

    app = FastAPI(
        lifespan=lifespan,
        title=f"{APP_NAME} API",
        version=APP_VERSION,
        description="Backend for the AGRI-SENSE agricultural intelligence platform.",
        # Interactive docs are for development: production exposes neither them nor the schema.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else f"{settings.api_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    # Added last = outermost: headers wrap every response, including 413/429 and CORS preflights.
    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimiter,
            per_minute=settings.rate_limit_per_minute,
            expensive_per_minute=settings.rate_limit_expensive_per_minute,
        )
    app.add_middleware(RequestLimits, max_body_bytes=int((settings.max_upload_mb + 1) * 1_048_576))
    app.add_middleware(SecurityHeaders, hsts=settings.is_production)
    app.state.broadcaster = Broadcaster()
    app.state.simulator = None
    app.state.alerts = None
    install_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    logger.info("AGRI-SENSE API %s starting (env=%s)", APP_VERSION, settings.app_env)
    return app


app = create_app()
