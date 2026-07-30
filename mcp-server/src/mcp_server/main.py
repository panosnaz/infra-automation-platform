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

    def _tool_impl(**kwargs):  # noqa: ANN001, ANN202
        try:
            request = spec.schema(**kwargs)
        except PydanticValidationError as exc:
            raise MCPServerError(f"Invalid input for '{spec.name}': {exc}") from exc
        try:
            return spec.handler(request, **deps)
        except MCPServerError:
            raise
        except Exception as exc:  # noqa: BLE001 - never leak raw stack traces (Ref-Arch §7.5)
            logger.exception("Tool '%s' failed", spec.name)
            raise MCPServerError(f"'{spec.name}' failed: {exc}") from exc

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
    params = [
        inspect.Parameter(
            field_name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=field_info.annotation,
            default=inspect.Parameter.empty if field_info.is_required() else field_info.default,
        )
        for field_name, field_info in spec.schema.model_fields.items()
    ]
    _tool_impl.__signature__ = inspect.Signature(params)

    server.tool(name=spec.name, description=spec.description)(_tool_impl)


def main() -> None:
    server, settings = build_server()
    if settings.mcp_transport == "streamable-http":
        server.run(transport="streamable-http", host=settings.mcp_host, port=settings.mcp_port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
