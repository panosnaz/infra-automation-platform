"""MCP client restricted to read-only tools.

The restriction is enforced here, before any request leaves the process, so a
diagnosis cannot change platform state even if a node is written wrongly or a
future LLM node proposes a write. ADR-022 forbids this workflow from writing;
this allowlist is what makes that structural rather than a convention.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "show_status",
    "list_aci_tenants",
    "get_tenant_intent",
    "get_fabric_intent",
    "get_generated_intent",
    "get_pipeline_report",
    "get_plan_changes",
})

# The diagnosis cannot run without these; checked once at connect time.
REQUIRED_TOOLS: frozenset[str] = frozenset({
    "show_status", "get_tenant_intent", "get_generated_intent", "get_pipeline_report",
})


class WriteToolRefused(RuntimeError):
    """A tool outside READ_ONLY_TOOLS was requested."""


class ToolCallFailed(RuntimeError):
    """The MCP Server returned a tool error (backend refused or was unreachable)."""

    def __init__(self, tool: str, message: str) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool = tool
        self.message = message


class McpReader:
    """Calls read-only MCP tools and returns their JSON payload as a dict."""

    def __init__(self, session: Any) -> None:
        self._session = session
        self.calls: list[str] = []

    async def call(self, tool: str, **arguments: Any) -> dict:
        if tool not in READ_ONLY_TOOLS:
            raise WriteToolRefused(f"'{tool}' is not a read-only tool; this workflow never writes")
        self.calls.append(tool)
        result = await self._session.call_tool(tool, {k: v for k, v in arguments.items() if v is not None})
        if getattr(result, "is_error", False):
            raise ToolCallFailed(tool, _text(result) or "tool reported an error")
        return _payload(result)


def _text(result: Any) -> str:
    return "\n".join(getattr(c, "text", "") for c in getattr(result, "content", None) or []).strip()


def _payload(result: Any) -> dict:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        # The SDK wraps a non-object return value as {"result": ...}.
        if set(structured) == {"result"} and isinstance(structured["result"], dict):
            return structured["result"]
        return structured
    text = _text(result)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolCallFailed("?", f"tool returned non-JSON content: {text[:200]}") from exc
    return value if isinstance(value, dict) else {"result": value}


@asynccontextmanager
async def connect(url: str, required: frozenset[str] = REQUIRED_TOOLS) -> AsyncIterator[McpReader]:
    """`required`: the tools the calling workflow cannot run without."""
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            missing = required - {t.name for t in listed.tools}
            if missing:
                raise ToolCallFailed(
                    "list_tools",
                    f"MCP Server at {url} lacks {sorted(missing)}; rebuild docker/mcp-server",
                )
            yield McpReader(session)
