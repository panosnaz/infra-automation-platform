"""Bearer-key check in front of the MCP endpoint (Ref-Arch 7.3, first boundary).

Plain ASGI with no SDK import, so it is testable offline. One shared key is the
whole model for now: it stops anyone who can merely reach the port. Per-client
keys are what ADR-022's write workflows will need.
"""
from __future__ import annotations

import hmac
import json

# The container healthcheck calls /health with no credentials.
OPEN_PATHS = frozenset({"/health"})


class ApiKeyMiddleware:
    def __init__(self, app, api_key: str) -> None:
        self.app = app
        self._expected = f"Bearer {api_key}".encode()

    async def __call__(self, scope, receive, send) -> None:
        # Only HTTP carries requests here: lifespan must pass or the server
        # never starts, and the server exposes no websocket route.
        if scope["type"] != "http" or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        presented = dict(scope["headers"]).get(b"authorization", b"")
        if hmac.compare_digest(presented, self._expected):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"error": "missing or invalid API key"}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b"Bearer"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
