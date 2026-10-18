"""Workflow 2 (ADR-022): read-only deployment diagnosis as a LangGraph graph.

    read_status ──(tenant unknown)──────────────────────────────┐
         │                                                       │
    read_intent ──(no intent)──────────────────────────────────┤
         │ fan-out                                               │
    read_generated   read_report                                 │
         └──────┬────────┘                                       ▼
             analyse ── retrieve_knowledge ── render ──► END

Every read goes through McpReader, which refuses any non-read-only tool. No
node holds credentials and no node writes.
"""
from __future__ import annotations

import operator
from dataclasses import asdict
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from platform_reasoning import analysis, knowledge, report
from platform_reasoning.mcp_reader import ToolCallFailed, WriteToolRefused


class DiagnosisState(TypedDict, total=False):
    tenant: str
    object_name: str | None
    pipeline_id: int | None
    environment: str
    status: dict | None
    intent: dict | None
    generated: dict | None
    pipeline_report: dict | None
    errors: Annotated[dict[str, str], operator.or_]
    diagnosis: dict
    knowledge: dict[str, list[dict]]
    report: str


def _transient(exc: Exception) -> bool:
    # A refused write or a tool-level error is deterministic; retrying cannot help.
    return not isinstance(exc, (ToolCallFailed, WriteToolRefused))


_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, retry_on=_transient)


def build_graph(reader: Any, sections: list[knowledge.Section]):
    async def read_status(state: DiagnosisState) -> dict:
        try:
            status = await reader.call("show_status", name=state["tenant"])
        except ToolCallFailed as exc:
            return {"status": None, "errors": {"status": exc.message}}
        recorded = ((status.get("nautobot") or {}).get("last_pipeline_id")) if status.get("found") else None
        return {"status": status, "pipeline_id": state.get("pipeline_id") or recorded}

    async def read_intent(state: DiagnosisState) -> dict:
        try:
            return {"intent": await reader.call("get_tenant_intent", tenant=state["tenant"])}
        except ToolCallFailed as exc:
            return {"intent": None, "errors": {"intent": exc.message}}

    async def read_generated(state: DiagnosisState) -> dict:
        try:
            generated = await reader.call(
                "get_generated_intent", tenant=state["tenant"], pipeline_id=state.get("pipeline_id")
            )
        except ToolCallFailed as exc:
            return {"generated": None, "errors": {"generated": exc.message}}
        return {"generated": generated}

    async def read_report(state: DiagnosisState) -> dict:
        try:
            result = await reader.call("get_pipeline_report", pipeline_id=state.get("pipeline_id"))
        except ToolCallFailed as exc:
            return {"pipeline_report": None, "errors": {"report": exc.message}}
        return {"pipeline_report": result}

    def analyse(state: DiagnosisState) -> dict:
        diagnosis = analysis.analyse(
            tenant=state["tenant"],
            object_name=state.get("object_name"),
            intent=state.get("intent"),
            generated=state.get("generated"),
            report=state.get("pipeline_report"),
            errors=state.get("errors") or {},
            environment=state.get("environment") or "production",
        )
        return {"diagnosis": asdict(diagnosis)}

    def retrieve_knowledge(state: DiagnosisState) -> dict:
        d = state["diagnosis"]
        if d.get("object_name"):
            families = analysis.classify_faults(d.get("object_faults") or [])
        else:
            families = {**(d.get("shared_fault_families") or {}), **(d.get("fault_families") or {})}
        found: dict[str, list[dict]] = {}
        for name in families:
            fam = analysis.family(name)
            terms = list(fam.kb_terms) if fam else sorted({f["code"] for f in families[name]})
            found[name] = knowledge.search(sections, terms, limit=2)
        return {"knowledge": found}

    def render(state: DiagnosisState) -> dict:
        return {"report": report.render(state, reads=list(reader.calls))}

    def after_status(state: DiagnosisState) -> str:
        status = state.get("status")
        return "read_intent" if status is not None and status.get("found") else "analyse"

    def after_intent(state: DiagnosisState) -> list[str] | str:
        return ["read_generated", "read_report"] if state.get("intent") else "analyse"

    graph = StateGraph(DiagnosisState)
    for name, node in (
        ("read_status", read_status),
        ("read_intent", read_intent),
        ("read_generated", read_generated),
        ("read_report", read_report),
    ):
        graph.add_node(name, node, retry_policy=_RETRY)
    graph.add_node("analyse", analyse)
    graph.add_node("retrieve_knowledge", retrieve_knowledge)
    graph.add_node("render", render)

    graph.add_edge(START, "read_status")
    graph.add_conditional_edges("read_status", after_status, ["read_intent", "analyse"])
    graph.add_conditional_edges("read_intent", after_intent, ["read_generated", "read_report", "analyse"])
    graph.add_edge(["read_generated", "read_report"], "analyse")
    graph.add_edge("analyse", "retrieve_knowledge")
    graph.add_edge("retrieve_knowledge", "render")
    graph.add_edge("render", END)
    return graph.compile()


async def diagnose(
    reader: Any,
    tenant: str,
    object_name: str | None = None,
    pipeline_id: int | None = None,
    sections: list[knowledge.Section] | None = None,
    environment: str = "production",
) -> DiagnosisState:
    graph = build_graph(reader, sections if sections is not None else knowledge.load_sections())
    return await graph.ainvoke(
        {"tenant": tenant, "object_name": object_name, "pipeline_id": pipeline_id,
         "environment": environment, "errors": {}}
    )
