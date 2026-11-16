"""Background loop that evaluates automatic alert rules for every farm (Phase 17)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Farm
from app.realtime.broadcaster import Broadcaster
from app.services import alerting

logger = logging.getLogger("agri_sense.alerts")


class AlertRunner:
    def __init__(
        self, session_factory: Callable[[], Session], broadcaster: Broadcaster, interval_seconds: float
    ) -> None:
        self.session_factory = session_factory
        self.broadcaster = broadcaster
        self.interval = interval_seconds
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.runs = 0
        self._task: asyncio.Task[None] | None = None

    def run_once(self) -> list[tuple[int, list[dict[str, object]]]]:
        """Evaluate every farm, each in its own transaction (one failing farm does not block others)."""
        published = []
        with self.session_factory() as db:
            farm_ids = [f.id for f in alerting.farms_to_evaluate(db)]
        for farm_id in farm_ids:
            with self.session_factory() as db:
                try:
                    farm = db.get(Farm, farm_id)
                    if farm is None:
                        continue
                    result = alerting.evaluate_farm(db, farm)
                    db.commit()
                    published.append((farm_id, result["events"]))
                except Exception:
                    db.rollback()
                    logger.exception("Alert evaluation failed for farm %s", farm_id)
        self.runs += 1
        self.last_run_at = datetime.now(UTC)
        return published

    async def _loop(self) -> None:
        logger.info("Alert evaluator started (every %ss)", self.interval)
        while True:
            started = time.monotonic()
            try:
                for farm_id, events in await asyncio.to_thread(self.run_once):
                    for e in events:  # published only after commit
                        self.broadcaster.publish(farm_id, alerting.ALERT_EVENT, e)
                self.last_error = None
            except Exception as exc:
                self.last_error = type(exc).__name__
                logger.exception("Alert evaluation loop failed")
            await asyncio.sleep(max(5.0, self.interval - (time.monotonic() - started)))

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="alert-evaluator")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
