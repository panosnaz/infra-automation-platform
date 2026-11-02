"""The MCP endpoint refuses a caller without the key, once a key is set.

MCP_API_KEY sat in config.py and the compose file from Milestone 5 with nothing
reading it, so setting it protected nothing: any process that could reach port
8071 could call every tool, deletes included (found 2026-10-17, ADR-022).
"""
from __future__ import annotations

import asyncio

from mcp_server.auth import ApiKeyMiddleware


class _App:
    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True


def _call(path="/mcp", headers=(), scope_type="http", key="s3cret"):
    app, sent = _App(), []

    async def send(message):
        sent.append(message)

    scope = {"type": scope_type, "path": path, "headers": list(headers)}
    asyncio.run(ApiKeyMiddleware(app, key)(scope, None, send))
    return app.called, sent


def test_the_right_key_reaches_the_server():
    called, sent = _call(headers=[(b"authorization", b"Bearer s3cret")])
    assert called and sent == []


def test_no_key_is_refused_and_the_server_never_runs():
    called, sent = _call()
    assert not called
    assert sent[0]["status"] == 401
    assert (b"www-authenticate", b"Bearer") in sent[0]["headers"]


def test_a_wrong_key_is_refused():
    assert not _call(headers=[(b"authorization", b"Bearer nope")])[0]


def test_the_key_without_the_bearer_scheme_is_refused():
    assert not _call(headers=[(b"authorization", b"s3cret")])[0]


def test_a_refusal_does_not_echo_the_key():
    _, sent = _call(headers=[(b"authorization", b"Bearer nope")])
    assert b"s3cret" not in b"".join(m.get("body", b"") for m in sent)


def test_health_stays_open_for_the_container_healthcheck():
    assert _call(path="/health")[0]


def test_startup_events_are_not_blocked():
    """Lifespan carries no headers; refusing it would stop the server starting."""
    assert _call(path="", scope_type="lifespan")[0]
