"""Broadcaster fan-out, SSE framing and the stream endpoint's access rules."""

import asyncio
import json
import threading
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.realtime.broadcaster import Broadcaster, StreamEvent
from app.realtime.sse import event_stream, format_event
from tests.api.helpers import V1, err, make_farm, ok
from tests.conftest import ClientFor


def test_broadcaster_fans_out_per_farm_and_drops_oldest_for_slow_clients() -> None:
    async def scenario() -> None:
        b = Broadcaster(queue_size=2)
        a1, a2, other = b.subscribe(1), b.subscribe(1), b.subscribe(2)
        assert b.publish(1, "readings", {"n": 1}) == 2
        assert other.empty()
        b.publish(1, "readings", {"n": 2})
        b.publish(1, "readings", {"n": 3})  # a1/a2 full: oldest (n=1) dropped
        assert [a1.get_nowait().data["n"] for _ in range(2)] == [2, 3]
        assert b.dropped == 2
        b.unsubscribe(1, a1)
        b.unsubscribe(1, a2)
        assert b.subscriber_count == 1
        assert b.publish(1, "readings", {}) == 0

    asyncio.run(scenario())


def test_publish_from_worker_thread_reaches_subscribers() -> None:
    async def scenario() -> StreamEvent:
        b = Broadcaster()
        b.bind_loop(asyncio.get_running_loop())
        queue = b.subscribe(7)
        threading.Thread(target=b.publish_threadsafe, args=(7, "readings", {"ok": True})).start()
        return await asyncio.wait_for(queue.get(), timeout=2)

    event = asyncio.run(scenario())
    assert (event.event, event.data) == ("readings", {"ok": True})


def test_sse_framing() -> None:
    assert format_event("readings", {"a": 1}, 5) == 'id: 5\nevent: readings\ndata: {"a":1}\n\n'
    assert format_event(None, "line1\nline2") == 'data: "line1\\nline2"\n\n'  # JSON escapes newlines


def test_event_stream_sends_snapshot_events_heartbeats_and_stops_on_disconnect() -> None:
    async def scenario() -> list[str]:
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        disconnected = {"value": False}

        async def is_disconnected() -> bool:
            return disconnected["value"]

        chunks: list[str] = []
        gen = event_stream(queue, {"farm_id": 1, "sensors": []}, is_disconnected, heartbeat_seconds=0.01)
        chunks.append(await anext(gen))  # retry hint
        chunks.append(await anext(gen))  # snapshot
        chunks.append(await anext(gen))  # idle -> heartbeat
        queue.put_nowait(StreamEvent(9, "readings", {"farm_id": 1, "readings": []}))
        chunks.append(await anext(gen))
        disconnected["value"] = True
        async for chunk in gen:  # generator must finish once the client is gone
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(scenario())
    assert chunks[0] == "retry: 5000\n\n"
    assert chunks[1].startswith("event: snapshot\n")
    assert chunks[2] == ": ping\n\n"
    assert chunks[3].startswith("id: 9\nevent: readings\n")


def test_stream_requires_auth_and_ownership(client_for: ClientFor) -> None:
    owner = client_for("owner@example.com")
    farm = make_farm(owner)
    err(client_for(None).get(f"{V1}/farms/{farm['id']}/stream"), 401, "unauthorized")
    err(client_for("mallory@example.com").get(f"{V1}/farms/{farm['id']}/stream"), 404, "not_found")


def test_http_ingest_publishes_to_the_live_stream_after_commit(api: TestClient) -> None:
    published: list[tuple[int, str, dict[str, Any]]] = []

    class Spy(Broadcaster):
        def publish_threadsafe(self, farm_id: int, event: str, data: dict[str, Any]) -> None:
            published.append((farm_id, event, data))

    api.app.state.broadcaster = Spy()  # type: ignore[attr-defined]
    farm = make_farm(api)
    sensor = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/sensors",
            json={"name": "RH", "sensor_type": "humidity", "source": "hardware"},
        ),
        201,
    )
    when = datetime.now(UTC).replace(microsecond=0).isoformat()
    ok(
        api.post(
            f"{V1}/sensors/{sensor['id']}/readings", json={"readings": [{"recorded_at": when, "value": 61.5}]}
        )
    )
    ok(
        api.post(
            f"{V1}/sensors/{sensor['id']}/readings", json={"readings": [{"recorded_at": when, "value": 61.5}]}
        )
    )

    assert len(published) == 1  # the duplicate inserted nothing, so nothing was announced
    farm_id, event, data = published[0]
    assert (farm_id, event) == (farm["id"], "readings")
    item = data["readings"][0]
    assert item["sensor_id"] == sensor["id"] and item["value"] == 61.5 and item["is_simulated"] is False
    json.dumps(data)  # payload is JSON-serialisable
