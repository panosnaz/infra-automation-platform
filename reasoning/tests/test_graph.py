"""The LangGraph graph end to end against a fake read-only MCP reader."""
from __future__ import annotations

from fixtures import GENERATED, INTENT, REPORT, STATUS, fresh

from platform_reasoning.diagnose import diagnose
from platform_reasoning.knowledge import Section
from platform_reasoning.mcp_reader import READ_ONLY_TOOLS, ToolCallFailed

_SECTIONS = [Section("knowledge/adr/ADR-020.md", "Evidence", 10, ("Node Cannot Deploy because no switches.",))]


class _Reader:
    """Serves canned payloads; a payload that is an exception is raised."""

    def __init__(self, **payloads):
        self.payloads = {
            "show_status": fresh(STATUS),
            "get_tenant_intent": fresh(INTENT),
            "get_generated_intent": fresh(GENERATED),
            "get_pipeline_report": fresh(REPORT),
            **payloads,
        }
        self.calls: list[str] = []
        self.arguments: dict[str, dict] = {}

    async def call(self, tool, **arguments):
        assert tool in READ_ONLY_TOOLS
        self.calls.append(tool)
        self.arguments[tool] = arguments
        value = self.payloads[tool]
        if isinstance(value, Exception):
            raise value
        return value


async def test_full_run_reads_all_four_layers_and_writes_nothing():
    reader = _Reader()
    state = await diagnose(reader, "sales", "BGP_L3Out", sections=_SECTIONS)

    assert sorted(reader.calls) == sorted(
        ["show_status", "get_tenant_intent", "get_generated_intent", "get_pipeline_report"]
    )
    assert state["diagnosis"]["layers"][-1]["number"] == 4
    assert "0 writes" in state["report"]
    assert "knowledge/adr/ADR-020.md:10" in state["report"]


async def test_the_tenants_recorded_pipeline_is_used_when_none_is_given():
    reader = _Reader()
    await diagnose(reader, "sales", sections=_SECTIONS)
    assert reader.arguments["get_pipeline_report"] == {"pipeline_id": 60}
    assert reader.arguments["get_generated_intent"]["pipeline_id"] == 60


async def test_an_explicit_pipeline_overrides_the_recorded_one():
    reader = _Reader()
    await diagnose(reader, "sales", pipeline_id=59, sections=_SECTIONS)
    assert reader.arguments["get_pipeline_report"] == {"pipeline_id": 59}


async def test_an_unknown_tenant_routes_straight_to_analysis():
    reader = _Reader(show_status={"found": False, "name": "ghost"})
    state = await diagnose(reader, "ghost", sections=_SECTIONS)
    assert reader.calls == ["show_status"]
    assert "Stops at layer 1" in state["diagnosis"]["verdict"]


async def test_a_tool_error_is_recorded_and_the_run_still_completes():
    reader = _Reader(get_pipeline_report=ToolCallFailed("get_pipeline_report", "GitLab unreachable"))
    state = await diagnose(reader, "sales", "BGP_L3Out", sections=_SECTIONS)
    assert state["errors"] == {"report": "GitLab unreachable"}
    assert "pipeline report could not be read" in state["diagnosis"]["verdict"]
    assert "GitLab unreachable" in state["report"]


async def test_a_transient_failure_is_retried():
    class _Flaky(_Reader):
        failures = 1

        async def call(self, tool, **arguments):
            if tool == "get_tenant_intent" and self.failures:
                self.failures -= 1
                raise ConnectionError("APIC proxy dropped the connection")
            return await super().call(tool, **arguments)

    reader = _Flaky()
    state = await diagnose(reader, "sales", "BGP_L3Out", sections=_SECTIONS)
    assert state["diagnosis"]["layers"][0]["state"] == "ok"
