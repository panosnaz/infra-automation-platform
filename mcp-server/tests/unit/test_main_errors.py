"""Error messages must reach the agent.

The MCP SDK (2.x) shows the model only "Error executing tool <name>" for any
exception that is not its own ToolError. main.py raised this project's
MCPServerError, so every refusal and validation message was logged and never
shown -- found 2026-10-12, when the delete tools' refusals (which name what
still references an object) arrived over MCP with no text.

Needs the 2.x SDK, which is installed in the server container; skipped
elsewhere so the suite stays runnable offline.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.mcpserver")

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from pydantic import BaseModel, field_validator  # noqa: E402

from mcp_server.errors import NautobotError  # noqa: E402
from mcp_server.main import _register_with_mcp  # noqa: E402
from mcp_server.tools.registry import ToolSpec  # noqa: E402


class _Req(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _lower(cls, v):
        if v != v.lower():
            raise ValueError("name must be lowercase")
        return v


class _CapturingServer:
    def tool(self, name, description):
        def _wrap(fn):
            self.fn = fn
            return fn
        return _wrap


def _registered(handler):
    server = _CapturingServer()
    spec = ToolSpec(name="t", domain="d", description="x", schema=_Req, handler=handler)
    _register_with_mcp(server, spec, {})
    return server.fn


def test_a_validation_message_reaches_the_caller():
    fn = _registered(lambda request: {})
    with pytest.raises(ToolError, match="name must be lowercase"):
        fn(name="UPPER")


def test_a_refusal_from_the_client_reaches_the_caller():
    def handler(request):
        raise NautobotError("Refusing to delete contract 'web': still referenced -- EPG 'app' provides it")

    with pytest.raises(ToolError, match="EPG 'app' provides it"):
        _registered(handler)(name="ok")


def test_a_crash_shows_only_its_type_not_its_contents():
    def handler(request):
        raise KeyError("internal-detail-that-must-not-leak")

    with pytest.raises(ToolError) as info:
        _registered(handler)(name="ok")
    assert "KeyError" in str(info.value)
    assert "internal-detail" not in str(info.value)
