"""Unit tests for the APIC fault-delta check -- no live APIC needed.

The diff logic is pure set arithmetic plus DN scoping, so it is fully
testable offline. What it guards is the gap that let an invalid L4-L7 device
ship on 2026-09-15: `terraform apply` succeeded, every relation reported
`state: formed`, and APIC had the device flagged invalid the whole time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform" / "workflows" / "scripts"))

from check_apic_faults import is_managed, managed_tenants, new_managed_faults  # noqa: E402


def _fault(severity="minor", code="F1690", descr="Configuration is invalid"):
    return {"severity": severity, "code": code, "descr": descr}


def test_a_new_fault_under_a_managed_tenant_fails():
    before = {}
    after = {"uni/tn-sales/lDevVip-fw/fault-F1690": _fault()}

    assert new_managed_faults(before, after, ["sales"])


def test_a_pre_existing_fault_is_not_attributed_to_this_deployment():
    """The whole reason a snapshot exists: this fabric already carries
    unrelated faults (undiscovered nodes, licensing). Blocking on those would
    make the check useless and it would be switched off."""
    fault = {"uni/tn-sales/lDevVip-fw/fault-F1690": _fault()}

    assert new_managed_faults(fault, fault, ["sales"]) == {}


def test_a_new_fault_outside_managed_tenants_is_ignored():
    """A fault raised on fabric infrastructure we did not touch must not fail
    our deployment."""
    after = {"topology/pod-1/node-1/sys/fault-F0104": _fault(severity="critical")}

    assert new_managed_faults({}, after, ["sales"]) == {}


@pytest.mark.parametrize("severity", ["cleared", "info"])
def test_cleared_and_info_faults_are_not_failures(severity):
    after = {"uni/tn-sales/lDevVip-fw/fault-F1690": _fault(severity=severity)}

    assert new_managed_faults({}, after, ["sales"]) == {}


def test_tenant_matching_does_not_prefix_collide():
    """`sales` must not claim a fault belonging to `sales-archive` -- a bare
    substring match would, which is why the check anchors on `tn-<name>/`."""
    assert is_managed("uni/tn-sales/lDevVip-fw/fault-F1690", ["sales"]) is True
    assert is_managed("uni/tn-sales-archive/lDevVip-fw/fault-F1690", ["sales"]) is False


def test_managed_tenants_reads_the_generated_yaml(tmp_path):
    path = tmp_path / "tenants.yaml"
    path.write_text("apic:\n  tenants:\n    - name: sales\n    - name: finance\n", encoding="utf-8")

    assert managed_tenants(str(path)) == ["sales", "finance"]


def test_managed_tenants_tolerates_an_empty_document(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("apic:\n  tenants: []\n", encoding="utf-8")

    assert managed_tenants(str(path)) == []


def test_the_real_regression_this_was_built_for():
    """The exact 2026-09-15 case: an apply that Terraform called successful,
    which left three new faults on the managed tenant."""
    before = {"topology/pod-1/node-1/sys/fault-F0104": _fault(severity="critical")}
    after = dict(before)
    after.update({
        "uni/tn-svc/lDevVip-fw/fault-F1690": _fault(
            descr="Configuration is invalid due to trunked port group option specified for physical device"),
        "uni/tn-svc/lDevVip-fw/fault-F0764": _fault(descr="L4-L7 Devices configuration fw is invalid."),
        "uni/tn-svc/lDevVip-fw/lIf-consumer/fault-F0772": _fault(descr="LIf configuration consumer is invalid."),
    })

    introduced = new_managed_faults(before, after, ["svc"])

    assert len(introduced) == 3
    assert any("trunked port group" in i["descr"] for i in introduced.values())
