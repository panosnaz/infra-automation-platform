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

import check_apic_faults  # noqa: E402
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


# ---------------------------------------------------------------------------
# Non-tenant scope (2026-09-15).
#
# The original scoping anchored only on `tn-<name>/`. The PBR lab apply raised
# 7 faults on VMM-domain and VLAN-pool objects -- which live outside any
# tenant -- and the check reported none of them. They were all `cleared` that
# time, so nothing was actually missed, but a real fault on a domain, pool,
# AEP or leaf profile would have passed silently.
# ---------------------------------------------------------------------------

_NAC_WITH_GLOBAL_OBJECTS = """
apic:
  tenants:
    - name: sales
  fabric_policies:
    vlan_pools:
      - name: vCenter_VMM_Pool
    vmm_domains:
      - name: vCenter_VMM
  access_policies:
    physical_domains:
      - name: Sales_PhyDom
    aeps:
      - name: HOST_AAEP
    leaf_profiles:
      - name: Leaf101_SwProf
"""


@pytest.fixture
def nac_with_global_objects(tmp_path):
    path = tmp_path / "tenants.yaml"
    path.write_text(_NAC_WITH_GLOBAL_OBJECTS, encoding="utf-8")
    return str(path)


def test_managed_global_objects_lists_every_non_tenant_object(nac_with_global_objects):
    fragments = check_apic_faults.managed_global_objects(nac_with_global_objects)

    assert set(fragments) == {
        "vlanns-[vCenter_VMM_Pool]",
        "dom-vCenter_VMM/",
        "phys-Sales_PhyDom",
        "attentp-HOST_AAEP",
        "nprof-Leaf101_SwProf",
    }


def test_managed_global_objects_is_empty_when_none_are_declared(tmp_path):
    path = tmp_path / "tenants.yaml"
    path.write_text("apic:\n  tenants:\n    - name: sales\n", encoding="utf-8")

    assert check_apic_faults.managed_global_objects(str(path)) == []


@pytest.mark.parametrize(
    "fault_dn",
    [
        "uni/vmmp-VMware/dom-vCenter_VMM/rsdefaultCdpIfPol/fault-F1068",
        "uni/infra/vlanns-[vCenter_VMM_Pool]-dynamic/fault-F0721",
        "uni/phys-Sales_PhyDom/fault-F0123",
        "uni/infra/attentp-HOST_AAEP/fault-F0123",
        "uni/infra/nprof-Leaf101_SwProf/fault-F0123",
    ],
)
def test_faults_on_our_non_tenant_objects_are_now_claimed(fault_dn, nac_with_global_objects):
    """These are the exact DN shapes the 2026-09-15 apply produced and the
    check silently ignored."""
    global_objects = check_apic_faults.managed_global_objects(nac_with_global_objects)

    assert check_apic_faults.is_managed(fault_dn, ["sales"], global_objects)


@pytest.mark.parametrize(
    "fault_dn",
    [
        "uni/vmmp-VMware/dom-someone-elses-vcenter/fault-F1068",
        "uni/infra/vlanns-[Unrelated_Pool]-static/fault-F0721",
        "uni/phys-Not_Ours/fault-F0123",
        "topology/pod-1/node-1/sys/cphys-[eth1/2]/fault-F0103",
        "licensecont/manager/fault-F3057",
    ],
)
def test_faults_on_objects_we_did_not_declare_are_still_ignored(fault_dn, nac_with_global_objects):
    """Widening the scope must not turn unrelated fabric noise into a failure
    -- the APIC/licensing/interface faults in this lab's 13-fault baseline
    would fail every single pipeline run."""
    global_objects = check_apic_faults.managed_global_objects(nac_with_global_objects)

    assert not check_apic_faults.is_managed(fault_dn, ["sales"], global_objects)


def test_new_managed_faults_catches_a_non_tenant_fault(nac_with_global_objects):
    global_objects = check_apic_faults.managed_global_objects(nac_with_global_objects)
    before = {}
    after = {
        "uni/vmmp-VMware/dom-vCenter_VMM/rsdefaultCdpIfPol/fault-F1068": {
            "code": "F1068", "severity": "major", "descr": "Failed to form relation",
        },
        "licensecont/manager/fault-F3057": {
            "code": "F3057", "severity": "major", "descr": "unrelated fabric noise",
        },
    }

    introduced = check_apic_faults.new_managed_faults(before, after, ["sales"], global_objects)

    assert list(introduced) == ["uni/vmmp-VMware/dom-vCenter_VMM/rsdefaultCdpIfPol/fault-F1068"]


def test_is_managed_without_global_objects_still_works():
    """Backwards compatibility: the parameter is optional, so existing callers
    that pass only tenants behave exactly as before."""
    assert check_apic_faults.is_managed("uni/tn-sales/lDevVip-FW/fault-F0764", ["sales"])
    assert not check_apic_faults.is_managed("uni/vmmp-VMware/dom-vCenter_VMM/fault-F1068", ["sales"])


@pytest.mark.parametrize("lc", ["soaking-clearing", "raised-clearing", "retaining"])
def test_a_fault_already_clearing_is_not_a_failure(lc):
    """Measured 2026-10-12: Terraform creates a VLAN pool before its range, so
    APIC raises F0721 "missing Encapsulation Blocks" for that instant, then
    clears it. The compare ran while it was still minor/soaking-clearing and
    failed a clean apply. Its lifecycle says the condition is already gone."""
    after = {"uni/infra/vlanns-[p]-static/fault-F0721": {**_fault(code="F0721"), "lc": lc}}
    assert new_managed_faults({}, after, ["sales"], ["vlanns-[p]-"]) == {}


@pytest.mark.parametrize("lc", ["soaking", "raised", None])
def test_a_fault_not_yet_clearing_still_fails(lc):
    """`soaking` is a NEW fault that has not cleared -- it may well be real,
    so it still counts. A snapshot from before the lifecycle was recorded
    (no `lc`) keeps the old behaviour."""
    fault = _fault(code="F0721")
    if lc is not None:
        fault["lc"] = lc
    after = {"uni/infra/vlanns-[p]-static/fault-F0721": fault}
    assert new_managed_faults({}, after, ["sales"], ["vlanns-[p]-"])


def test_fabric_singletons_are_claimed_only_when_declared(tmp_path):
    """2026-10-13: a fabric-policy apply was compared against "[] tenants + 0
    objects" -- an OK that looked at nothing."""
    from check_apic_faults import managed_global_objects

    nac = tmp_path / "t.yaml"
    nac.write_text("apic:\n  fabric_policies:\n    ntp: {admin_state: enabled}\n    isis: {mtu: 1492}\n")
    frags = managed_global_objects(str(nac))
    assert "uni/fabric/time-default" in frags and "uni/fabric/isisDomP-default" in frags
    assert "uni/fabric/snmppol-default" not in frags, "undeclared singletons are not ours"


def test_pc_vpc_and_management_objects_are_claimed(tmp_path):
    from check_apic_faults import managed_global_objects

    nac = tmp_path / "t.yaml"
    nac.write_text(
        "apic:\n"
        "  access_policies:\n"
        "    lacp_policies: [{name: L}]\n    vpc_domains: [{name: V}]\n    pc_vpc_policy_groups: [{name: G}]\n"
        "  node_management:\n"
        "    inband_epgs: [{name: I}]\n"
        "    static_addresses: [{node_id: 901, pod_id: 1, type: out_of_band, address: 10.0.0.1/24}]\n"
    )
    frags = managed_global_objects(str(nac))
    for f in ("lacplagp-L", "expgep-V", "accbundle-G", "inb-I", "StNode-[topology/pod-1/node-901]"):
        assert f in frags
    assert is_managed("uni/tn-mgmt/mgmtp-default/oob-default/rsooBStNode-[topology/pod-1/node-901]/fault-F1", [], frags)


def test_route_reflector_and_pod_profile_faults_are_claimed(tmp_path):
    """2026-10-14: the APIC accepts a route-reflector node that is not a
    registered spine with HTTP 200, then raises F1893 under the BGP policy.
    The compare has to own that DN, or the fault goes unreported."""
    from check_apic_faults import managed_global_objects

    nac = tmp_path / "t.yaml"
    nac.write_text(
        "apic:\n  fabric_policies:\n"
        "    bgp_route_reflector: {asn: 65099, nodes: [{node_id: 1901, pod_id: 1}]}\n"
        "    pod_profile: {policy_group: pg1}\n"
    )
    frags = managed_global_objects(str(nac))
    fault_dn = "uni/fabric/bgpInstP-default/rr/node-1901/badselection/fault-F1893"
    after = {fault_dn: _fault(code="F1893", descr="Only spine nodes can be BGP Route-Reflectors.")}
    assert new_managed_faults({}, after, [], frags)
    assert "uni/fabric/podprof-default" in frags
