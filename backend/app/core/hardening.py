"""HTTP hardening (Phase 19): security headers, request-size limit and rate limiting.

Pure ASGI middleware, so streaming responses (server-sent events) are never buffered.

Rate limiting is in-memory and per process: it protects one API instance from abuse and runaway clients.
Behind several instances, put a shared limiter (reverse proxy or Redis) in front; see docs/SECURITY.md.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
# Paths that serve HTML/JS (Swagger UI) and need a looser policy; only present outside production.
DOC_PATHS = ("/docs", "/redoc")
# Endpoints that run models, aggregate lots of data or write files: limited more tightly.
EXPENSIVE = (
    ("POST", "/vision/"),
    ("POST", "/vision/recognitions"),
    ("POST", "/federated/runs"),
    ("POST", "/recommendations/generate"),
    ("POST", "/reports"),
    ("POST", "/alerts/evaluate"),
    ("POST", "/simulator/backfill"),
)
UNLIMITED = ("/health", "/stream")  # liveness probes and the long-lived event stream


class SecurityHeaders:
    def __init__(self, app: App, *, hsts: bool) -> None:
        self.app, self.hsts = app, hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        is_doc = scope["path"].startswith(DOC_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                extra = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                    b"cross-origin-resource-policy": b"same-site",
                }
                if not is_doc:
                    extra[b"content-security-policy"] = API_CSP.encode()
                if self.hsts:
                    extra[b"strict-transport-security"] = b"max-age=63072000; includeSubDomains"
                present = {k.lower() for k, _ in headers}
                headers.extend((k, v) for k, v in extra.items() if k not in present)
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def _json(
    send: Send, status: int, code: str, message: str, extra: list[tuple[bytes, bytes]] | None = None
) -> None:
    body = json.dumps({"error": {"code": code, "message": message, "details": None}}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        *(extra or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class RequestLimits:
    """Reject over-size bodies from their Content-Length before anything is read into memory."""

    def __init__(self, app: App, *, max_body_bytes: int) -> None:
        self.app, self.max = app, max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in ("POST", "PUT", "PATCH"):
            raw = dict(scope["headers"]).get(b"content-length")
            if raw is not None and raw.isdigit() and int(raw) > self.max:
                return await _json(
                    send,
                    413,
                    "payload_too_large",
                    f"Request bodies can be at most {self.max // 1_048_576} MB.",
                )
        await self.app(scope, receive, send)


class RateLimiter:
    """Sliding-window limiter keyed by the caller (a hash of the bearer token, else the client IP)."""

    def __init__(
        self,
        app: App,
        *,
        per_minute: int,
        expensive_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app, self.limit, self.expensive_limit, self.clock = app, per_minute, expensive_per_minute, clock
        self.hits: dict[tuple[str, bool], deque[float]] = defaultdict(deque)
        self.last_sweep = clock()

    def _key(self, scope: Scope) -> str:
        auth = dict(scope["headers"]).get(b"authorization")
        if auth:
            return "t:" + hashlib.sha256(auth).hexdigest()[:16]
        client = scope.get("client")
        return "ip:" + (client[0] if client else "unknown")

    @staticmethod
    def _expensive(scope: Scope) -> bool:
        path = scope["path"]
        return any(scope["method"] == m and frag in path for m, frag in EXPENSIVE)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or scope["path"].endswith(UNLIMITED):
            return await self.app(scope, receive, send)
        now = self.clock()
        expensive = self._expensive(scope)
        limit = self.expensive_limit if expensive else self.limit
        window = self.hits[(self._key(scope), expensive)]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= limit:
            wait = max(1, int(60 - (now - window[0])) + 1)
            return await _json(
                send,
                429,
                "rate_limited",
                f"Too many requests. Try again in {wait} s.",
                [(b"retry-after", str(wait).encode())],
            )
        window.append(now)
        if now - self.last_sweep > 300:  # drop idle callers so the table cannot grow without bound
            self.last_sweep = now
            for k in [k for k, w in self.hits.items() if not w or now - w[-1] >= 60]:
                del self.hits[k]
        await self.app(scope, receive, send)
