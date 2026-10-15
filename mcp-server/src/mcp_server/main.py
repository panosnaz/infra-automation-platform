"""MCP protocol entrypoint.

Registers every tool from mcp_server.tools.registry with the actual MCP
server object, and runs it. Building tool wiring from our own registry
(rather than sprinkling `@mcp.tool()` directly across tools/aci.py /
tools/generic.py) is what keeps Section 7.2's domain-isolation and
catalogue-introspection guarantees enforceable in one place.

SDK note: the installed `mcp` package (2.x) exposes the FastMCP-style
decorator API as `mcp.server.mcpserver.MCPServer` (older docs/examples
referencing `mcp.server.fastmcp.FastMCP` describe an earlier SDK layout --
same shape, different import path in this version).
"""
from __future__ import annotations

import logging
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError as PydanticValidationError

# Side-effect imports: populate the registry before main() builds the
# catalogue. tools/generic.py must never import tools/aci.py or vice versa
# (Reference-Architecture.md §7.2) -- only this module, and only for wiring.
import mcp_server.tools.aci  # noqa: F401
import mcp_server.tools.evpn  # noqa: F401
import mcp_server.tools.generic  # noqa: F401
from mcp_server.clients.gitlab import GitLabClient
from mcp_server.clients.nautobot import NautobotClient
from mcp_server.config import Settings, load_settings
from mcp_server.errors import MCPServerError
from mcp_server.tools.registry import registry

logger = logging.getLogger("mcp_server")


def build_server() -> tuple[MCPServer, Settings]:
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level,
        format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
        stream=sys.stderr,  # stdout is the MCP protocol channel over stdio transport
    )

    nautobot = NautobotClient(settings.nautobot_url, settings.nautobot_token)
    gitlab_client = GitLabClient(
        settings.gitlab_url, settings.gitlab_token, settings.gitlab_project_id
    )

    server = MCPServer(
        name="network-platform-mcp-server",
        version="0.1.0",
        instructions=(
            "Tools for the Network Platform Engineering Platform. Every "
            "tool writes structured objects directly to Nautobot (the "
            "Source of Truth) -- there is no intermediate intent schema "
            "(ADR-018). Deployment is asynchronous: after a create_* call, "
            "use show_status to check on the triggered pipeline."
        ),
    )

    # Dependency injection: each tool handler declares its client
    # dependencies as keyword-only params (nautobot=..., gitlab=...); this
    # loop supplies exactly the ones each handler asks for, by name, so
    # adding a new client later never touches unrelated tools.
    available_clients = {"nautobot": nautobot, "gitlab": gitlab_client}

    for spec in registry.catalogue():
        _register_with_mcp(server, spec, available_clients)

    @server.custom_route("/health", methods=["GET"])
    async def _health(request):  # noqa: ANN001, ANN202
        """Reachable, not necessarily authorized -- same pattern Platform
        v1's /readiness endpoint already proved out (Ref-Arch.md §7.6).
        Checks Nautobot/GitLab reachability; never touches Vault directly
        (Milestone 5 tools don't need domain credentials).
        """
        from starlette.responses import JSONResponse

        checks: dict[str, str] = {}
        try:
            nautobot.ping()
            checks["nautobot"] = "reachable"
        except Exception as exc:  # noqa: BLE001
            checks["nautobot"] = f"unreachable: {exc}"
        try:
            gitlab_client.latest_pipeline()
            checks["gitlab"] = "reachable"
        except Exception as exc:  # noqa: BLE001
            checks["gitlab"] = f"unreachable: {exc}"
        ok = all(v == "reachable" for v in checks.values())
        return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)

    logger.info("MCP server built with %d tool(s): %s", len(registry.catalogue()), [s.name for s in registry.catalogue()])
    return server, settings


def _register_with_mcp(server: MCPServer, spec, available_clients: dict) -> None:
    import inspect

    handler_params = set(inspect.signature(spec.handler).parameters) - {"request"}
    deps = {k: v for k, v in available_clients.items() if k in handler_params}

    # Errors must be raised as the SDK's ToolError to reach the agent. The SDK
    # (2.x) treats ANY other exception as a crash and sends the model only
    # "Error executing tool <name>" -- so until 2026-10-12, every refusal,
    # validation message and "not found (known: ...)" list this server
    # produced was logged here and never shown to the agent. Found when the
    # delete tools' refusals, which name what still references an object,
    # arrived over MCP with no text at all.
    #
    # Anticipated failures (bad input; anything from errors.py, whose messages
    # are written for the caller) pass their message through. A genuine crash
    # still reaches the agent only as its exception type -- no internals, per
    # Ref-Arch §7.5 -- with the traceback in the server log.
    def _tool_impl(**kwargs):  # noqa: ANN001, ANN202
        try:
            request = spec.schema(**kwargs)
        except PydanticValidationError as exc:
            raise ToolError(f"Invalid input for '{spec.name}': {exc}") from exc
        try:
            return spec.handler(request, **deps)
        except MCPServerError as exc:
            raise ToolError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - never leak raw stack traces (Ref-Arch §7.5)
            logger.exception("Tool '%s' failed", spec.name)
            raise ToolError(
                f"'{spec.name}' failed unexpectedly ({type(exc).__name__}); see the MCP server log."
            ) from exc

    _tool_impl.__name__ = f"tool_{spec.name}"

    # The MCP SDK's @server.tool() decorator introspects the wrapped
    # function's *actual* signature (inspect.signature()) to build the
    # tool's advertised input schema -- a bare **kwargs catch-all produces a
    # broken schema (confirmed live: the SDK asked callers for a literal
    # "kwargs" field instead of the real per-tool fields). Building an
    # explicit signature from the Pydantic schema's own fields and attaching
    # it via __signature__ keeps this loop fully generic (works for any
    # future tool's schema, no per-tool wrapper function needed in this
    # file) while still giving the SDK real parameter names/types/defaults.
    # NOTE on the default: a Pydantic field declared with `default_factory`
    # (e.g. `list[dict] = Field(default_factory=list)`) has `.default` set to
    # PydanticUndefined, NOT to the factory's value. Passing that straight
    # through made the SDK advertise the field as REQUIRED, so an AI client
    # that omitted it got "Field required" and the tool was uncallable
    # without it. Eleven fields across nine tools were affected, including
    # create_epg and create_aep -- both of which had been live-verified,
    # because every unit test calls the handler directly and never goes
    # through this generated signature. Found 2026-09-16 by driving a new
    # tool over the real MCP protocol.
    #
    # get_default(call_default_factory=True) resolves the factory.
    # KEYWORD_ONLY, not POSITIONAL_OR_KEYWORD: MCP calls tools by keyword,
    # and keyword-only parameters may mix required and defaulted fields in any
    # order. A positional signature raises "non-default argument follows
    # default argument" -- and stops the server starting -- whenever a schema
    # declares a required field after an optional one, which an inherited
    # optional base field (e.g. `location`) makes unavoidable (2026-10-12).
    params = [
        inspect.Parameter(
            field_name,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=field_info.annotation,
            default=(
                inspect.Parameter.empty
                if field_info.is_required()
                else field_info.get_default(call_default_factory=True)
            ),
        )
        for field_name, field_info in spec.schema.model_fields.items()
    ]
    _tool_impl.__signature__ = inspect.Signature(params)

    # Surface the evidence level -- and anything the tool cannot set yet -- to
    # the AI client that is about to call it, so it can tell the user rather
    # than report confident success. Composed by ToolSpec.client_description()
    # so it is testable without the MCP SDK.
    description = spec.client_description()

    server.tool(name=spec.name, description=description)(_tool_impl)


def main() -> None:
    server, settings = build_server()
    if settings.mcp_transport == "streamable-http":
        server.run(transport="streamable-http", host=settings.mcp_host, port=settings.mcp_port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
