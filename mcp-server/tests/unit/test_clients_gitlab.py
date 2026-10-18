"""Parsers behind get_pipeline_report -- no GitLab needed.

The fault-check fixture is the real verify_apic_faults trace of pipeline 60
(job 1003, 2026-10-15), timestamps and stream markers included, because the
parser's whole job is coping with that framing. Its point: terraform_apply
reported 116 resources added and APIC still marked the L4-L7 device invalid.
"""
from __future__ import annotations

from mcp_server.clients.gitlab import clean_trace, parse_fault_check, parse_terraform

_FAULT_TRACE = """\
2026-10-15T11:57:38.414020Z 01E FAIL: this deployment introduced 2 new fault(s) under managed tenant(s) ['sales'] + 9 non-tenant object(s):
2026-10-15T11:57:38.414036Z 01E   [minor (soaking)] F0764  uni/tn-sales/lDevVip-FW/fault-F0764
2026-10-15T11:57:38.414036Z 01E       L4-L7 Devices configuration FW for tenant sales is invalid.
2026-10-15T11:57:38.414041Z 01E   [minor (soaking)] F1690  uni/tn-sales/lDevVip-FW/vnsConfIssue-missing-cdev/fault-F1690
2026-10-15T11:57:38.414041Z 01E       Configuration is invalid due to No device found in cluster.
2026-10-15T11:57:38.414041Z 01E
2026-10-15T11:57:38.414042Z 01E Terraform reported success, so these objects exist -- but APIC considers them invalid and will not deploy them. Treat this as a failed deployment, not a warning.
2026-10-15T11:57:40.840378Z 00O ERROR: Job failed: exit code 1
"""


def test_clean_trace_strips_timestamp_stream_marker_and_colour():
    lines = clean_trace("2026-10-15T11:56:33.092548Z 01O \x1b[32mApply complete!\x1b[0m\n")
    assert lines == ["Apply complete!"]


def test_fault_check_reports_every_new_fault_with_its_description():
    result = parse_fault_check(clean_trace(_FAULT_TRACE))

    assert result["status"] == "new_faults"
    assert [f["code"] for f in result["faults"]] == ["F0764", "F1690"]
    first = result["faults"][0]
    assert first == {
        "severity": "minor",
        "lc": "soaking",
        "code": "F0764",
        "dn": "uni/tn-sales/lDevVip-FW/fault-F0764",
        "descr": "L4-L7 Devices configuration FW for tenant sales is invalid.",
    }


def test_fault_check_clean_run():
    lines = ["OK: no new configuration faults under managed tenant(s) ['sales'] + 9 non-tenant object(s) (12 before, 12 now)"]
    result = parse_fault_check(lines)
    assert result["status"] == "clean"
    assert result["faults"] == []
    assert "['sales']" in result["detail"]


def test_fault_check_unreachable_apic_is_unverifiable_not_clean():
    """The script fails closed when it cannot reach APIC; reading that as
    'clean' would turn an unverified fabric into a verified one."""
    result = parse_fault_check(["FAIL (fail-closed): could not reach APIC at https://172.30.46.103: timed out"])
    assert result["status"] == "unverifiable"
    assert "timed out" in result["detail"]


def test_unrecognised_output_is_never_reported_as_clean():
    assert parse_fault_check(["something the script never printed"])["status"] == "unrecognised"


def test_terraform_plan_and_apply_summaries():
    plan = parse_terraform(["Plan: 3 to add, 1 to change, 2 to destroy."])
    assert plan["plan"] == {"add": 3, "change": 1, "destroy": 2}

    apply = parse_terraform(clean_trace(
        "2026-10-15T11:56:33.092548Z 01O Apply complete! Resources: 116 added, 0 changed, 0 destroyed.\n"
    ))
    assert apply["apply"] == {"added": 116, "changed": 0, "destroyed": 0}


def test_terraform_no_changes_is_a_zero_plan():
    result = parse_terraform(["No changes. Your infrastructure matches the configuration."])
    assert result["plan"] == {"add": 0, "change": 0, "destroy": 0}


def test_terraform_errors_are_collected_but_python_exception_names_are_not():
    result = parse_terraform([
        "│ Error: Creation of rest request failed",
        "urllib.error.URLError: <urlopen error timed out>",
        "Error: Invalid reference",
    ])
    assert result["errors"] == ["Creation of rest request failed", "Invalid reference"]
