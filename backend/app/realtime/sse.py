"""Server-Sent Events formatting and the per-connection event generator."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.realtime.broadcaster import StreamEvent

RETRY_MS = 5_000


def format_event(event: str | None, data: Any, event_id: int | None = None) -> str:
    """One SSE message. Multi-line JSON is never produced (compact separators), but any
    newline in the payload is still split into separate `data:` lines per the spec."""
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    payload = json.dumps(data, separators=(",", ":"), default=str)
    lines.extend(f"data: {line}" for line in payload.split("\n"))
    return "\n".join(lines) + "\n\n"


async def event_stream(
    queue: asyncio.Queue[StreamEvent],
    snapshot: dict[str, Any],
    is_disconnected: Callable[[], Awaitable[bool]],
    *,
    heartbeat_seconds: float = 10.0,
    max_events: int | None = None,
) -> AsyncIterator[str]:
    """Yield: reconnect hint, a snapshot of current values, then live events and heartbeats."""
    yield f"retry: {RETRY_MS}\n\n"
    yield format_event("snapshot", snapshot)
    sent = 0
    while max_events is None or sent < max_events:
        if await is_disconnected():
            break
        try:
            message = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
        except TimeoutError:
            yield ": ping\n\n"  # keeps proxies from closing an idle connection
            continue
        yield format_event(message.event, message.data, message.id)
        sent += 1
