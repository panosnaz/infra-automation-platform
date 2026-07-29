"""Generic tools -- domain-agnostic, never import from a domain-specific
tools module (tools/aci.py, future tools/evpn.py, etc.).

Milestone 5 scope (Execution-Framework.md §6): show_status only. deploy/
approve_change/deny_change/query_knowledge are listed in
Platform-v2-Reference-Architecture.md §7.8's catalogue but are future
additions once the create_tenant + show_status gate is met.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from mcp_server.clients.gitlab import GitLabClient
from mcp_server.clients.nautobot import NautobotClient
from mcp_server.tools.registry import registry


class ShowStatusRequest(BaseModel):
    name: str = Field(description="Tenant name to check status for, e.g. 'finance'.")


@registry.register(
    name="show_status",
    domain="generic",
    description=(
        "Merge Nautobot's stored deployment status (validation_status, "
        "last_pipeline_id, last_pipeline_url, last_validated_at -- written "
        "by the pipeline's write_results job) with GitLab's live pipeline "
        "status for the most recent pipeline run. This is the one piece of "
        "genuinely new logic the MCP Server owns (Reference-Architecture.md "
        "§7.7) -- it does not re-implement or duplicate either source."
    ),
    schema=ShowStatusRequest,
)
def show_status(
    request: ShowStatusRequest, *, nautobot: NautobotClient, gitlab: GitLabClient
) -> dict:
    tenant = nautobot.get_tenant_status(request.name)
    if tenant is None:
        return {"found": False, "name": request.name}

    custom_fields = tenant.get("custom_fields") or {}
    nautobot_status = {
        "validation_status": custom_fields.get("validation_status"),
        "last_pipeline_id": custom_fields.get("last_pipeline_id"),
        "last_pipeline_url": custom_fields.get("last_pipeline_url"),
        "last_validated_at": custom_fields.get("last_validated_at"),
    }

    live_pipeline = None
    pipeline_id = custom_fields.get("last_pipeline_id")
    if pipeline_id:
        live_pipeline = gitlab.pipeline(int(pipeline_id))
    if live_pipeline is None:
        # No recorded pipeline yet for this tenant (e.g. webhook still
        # in flight) -- fall back to the most recent pipeline on the
        # project so a caller sees *something* is running.
        live_pipeline = gitlab.latest_pipeline()

    return {
        "found": True,
        "name": request.name,
        "nautobot": nautobot_status,
        "gitlab_live_pipeline": live_pipeline,
    }
