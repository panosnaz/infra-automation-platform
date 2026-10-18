"""Cross-layer analysis: each test pins where an object stops travelling."""
from __future__ import annotations

import pytest
from fixtures import GENERATED, INTENT, REPORT, fresh

from platform_reasoning import analysis


def _stop(d):
    return next((layer for layer in d.layers if layer.state == "stop"), None)


def test_object_with_only_switch_absence_faults_stops_at_layer_4():
    d = analysis.analyse("sales", "BGP_L3Out", fresh(INTENT), fresh(GENERATED), fresh(REPORT))
    assert _stop(d).number == 4
    assert [f["code"] for f in d.object_faults] == ["F1298"]
    assert analysis.classify_faults(d.object_faults).keys() == {"switch_absence"}
    assert "stored and not deployed" in d.verdict


def test_l4l7_device_faults_are_attributed_to_the_device_not_the_graph():
    """'FW' must not claim faults on 'FW_SGT' -- a substring match would."""
    d = analysis.analyse("sales", "FW", fresh(INTENT), fresh(GENERATED), fresh(REPORT))
    assert sorted(f["code"] for f in d.object_faults) == ["F0764", "F1690"]
    assert analysis.classify_faults(d.object_faults).keys() == {"l4l7_without_concrete_device"}


def test_object_with_no_fault_reached_apic_cleanly():
    d = analysis.analyse("sales", "Presales_VRF", fresh(INTENT), fresh(GENERATED), fresh(REPORT))
    assert d.layers[-1].state == "warn"
    assert "no fault on it" in d.verdict


def test_unknown_object_stops_at_layer_1_and_suggests_the_close_name():
    d = analysis.analyse("sales", "BGP_L3OUT", fresh(INTENT), fresh(GENERATED), fresh(REPORT))
    assert _stop(d).number == 1
    assert d.suggestions == ["did you mean 'BGP_L3Out'?"]


def test_object_in_nautobot_but_not_generated_stops_at_layer_2():
    generated = fresh(GENERATED)
    generated["intent"]["l3outs"] = []
    d = analysis.analyse("sales", "BGP_L3Out", fresh(INTENT), generated, fresh(REPORT))
    assert _stop(d).number == 2
    assert "did not generate it" in d.verdict


def test_tenant_absent_from_the_generated_file_stops_at_layer_2():
    generated = fresh(GENERATED)
    generated.update(tenant_present=False, intent=None)
    d = analysis.analyse("sales", None, fresh(INTENT), generated, fresh(REPORT))
    assert _stop(d).number == 2


def test_unapproved_apply_stops_at_layer_3_with_a_next_step():
    report = fresh(REPORT)
    report["awaiting_approval"] = ["terraform_apply"]
    del report["terraform"]["terraform_apply"]
    d = analysis.analyse("sales", "BGP_L3Out", fresh(INTENT), fresh(GENERATED), report)
    assert _stop(d).number == 3
    assert "approve terraform_apply" in d.suggestions[0]


def test_failed_apply_stops_at_layer_3_with_the_terraform_error():
    report = fresh(REPORT)
    report["terraform"]["terraform_apply"] = {"status": "failed", "errors": ["unknown attribute 'asn' in element 'bgpPeerP'"]}
    d = analysis.analyse("sales", "BGP_L3Out", fresh(INTENT), fresh(GENERATED), report)
    assert _stop(d).number == 3
    assert "bgpPeerP" in d.verdict


def test_an_unverifiable_fault_check_is_never_reported_as_ok():
    report = fresh(REPORT)
    report["apic_fault_checks"]["verify_apic_faults"].update(status="unverifiable", faults=[], detail="APIC timed out")
    d = analysis.analyse("sales", "BGP_L3Out", fresh(INTENT), fresh(GENERATED), report)
    assert d.layers[-1].state == "unknown"
    assert "could not verify" in d.verdict


def test_clean_fault_check_is_ok():
    report = fresh(REPORT)
    report["apic_fault_checks"]["verify_apic_faults"].update(status="clean", faults=[])
    d = analysis.analyse("sales", "BGP_L3Out", fresh(INTENT), fresh(GENERATED), report)
    assert d.layers[-1].state == "ok"


def test_tenant_level_counts_families_and_flags_nothing_unexplained():
    """On the simulator every fault in the pipeline-60 fixture is a known
    floor. The tenant's own faults and the fabric-wide one (F0699 under
    uni/infra, which belongs to no tenant) are counted apart."""
    d = analysis.analyse("sales", None, fresh(INTENT), fresh(GENERATED), fresh(REPORT), environment="simulator")
    assert {k: len(v) for k, v in d.fault_families.items()} == {
        "switch_absence": 1, "l4l7_without_concrete_device": 3,
    }
    assert {k: len(v) for k, v in d.shared_fault_families.items()} == {"switch_absence": 1}
    assert d.layers[-1].state == "warn"


def test_an_unknown_fault_is_unexplained_and_makes_layer_4_stop():
    report = fresh(REPORT)
    report["apic_fault_checks"]["verify_apic_faults"]["faults"].append(
        {"severity": "major", "code": "F9999", "dn": "uni/tn-sales/BD-Presales_BD/fault-F9999", "descr": "new"}
    )
    d = analysis.analyse("sales", None, fresh(INTENT), fresh(GENERATED), report)
    assert len(d.fault_families[analysis.UNEXPLAINED]) == 1
    assert d.layers[-1].state == "stop"
    assert "F9999" in d.kb_terms


def test_named_objects_treats_epgs_and_endpoint_groups_as_one_kind():
    assert ("epg", "Web_EPG") in analysis.named_objects(fresh(INTENT))
    assert ("epg", "Web_EPG") in analysis.named_objects(fresh(GENERATED)["intent"])


def test_missing_tenant_stops_at_layer_1():
    d = analysis.analyse("ghost", None, None, None, None, {"intent": "Tenant 'ghost' not found"})
    assert _stop(d).number == 1
    assert d.layers[0].detail == "Tenant 'ghost' not found"


# --- review fixes (2026-10-18) ------------------------------------------------

def _evpn_alongside(report: dict) -> dict:
    """The same pipeline with the EVPN domain's jobs present too."""
    report["terraform"]["evpn_terraform_plan"] = {"status": "success", "plan": {"add": 4, "change": 0, "destroy": 0}}
    report["awaiting_approval"] = ["evpn_terraform_apply"]
    report["apic_fault_checks"]["evpn_verify_apic_faults"] = {"status": "unverifiable", "faults": []}
    return report


def test_an_evpn_apply_awaiting_approval_does_not_stop_an_aci_diagnosis():
    """Job matching was endswith('terraform_apply'), which also matched
    evpn_terraform_apply: an applied ACI change was reported as unapproved."""
    report = _evpn_alongside(fresh(REPORT))
    d = analysis.analyse("sales", "BGP_L3Out", fresh(INTENT), fresh(GENERATED), report, environment="simulator")
    assert d.layers[2].state == "ok" and "116 added" in d.layers[2].detail
    assert d.layers[3].number == 4 and "awaits" not in d.verdict


def test_the_aci_fault_check_is_read_not_another_domains():
    report = _evpn_alongside(fresh(REPORT))
    report["apic_fault_checks"] = {"evpn_verify_apic_faults": report["apic_fault_checks"]["evpn_verify_apic_faults"],
                                   "verify_apic_faults": report["apic_fault_checks"]["verify_apic_faults"]}
    d = analysis.analyse("sales", None, fresh(INTENT), fresh(GENERATED), report, environment="simulator")
    assert d.layers[-1].state == "warn", "the EVPN check (first in the dict) must not be the one read"


def _with_fault(report: dict, fault: dict) -> dict:
    report["apic_fault_checks"]["verify_apic_faults"]["faults"].append(fault)
    return report


_HR_FAULT = {"severity": "major", "code": "F0467", "dn": "uni/tn-hr/ap-a/epg-Web_EPG/fault-F0467",
             "descr": "Configuration failed for EPG Web_EPG"}


def test_another_tenants_fault_is_not_charged_to_this_tenant():
    d = analysis.analyse("sales", None, fresh(INTENT), fresh(GENERATED), _with_fault(fresh(REPORT), _HR_FAULT),
                         environment="simulator")
    assert analysis.UNEXPLAINED not in d.fault_families
    assert d.other_tenant_faults == 1
    assert d.layers[-1].state == "warn"
    assert "1 belong to other tenants" in d.layers[-1].detail


def test_an_object_fault_must_be_in_this_tenant():
    """'Web_EPG' also exists in tenant hr; its fault is not sales' Web_EPG's."""
    d = analysis.analyse("sales", "Web_EPG", fresh(INTENT), fresh(GENERATED), _with_fault(fresh(REPORT), _HR_FAULT),
                         environment="simulator")
    assert d.object_faults == []


def test_aci_prefix_is_stripped_for_tenant_matching():
    d = analysis.analyse("ACI:sales", None, fresh(INTENT), fresh(GENERATED), fresh(REPORT), environment="simulator")
    assert sum(len(v) for v in d.fault_families.values()) == 4


def test_known_lab_families_are_not_explained_away_outside_the_simulator():
    """F1298 'Node Cannot Deploy' is the lab's floor -- no switch is
    registered -- but on a real fabric it is a genuine problem. Outside the
    simulator it is still classified, and it stops the diagnosis."""
    d = analysis.analyse("sales", "BGP_L3Out", fresh(INTENT), fresh(GENERATED), fresh(REPORT))
    assert d.environment == "production"
    assert d.layers[-1].state == "stop"
    assert "not expected outside the simulator" in d.verdict
    whole = analysis.analyse("sales", None, fresh(INTENT), fresh(GENERATED), fresh(REPORT))
    assert whole.layers[-1].state == "stop"


@pytest.mark.parametrize("fault,family", [
    ({"code": "F1893", "dn": "uni/fabric/bgpInstP-default/rr/node-1001/badselection/fault-F1893",
      "descr": "Node 1001 is marked as a route-reflector ... Please verify that node 1001 is reachable, "
               "and is not a leaf node. Only spine nodes can be BGP Route-Reflectors."}, "rr_node_not_registered_spine"),
    ({"code": "F0749", "dn": "uni/fabric/protpol/expgep-vpc-101-102/fault-F0749",
      "descr": "Failed to configure the vPC policy for the vPC pair 94 and a virtual IP address of 0.0.0.0 because: "
               "Both Nodes in VPC Not in Fabric,VPC Node IP Address Unknown,One Node in VPC is Not Leaf"},
     "vpc_pair_not_in_fabric"),
    ({"code": "F0756", "dn": "uni/tn-sales/ctx-prod/rsospfCtxPol/fault-F0756",
      "descr": "Failed to form relation to MO ospfCtxP-x of class ospfCtxPol"}, analysis.UNEXPLAINED),
])
def test_further_lab_floors_are_classified_and_a_real_defect_is_not(fault, family):
    assert analysis.classify_name(fault) == family
