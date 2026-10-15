"""The not-yet-settable catalogue, the tool declarations, the Terraform
markers and the Evidence Matrix must agree.

Same purpose as the evidence-level tests: a gap written only in prose drifts
out of date the first time someone closes it in code and forgets the prose,
or adds a tool without saying what it cannot do. This makes the statement
structural.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

import mcp_server.tools.aci  # noqa: F401
import mcp_server.tools.evpn  # noqa: F401
import mcp_server.tools.generic  # noqa: F401
from mcp_server.not_settable import NOT_SETTABLE
from mcp_server.tools.registry import ToolRegistry, registry

# Repo root when run from a checkout; inside the server container only the
# tests are mounted, so there may be no parent that far up -- the tests that
# need the repo then skip (see _need) rather than fail to import.
_parents = Path(__file__).resolve().parents
REPO = _parents[3] if len(_parents) > 3 else Path("/nonexistent")
MAIN_TF = REPO / "platform" / "terraform" / "aci" / "main.tf"
MATRIX = REPO / "knowledge" / "architecture" / "Evidence-Matrix.md"


def _need(path: Path) -> str:
    if not path.exists():  # e.g. inside the server container, which ships only mcp-server/
        pytest.skip(f"{path} not available here")
    return path.read_text(encoding="utf-8")


def _terraform_marks() -> dict[str, set[str]]:
    tf = _need(MAIN_TF)
    resource = re.compile(r'^resource "(\w+)"', re.M)
    marks: dict[str, set[str]] = {}
    for m in re.finditer(r"# NOT-SETTABLE\[(NS-\d+)\]:", tf):
        marks.setdefault(m.group(1), set()).add(resource.search(tf, m.end()).group(1))
    return marks


def _matrix_rows() -> dict[str, list[str]]:
    text = _need(MATRIX)
    section = text[text.index("## 6. Not yet settable"):]
    rows = {}
    for line in section.splitlines():
        if line.startswith("| NS-"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows[cells[0]] = cells
    return rows


# --- the catalogue itself ------------------------------------------------------

def test_every_gap_is_fully_described():
    for nid, gap in NOT_SETTABLE.items():
        assert re.fullmatch(r"NS-\d{2}", nid), nid
        for field in ("title", "why", "meanwhile", "next"):
            assert getattr(gap, field).strip(), f"{nid}.{field} is empty"


def test_every_gap_is_used_somewhere():
    """An ID nobody declares is either closed (remove it) or forgotten."""
    used = {i for s in registry.catalogue() for i in s.not_settable} | set(_terraform_marks())
    platform_only = {"NS-14"}  # health score policy: no tool and no resource exist to mark
    assert set(NOT_SETTABLE) - used - platform_only == set()


# --- registration and what the agent sees ------------------------------------------

class _S(BaseModel):
    pass


def test_an_unknown_id_is_refused_at_registration():
    with pytest.raises(ValueError, match="unknown not_settable"):
        ToolRegistry().register(name="t", domain="d", description="x", schema=_S, not_settable=("NS-99",))


def test_the_remark_reaches_the_agent_and_only_when_declared():
    with_gap = registry.get("update_epg").client_description()
    assert "[NOT YET SETTABLE" in with_gap
    assert "NS-10" in with_gap and "APIC defaults for each" in with_gap
    assert "NS-01" not in with_gap, "NS-01 closed 2026-10-15 -- the VRF preferred group is settable"
    assert "[NOT YET SETTABLE" not in registry.get("create_tenant").client_description()


def test_the_evidence_caveat_still_reaches_the_agent():
    """client_description() took over main.py's caveat; it must not be lost."""
    spec = next(s for s in registry.catalogue() if s.evidence == "unit-tested")
    assert "[EVIDENCE: unit-tested" in spec.client_description()


# --- the four places agree -----------------------------------------------------------

def test_terraform_markers_name_real_gaps():
    assert set(_terraform_marks()) <= set(NOT_SETTABLE)


def test_the_matrix_lists_exactly_the_catalogue():
    assert set(_matrix_rows()) == set(NOT_SETTABLE)


def test_the_matrix_tool_column_matches_the_declarations():
    rows = _matrix_rows()
    for nid in NOT_SETTABLE:
        declared = {s.name for s in registry.catalogue() if nid in s.not_settable}
        listed = set(re.findall(r"`([a-z0-9_]+)`", rows[nid][2]))
        assert listed == declared, f"{nid}: matrix lists {sorted(listed)}, tools declare {sorted(declared)}"


def test_the_matrix_terraform_column_matches_the_markers():
    rows, marks = _matrix_rows(), _terraform_marks()
    for nid in NOT_SETTABLE:
        listed = set(re.findall(r"`(aci_[a-z0-9_]+)`", rows[nid][3]))
        assert listed == marks.get(nid, set()), f"{nid}: matrix lists {sorted(listed)}, main.tf marks {sorted(marks.get(nid, set()))}"
