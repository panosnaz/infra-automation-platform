"""The read-only allowlist and payload decoding -- no MCP Server needed."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from platform_reasoning.mcp_reader import READ_ONLY_TOOLS, auth_headers, McpReader, ToolCallFailed, WriteToolRefused


def test_no_key_sends_no_header(monkeypatch):
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    assert auth_headers() is None


def test_the_key_goes_out_as_a_bearer_header(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "s3cret")
    assert auth_headers() == {"Authorization": "Bearer s3cret"}


class _Session:
    def __init__(self, result):
        self.result = result
        self.sent: list[tuple[str, dict]] = []

    async def call_tool(self, name, arguments):
        self.sent.append((name, arguments))
        return self.result


def _result(structured=None, text=None, is_error=False):
    content = [SimpleNamespace(text=text)] if text is not None else []
    return SimpleNamespace(structured_content=structured, content=content, is_error=is_error)


@pytest.mark.parametrize("tool", ["create_tenant", "delete_tenant", "update_vrf", "bind_epg_contract"])
async def test_a_write_tool_is_refused_before_anything_is_sent(tool):
    session = _Session(_result({"ok": True}))
    with pytest.raises(WriteToolRefused):
        await McpReader(session).call(tool, name="x")
    assert session.sent == []


def test_the_allowlist_contains_no_writing_tool():
    writing = ("create_", "update_", "delete_", "bind_", "unbind_", "set_", "add_", "assign_", "reset_")
    assert not [t for t in READ_ONLY_TOOLS if t.startswith(writing)]


async def test_structured_content_is_returned_and_none_arguments_are_dropped():
    session = _Session(_result({"found": True}))
    assert await McpReader(session).call("get_pipeline_report", pipeline_id=None) == {"found": True}
    assert session.sent == [("get_pipeline_report", {})]


async def test_the_sdk_result_wrapper_is_unwrapped():
    session = _Session(_result({"result": {"found": True}}))
    assert await McpReader(session).call("show_status", name="sales") == {"found": True}


async def test_text_json_content_is_parsed_when_there_is_no_structured_content():
    session = _Session(_result(text=json.dumps({"tenant": "sales"})))
    assert await McpReader(session).call("get_tenant_intent", tenant="sales") == {"tenant": "sales"}


async def test_a_tool_error_raises_with_the_servers_message():
    session = _Session(_result(text="Tenant 'ghost' not found in Nautobot", is_error=True))
    with pytest.raises(ToolCallFailed, match="ghost"):
        await McpReader(session).call("get_tenant_intent", tenant="ghost")
