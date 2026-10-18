"""Workflow `review-plan` (ADR-022 roadmap 2): summarise a pending Terraform
plan in plain words before a human approves it. Read-only.

    read_plan (get_plan_changes) ──► summarise ──► END

What the approver must be told, in this order: what the plan creates /
changes / DELETES / REPLACES, by object type and name; the module's own
caveats on what changes (EVIDENCE notes, NOT-SETTABLE gaps); drift Terraform
noticed; and whether the parsed list adds up to Terraform's own Plan line.
Deterministic -- no LLM -- and it approves nothing (ADR-022 Decision 6).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from platform_reasoning.mcp_reader import ToolCallFailed, WriteToolRefused

REQUIRED_TOOLS: frozenset[str] = frozenset({"get_plan_changes"})
ACTIONS = ("create", "update", "delete", "replace")
_MAX_KEYS = 6

# Plain names for the resource types an approver meets most; anything else
# falls back to the type without its "aci_" prefix.
FRIENDLY: dict[str, str] = {
    "aci_tenant": "tenant", "aci_vrf": "VRF", "aci_bridge_domain": "bridge domain", "aci_subnet": "BD subnet",
    "aci_application_profile": "application profile", "aci_application_epg": "EPG",
    "aci_epg_to_contract": "EPG contract binding", "aci_contract": "contract", "aci_contract_subject": "contract subject",
    "aci_filter": "filter", "aci_filter_entry": "filter entry", "aci_l3_outside": "L3Out",
    "aci_external_network_instance_profile": "external EPG", "aci_l3_ext_subnet": "external EPG subnet",
    "aci_logical_node_profile": "L3Out node profile", "aci_logical_interface_profile": "L3Out interface profile",
    "aci_l3out_path_attachment": "L3Out interface", "aci_bgp_peer_connectivity_profile": "BGP peer",
    "aci_l3out_static_route": "static route", "aci_endpoint_security_group": "ESG", "aci_any": "vzAny",
    "aci_vlan_pool": "VLAN pool", "aci_physical_domain": "physical domain", "aci_vmm_domain": "VMM domain",
    "aci_attachable_access_entity_profile": "AEP", "aci_rest_managed": "APIC object (REST)",
    "aci_destination_of_redirected_traffic": "PBR destination", "aci_service_redirect_policy": "PBR policy",
    "aci_epg_to_static_path": "EPG static path", "aci_ranges": "VLAN range",
    "aci_l4_l7_logical_interface": "L4-L7 logical interface", "aci_match_route_destination_rule": "route-map prefix rule",
    "aci_match_rule": "route-map match rule", "aci_route_control_profile": "route map",
    "aci_route_control_context": "route-map entry", "aci_logical_node_to_fabric_node": "L3Out node",
}


def friendly(resource_type: str) -> str:
    return FRIENDLY.get(resource_type, resource_type.removeprefix("aci_").replace("_", " "))


def _plural(n: int, name: str) -> str:
    """'8 filter entries', '2 PBR destinations' -- only the last word changes."""
    if n == 1:
        return f"{n} {name}"
    head, _, last = name.rpartition(" ")
    if last.endswith("s") or last.endswith(")"):
        plural = last
    elif last.endswith("y") and last[-2:-1].lower() not in "aeiou":
        plural = last[:-1] + "ies"
    else:
        plural = last + "s"
    return f"{n} {head + ' ' if head else ''}{plural}"


@dataclass
class PlanSummary:
    pipeline: dict
    awaiting_approval: bool
    risk: str  # "low", "review deletions", "incomplete", "no plan"
    headline: str
    lines: dict[str, list[str]] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    check: str = ""


def summarise(payload: dict) -> PlanSummary:
    pipeline = payload.get("pipeline") or {}
    awaiting = bool(payload.get("awaiting_approval"))
    if not payload.get("found"):
        return PlanSummary(pipeline, False, "no plan", payload.get("reason", "no pipeline found"))
    if payload.get("reason"):
        return PlanSummary(pipeline, awaiting, "no plan", payload["reason"])

    changes = payload.get("changes") or []
    grouped: dict[str, dict[str, list[str]]] = {a: defaultdict(list) for a in ACTIONS}
    for change in changes:
        if change["action"] in grouped:
            grouped[change["action"]][change["type"]].append(change["key"] or change["address"])
    lines = {}
    for action in ACTIONS:
        out = []
        for rtype, keys in sorted(grouped[action].items(), key=lambda kv: (-len(kv[1]), kv[0])):
            shown = ", ".join(keys[:_MAX_KEYS]) + (f" (+{len(keys) - _MAX_KEYS} more)" if len(keys) > _MAX_KEYS else "")
            out.append(f"{_plural(len(keys), friendly(rtype))}: {shown}")
        lines[action] = out
    n = {a: sum(len(v) for v in grouped[a].values()) for a in ACTIONS}

    summary, counted = payload.get("summary"), payload.get("counted")
    check = (f"The list adds up to Terraform's own Plan line ({summary['add']} to add, {summary['change']} to change, "
             f"{summary['destroy']} to destroy)." if payload.get("consistent") and summary else "")

    if not payload.get("consistent"):
        headline = (f"WARNING: the parsed list does not add up to Terraform's own Plan line (plan {summary}, "
                    f"parsed {counted}) -- read the job log before approving.")
        risk = "incomplete"
    elif not changes:
        headline, risk = "No changes: approving would apply nothing.", "low"
    else:
        parts = [f"Creates {n['create']}", f"changes {n['update']}",
                 f"{'DELETES' if n['delete'] else 'deletes'} {n['delete']}"]
        if n["replace"]:
            parts.append(f"REPLACES {n['replace']}")
        headline = ", ".join(parts) + "."
        if n["delete"] or n["replace"]:
            headline += " Review each deletion and replacement below before approving."
            risk = "review deletions"
        else:
            headline += " Nothing is deleted or replaced."
            risk = "low"

    # An outdated plan outranks everything else: GitLab's cancel does not
    # cancel a waiting manual job, so an older pipeline stays approvable.
    if payload.get("superseded_by"):
        headline = (f"OUTDATED: pipeline {payload['superseded_by']} planned this branch after this one -- "
                    f"approving this would apply an outdated plan. Review pipeline {payload['superseded_by']} instead. "
                    f"(This plan: {headline})")
        risk = "outdated"

    caveats = []
    changed_types = {c["resource"]: c["type"] for c in changes}
    for resource, marks in sorted((payload.get("markers") or {}).items()):
        name = friendly(changed_types.get(resource, resource.split(".")[0]))
        for ns in marks.get("not_settable") or []:
            caveats.append(f"{name}: {ns['id']} not yet settable -- {ns['title']}")
        for note in marks.get("evidence") or []:
            caveats.append(f"{name}: evidence note -- {note[:220]}{'...' if len(note) > 220 else ''}")
    if payload.get("warning"):
        caveats.append(f"WARNING: {payload['warning']}")

    drift = [f"{friendly(d['type'])} {d['key'] or d['address']} {d['kind']} outside Terraform since the last apply"
             for d in payload.get("drift") or []]
    return PlanSummary(pipeline, awaiting, risk, headline, lines, caveats, drift, check)


_LABEL = {"create": "Creates", "update": "Changes", "delete": "DELETES", "replace": "REPLACES (deleted, then re-created)"}


def render(s: PlanSummary, reads: list[str]) -> str:
    p = s.pipeline
    gate = "terraform_apply is WAITING FOR YOUR APPROVAL" if s.awaiting_approval else "terraform_apply is not waiting for approval"
    out = [f"Plan review: pipeline {p.get('id')} (branch {p.get('ref')}, commit {str(p.get('sha', ''))[:8]}) -- {gate}",
           "", s.headline]
    for action in ACTIONS:
        if s.lines.get(action):
            out += ["", f"{_LABEL[action]}:"] + [f"  {line}" for line in s.lines[action]]
    if s.caveats:
        out += ["", "Caveats the module records on what changes:"] + [f"  {c}" for c in s.caveats]
    if s.drift:
        out += ["", "Drift Terraform noticed while refreshing:"] + [f"  {d}" for d in s.drift]
    if s.check:
        out += ["", f"Check: {s.check}"]
    if s.risk not in ("no plan",):
        out += ["", "Before Terraform runs, the apply job takes an APIC configuration backup (apic-backup.json)."]
    out += ["", f"This review approves nothing -- the decision is yours in GitLab: {p.get('web_url', '')}",
            f"Read-only: {len(reads)} MCP call(s) ({', '.join(reads)}), 0 writes."]
    return "\n".join(out)


class ReviewState(TypedDict, total=False):
    pipeline_id: int | None
    plan: dict
    error: str
    report: str


def _transient(exc: Exception) -> bool:
    return not isinstance(exc, (ToolCallFailed, WriteToolRefused))


def build_graph(reader: Any):
    async def read_plan(state: ReviewState) -> dict:
        try:
            return {"plan": await reader.call("get_plan_changes", pipeline_id=state.get("pipeline_id"))}
        except ToolCallFailed as exc:
            return {"plan": {"found": False, "reason": f"get_plan_changes failed: {exc.message}"}, "error": exc.message}

    def summarise_node(state: ReviewState) -> dict:
        return {"report": render(summarise(state["plan"]), reads=list(getattr(reader, "calls", ["get_plan_changes"])))}

    graph = StateGraph(ReviewState)
    graph.add_node("read_plan", read_plan, retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0, retry_on=_transient))
    graph.add_node("summarise", summarise_node)
    graph.add_edge(START, "read_plan")
    graph.add_edge("read_plan", "summarise")
    graph.add_edge("summarise", END)
    return graph.compile()


async def review(reader: Any, pipeline_id: int | None = None) -> ReviewState:
    return await build_graph(reader).ainvoke({"pipeline_id": pipeline_id})
