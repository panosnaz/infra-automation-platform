"""Cross-layer analysis: each test pins where an object stops travelling."""
from __future__ import annotations

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
    d = analysis.analyse("sales", None, fresh(INTENT), fresh(GENERATED), fresh(REPORT))
    assert {k: len(v) for k, v in d.fault_families.items()} == {
        "switch_absence": 2, "l4l7_without_concrete_device": 3,
    }
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
