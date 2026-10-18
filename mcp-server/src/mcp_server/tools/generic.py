"""Generic tools -- domain-agnostic, never import from a domain-specific
tools module (tools/aci.py, future tools/evpn.py, etc.).

Milestone 5 scope (Execution-Framework.md §6): show_status only. deploy/
approve_change/deny_change/query_knowledge are listed in
Platform-v2-Reference-Architecture.md §7.8's catalogue but are future
additions once the create_tenant + show_status gate is met.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from mcp_server.clients.gitlab import GitLabClient, clean_trace, parse_fault_check, parse_terraform
from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.generic import GetPipelineReportRequest
from mcp_server.tools.registry import registry

_FINISHED = frozenset({"success", "failed", "canceled"})


class ShowStatusRequest(BaseModel):
    name: str = Field(description="Tenant name to check status for, e.g. 'finance'.")


@registry.register(
    name="show_status",
    evidence="live-verified",
    evidence_note="MCP protocol, Milestone 6 gate -- merged Nautobot + live GitLab status",
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


@registry.register(
    name="get_pipeline_report",
    domain="generic",
    description=(
        "Read-only. Report what one GitLab pipeline actually did: every job and its status, "
        "which jobs await manual approval, the Terraform plan and apply summaries "
        "(add / change / destroy counts, errors), and the APIC fault check result -- "
        "including each new fault's code, severity and DN. A green terraform_apply is NOT "
        "evidence the fabric is valid: APIC accepts configuration it then marks invalid, so "
        "read the apic_fault_checks section before reporting success."
    ),
    schema=GetPipelineReportRequest,
    evidence="live-verified",
    evidence_note=(
        "2026-10-17, over the real MCP protocol against the lab GitLab (16/16 checks with "
        "get_generated_intent, each cross-checked by a direct GitLab read with the same "
        "read_api token): pipeline 60's apply 116/0/0 and all 20 job statuses match GitLab; "
        "19/19 faults parsed with DN and description, matching the raw verify_apic_faults log; "
        "pipeline 59's unapproved terraform_apply reported as awaiting approval with its log "
        "not read; no id resolves to the newest pipeline that ran, skipping [skip ci] ones."
    ),
)
def get_pipeline_report(request: GetPipelineReportRequest, *, gitlab: GitLabClient) -> dict:
    if request.pipeline_id is None:
        pipeline = gitlab.latest_run_pipeline()
    else:
        pipeline = gitlab.pipeline(request.pipeline_id)
    if pipeline is None:
        return {"found": False, "pipeline_id": request.pipeline_id}

    jobs = gitlab.pipeline_jobs(pipeline["id"])
    terraform: dict[str, dict] = {}
    fault_checks: dict[str, dict] = {}
    for job in jobs:
        if job["status"] not in _FINISHED:
            continue
        name = job["name"]
        if name.endswith(("terraform_plan", "terraform_apply")):
            summary = parse_terraform(clean_trace(gitlab.job_trace(job["id"])))
            terraform[name] = {"job_id": job["id"], "status": job["status"], **summary}
        elif name.endswith("verify_apic_faults"):
            result = parse_fault_check(clean_trace(gitlab.job_trace(job["id"])))
            # `status` is the parsed verdict; the job's own status is kept separately.
            fault_checks[name] = {"job_id": job["id"], "job_status": job["status"], **result}

    return {
        "found": True,
        "pipeline": pipeline,
        "jobs": [{k: j[k] for k in ("id", "name", "stage", "status")} for j in jobs],
        "awaiting_approval": [j["name"] for j in jobs if j["status"] == "manual"],
        "terraform": terraform,
        "apic_fault_checks": fault_checks,
    }
