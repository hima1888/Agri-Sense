"""Background loop that ticks the simulator and pushes readings to live streams."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SensorReading
from app.realtime.broadcaster import Broadcaster
from app.services.readings import READINGS_EVENT, events_by_farm
from app.simulator.engine import SimulatorEngine

logger = logging.getLogger("agri_sense.simulator")
GAP_MAX = timedelta(hours=24)
GAP_STEP = timedelta(minutes=10)


class SimulatorRunner:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        broadcaster: Broadcaster,
        interval_seconds: float,
        engine: SimulatorEngine | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.broadcaster = broadcaster
        self.interval = interval_seconds
        self.engine = engine or SimulatorEngine()
        self.running = False
        self.last_tick_at: datetime | None = None
        self.last_tick_readings = 0
        self.last_error: str | None = None
        self.ticks = 0
        self._task: asyncio.Task[None] | None = None

    def tick_once(self, now: datetime | None = None) -> dict[int, dict[str, Any]]:
        """One simulation step in its own transaction. Returns stream payloads by farm."""
        with self.session_factory() as db:
            stored = self.engine.tick(db, now, timedelta(seconds=self.interval))
            db.commit()
        self.ticks += 1
        self.last_tick_at = datetime.now(UTC)
        self.last_tick_readings = len(stored)
        return events_by_farm(stored)

    def fill_gaps(
        self, now: datetime | None = None, max_gap: timedelta = GAP_MAX, step: timedelta = GAP_STEP
    ) -> int:
        """Fill the time the server was down or asleep (up to `max_gap`) with simulated history, so
        charts stay continuous on a host that sleeps when idle. Only simulated sensors are touched,
        and existing timestamps are kept. Returns the number of readings inserted."""
        now = now or datetime.now(UTC)
        inserted = 0
        with self.session_factory() as db:
            farm_ids = sorted({s.farm_id for s in SimulatorEngine.simulated_sensors(db)})
            for farm_id in farm_ids:
                sensor_ids = [s.id for s in SimulatorEngine.simulated_sensors(db, farm_id)]
                last = db.scalar(
                    select(func.max(SensorReading.recorded_at)).where(SensorReading.sensor_id.in_(sensor_ids))
                )
                if last is not None and last.tzinfo is None:
                    last = last.replace(tzinfo=UTC)
                start = max(last + step, now - max_gap) if last is not None else now - max_gap
                end = now - step
                if start > end:
                    continue
                inserted += int(self.engine.backfill(db, farm_id, start, end, step)["inserted"])
                self.engine.forget_farm(farm_id)
            db.commit()
        if inserted:
            logger.info("Simulator filled %s readings missed while the server was idle", inserted)
        return inserted

    async def _loop(self) -> None:
        self.running = True
        logger.info("Sensor simulator started (every %ss)", self.interval)
        try:
            try:
                await asyncio.to_thread(self.fill_gaps)
            except Exception:  # never block live readings on the catch-up
                logger.exception("Simulator gap fill failed")
            while True:
                started = time.monotonic()
                try:
                    payloads = await asyncio.to_thread(self.tick_once)
                    self.last_error = None
                    for farm_id, payload in payloads.items():  # published only after commit
                        self.broadcaster.publish(farm_id, READINGS_EVENT, payload)
                except Exception as exc:  # keep the loop alive; report via /system/info
                    self.last_error = type(exc).__name__
                    logger.exception("Simulator tick failed")
                await asyncio.sleep(max(0.5, self.interval - (time.monotonic() - started)))
        finally:
            self.running = False
            logger.info("Sensor simulator stopped")

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="sensor-simulator")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "interval_seconds": self.interval,
            "ticks": self.ticks,
            "last_tick_at": self.last_tick_at,
            "last_tick_readings": self.last_tick_readings,
            "last_error": self.last_error,
        }
