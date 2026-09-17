"""Unit tests for the Nautobot schema bootstrap -- no live Nautobot needed.

What these guard is the failure mode the script exists to prevent: Nautobot
answers HTTP 200 to a write against an undeclared Custom Field and silently
discards the data. Every MCP tool reports success and nothing persists. The
only defence is declaring the schema first, so the definition of "declared
correctly" has to be exact -- including which object type each field sits on,
because the same field on the wrong type fails in precisely the same silent
way.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform" / "workflows" / "scripts"))

import bootstrap_nautobot  # noqa: E402
from bootstrap_nautobot import CUSTOM_FIELDS, diff_fields  # noqa: E402


def _all_present() -> dict[str, dict]:
    """A Nautobot that already has the complete schema."""
    return {
        spec["key"]: {"type": spec["type"], "content_types": sorted(spec["content_types"])}
        for spec in CUSTOM_FIELDS
    }


def test_a_complete_instance_reports_nothing_to_do():
    missing, mismatched = diff_fields(_all_present())

    assert missing == []
    assert mismatched == []


def test_an_empty_instance_reports_every_field_missing():
    """A fresh Nautobot at a customer site. All of them, not some."""
    missing, mismatched = diff_fields({})

    assert len(missing) == len(CUSTOM_FIELDS)
    assert mismatched == []


def test_a_partially_configured_instance_reports_only_the_gap():
    """The realistic case: someone created a few by hand and stopped."""
    present = _all_present()
    del present["aci_l4l7_services"]
    del present["aci_route_control"]

    missing, mismatched = diff_fields(present)

    assert sorted(s["key"] for s in missing) == ["aci_l4l7_services", "aci_route_control"]
    assert mismatched == []


def test_a_field_on_the_wrong_object_type_is_not_treated_as_present():
    """This is the nastiest variant. The field exists, so a naive
    name-only check passes, and writes still vanish -- the MCP tools write it
    to a Tenant while Nautobot only allows it on a Location."""
    present = _all_present()
    present["aci_fabric_policies"] = {"type": "json", "content_types": ["tenancy.tenant"]}

    missing, mismatched = diff_fields(present)

    assert missing == []
    assert len(mismatched) == 1
    assert "aci_fabric_policies" in mismatched[0]
    assert "dcim.location" in mismatched[0], "the message must say what was expected"


def test_a_field_of_the_wrong_type_is_reported():
    """A JSON field declared as text silently truncates structured intent."""
    present = _all_present()
    present["aci_contracts"] = {"type": "text", "content_types": ["tenancy.tenant"]}

    _, mismatched = diff_fields(present)

    assert len(mismatched) == 1
    assert "aci_contracts" in mismatched[0] and "json" in mismatched[0]


def test_content_type_comparison_ignores_ordering():
    """Nautobot does not guarantee ordering; a different order is not a
    mismatch and must not produce a spurious failure at a customer site."""
    present = _all_present()
    multi = next((s for s in CUSTOM_FIELDS if len(s["content_types"]) > 1), None)
    if multi is None:
        pytest.skip("no multi-content-type field in the schema today")
    present[multi["key"]]["content_types"] = sorted(multi["content_types"], reverse=True)

    _, mismatched = diff_fields(present)

    assert mismatched == []


# ---------------------------------------------------------------------------
# The schema itself. These are assertions about the platform's requirements,
# not about the script -- they fail if someone adds a Custom Field to the code
# without adding it here, which is the drift this file exists to stop.
# ---------------------------------------------------------------------------

def test_every_field_is_declared_completely():
    for spec in CUSTOM_FIELDS:
        assert spec["key"].startswith("aci_"), f"{spec['key']} is not namespaced"
        assert spec["type"] in ("json", "text", "integer", "boolean"), spec["key"]
        assert spec["content_types"], f"{spec['key']} declares no object type"
        assert spec["label"] and spec["description"], f"{spec['key']} is undocumented"


def test_field_names_are_unique():
    keys = [s["key"] for s in CUSTOM_FIELDS]

    assert len(keys) == len(set(keys)), "a duplicate key would create the field twice"


def test_the_schema_matches_what_the_platform_actually_reads():
    """Cross-check against the generator and the MCP client: every aci_*
    Custom Field either side reads or writes must be declared here, or a
    fresh Nautobot silently drops it.
    """
    import re

    root = Path(__file__).resolve().parents[2]
    sources = [
        root / "platform" / "python" / "generator" / "transformer.py",
        root / "mcp-server" / "src" / "mcp_server" / "clients" / "nautobot.py",
    ]
    referenced: set[str] = set()
    for path in sources:
        referenced |= set(re.findall(r'["\'](aci_[a-z0-9_]+)["\']', path.read_text(encoding="utf-8")))

    declared = {s["key"] for s in CUSTOM_FIELDS}
    undeclared = sorted(referenced - declared)

    assert not undeclared, (
        "these aci_* Custom Fields are used by the platform but are NOT in "
        f"CUSTOM_FIELDS, so a fresh Nautobot would silently discard them: {undeclared}"
    )


def test_the_schema_has_no_fields_nothing_uses():
    """The reverse drift: a field declared here but read by nothing is dead
    weight a customer would be asked to create for no reason."""
    import re

    root = Path(__file__).resolve().parents[2]
    sources = [
        root / "platform" / "python" / "generator" / "transformer.py",
        root / "mcp-server" / "src" / "mcp_server" / "clients" / "nautobot.py",
    ]
    referenced: set[str] = set()
    for path in sources:
        referenced |= set(re.findall(r'["\'](aci_[a-z0-9_]+)["\']', path.read_text(encoding="utf-8")))

    unused = sorted({s["key"] for s in CUSTOM_FIELDS} - referenced)

    assert not unused, f"declared but never read or written: {unused}"


def test_module_exposes_a_main_returning_an_exit_code():
    """Matches the convention of every other script in that directory."""
    assert callable(bootstrap_nautobot.main)
