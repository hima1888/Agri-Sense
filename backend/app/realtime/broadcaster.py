"""In-process fan-out of live events to SSE subscribers, keyed by farm.

Producers (the simulator, the HTTP ingest endpoint, later MQTT) publish after their
database transaction commits; each open stream has a bounded queue. A slow client
loses its oldest events rather than growing memory without limit.

Single-process by design (one API instance). Scaling to several instances needs a
shared channel such as Postgres LISTEN/NOTIFY or Redis; producers would not change.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("agri_sense.realtime")


@dataclass(frozen=True)
class StreamEvent:
    id: int
    event: str
    data: dict[str, Any]


class Broadcaster:
    def __init__(self, queue_size: int = 200) -> None:
        self.queue_size = queue_size
        self._subscribers: dict[int, set[asyncio.Queue[StreamEvent]]] = defaultdict(set)
        self._ids = itertools.count(1)
        self._loop: asyncio.AbstractEventLoop | None = None
        self.dropped = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # -- must be called on the event loop --------------------------------
    def subscribe(self, farm_id: int) -> asyncio.Queue[StreamEvent]:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers[farm_id].add(queue)
        return queue

    def unsubscribe(self, farm_id: int, queue: asyncio.Queue[StreamEvent]) -> None:
        subs = self._subscribers.get(farm_id)
        if subs is not None:
            subs.discard(queue)
            if not subs:
                del self._subscribers[farm_id]

    def publish(self, farm_id: int, event: str, data: dict[str, Any]) -> int:
        """Deliver to every subscriber of the farm. Returns the number of subscribers reached."""
        message = StreamEvent(next(self._ids), event, data)
        subs = list(self._subscribers.get(farm_id, ()))
        for queue in subs:
            if queue.full():
                queue.get_nowait()  # drop the oldest event for this slow consumer
                self.dropped += 1
            queue.put_nowait(message)
        return len(subs)

    # -- safe from worker threads (sync endpoints, simulator DB thread) ---
    def publish_threadsafe(self, farm_id: int, event: str, data: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return  # nobody can be subscribed yet
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self.publish(farm_id, event, data)
        else:
            loop.call_soon_threadsafe(self.publish, farm_id, event, data)

    @property
    def subscriber_count(self) -> int:
        return sum(len(s) for s in self._subscribers.values())

    def farm_subscriber_count(self, farm_id: int) -> int:
        return len(self._subscribers.get(farm_id, ()))
