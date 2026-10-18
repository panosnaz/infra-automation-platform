"""Parsers behind get_plan_changes (2026-10-18) -- no GitLab needed.

The plan fixture is framed exactly like the real terraform_plan traces of
pipelines 63 and 64 (timestamp + stream marker per line, the drift section
Terraform prints BEFORE "will perform the following actions"), with one of
every action so each is pinned. The markers fixture uses main.tf's real
comment conventions.
"""
from __future__ import annotations

from mcp_server.clients.gitlab import clean_trace, parse_plan_changes, parse_resource_markers

_PLAN_TRACE = """\
2026-10-18T18:52:29.960826Z 01O aci_vrf.this["sales/Presales_VRF"]: Refreshing state... [id=uni/tn-sales/ctx-Presales_VRF]
2026-10-18T18:52:31.000000Z 01O Note: Objects have changed outside of Terraform
2026-10-18T18:52:31.000001Z 01O Terraform detected the following changes made outside of Terraform since the
2026-10-18T18:52:31.000002Z 01O last "terraform apply" which may have affected this plan:
2026-10-18T18:52:31.000003Z 01O   # aci_bridge_domain.this["sales/Presales_BD"] has changed
2026-10-18T18:52:31.000004Z 01O   # aci_filter.this["sales/old_flt"] has been deleted
2026-10-18T18:52:32.000000Z 01O Terraform used the selected providers to generate the following execution
2026-10-18T18:52:32.000001Z 01O plan. Resource actions are indicated with the following symbols:
2026-10-18T18:52:32.000002Z 01O Terraform will perform the following actions:
2026-10-18T18:52:32.000003Z 01O   # aci_vrf.this["sales/approval-demo"] will be created
2026-10-18T18:52:32.000004Z 01O   + resource "aci_vrf" "this" {
2026-10-18T18:52:32.000005Z 01O   # aci_vrf.this["sales/Presales_VRF"] will be updated in-place
2026-10-18T18:52:32.000006Z 01O   # aci_contract.this["sales/old_ct"] will be destroyed
2026-10-18T18:52:32.000007Z 01O   # (because key ["sales/old_ct"] is not in for_each map)
2026-10-18T18:52:32.000008Z 01O   # aci_subnet.this["sales/Presales_BD/10.0.1.254/24"] must be replaced
2026-10-18T18:52:32.000009Z 01O   # aci_rest_managed.ntp_policy[0] will be updated in-place
2026-10-18T18:52:32.000010Z 01O Plan: 2 to add, 2 to change, 2 to destroy.
"""


def _parsed(trace=_PLAN_TRACE):
    return parse_plan_changes(clean_trace(trace))


def test_every_action_is_parsed_with_its_resource_type_and_key():
    changes = _parsed()["changes"]
    assert [(c["type"], c["key"], c["action"]) for c in changes] == [
        ("aci_vrf", "sales/approval-demo", "create"),
        ("aci_vrf", "sales/Presales_VRF", "update"),
        ("aci_contract", "sales/old_ct", "delete"),
        ("aci_subnet", "sales/Presales_BD/10.0.1.254/24", "replace"),
        ("aci_rest_managed", "0", "update"),
    ]
    assert changes[-1]["resource"] == "aci_rest_managed.ntp_policy"


def test_drift_before_the_actions_is_reported_apart_not_as_a_change():
    result = _parsed()
    assert result["drift"] == [
        {"address": 'aci_bridge_domain.this["sales/Presales_BD"]', "type": "aci_bridge_domain",
         "key": "sales/Presales_BD", "kind": "changed"},
        {"address": 'aci_filter.this["sales/old_flt"]', "type": "aci_filter", "key": "sales/old_flt", "kind": "deleted"},
    ]


def test_parsed_lines_are_counted_against_terraforms_own_summary():
    """A replace counts as one add and one destroy, as Terraform counts it."""
    result = _parsed()
    assert result["summary"] == {"add": 2, "change": 2, "destroy": 2}
    assert result["counted"] == {"add": 2, "change": 2, "destroy": 2}
    assert result["consistent"] is True


def test_a_list_that_does_not_add_up_is_flagged_never_presented_as_complete():
    trace = _PLAN_TRACE.replace("Plan: 2 to add, 2 to change, 2 to destroy.", "Plan: 3 to add, 2 to change, 2 to destroy.")
    result = _parsed(trace)
    assert result["consistent"] is False


def test_no_changes():
    result = parse_plan_changes(["No changes. Your infrastructure matches the configuration."])
    assert result == {"summary": {"add": 0, "change": 0, "destroy": 0}, "counted": {"add": 0, "change": 0, "destroy": 0},
                      "consistent": True, "changes": [], "drift": []}


def test_a_failed_plan_has_no_summary_and_is_not_consistent():
    result = parse_plan_changes(["Error: Creation of rest request failed", "Planning failed."])
    assert result["summary"] is None and result["consistent"] is False


_MAIN_TF = '''\
# NOT-SETTABLE[NS-10]: further VRF attributes (e.g. BD enforcement) not modelled.
resource "aci_vrf" "this" {
  for_each = local.vrfs
}

# EVIDENCE: plan-verified only -- see aci_l3out_path_attachment above. No
# BGP session can ever establish on this fabric (no switches).
resource "aci_bgp_peer_connectivity_profile" "this" {
  for_each = local.bgp_peers
}

resource "aci_contract" "this" {
}

# NOT-SETTABLE[NS-18]: NTP authentication not set.
# NOT-SETTABLE[NS-22]: targets the default time policy only.
resource "aci_rest_managed" "ntp_policy" {
}
'''


def test_markers_attach_to_the_resource_below_them():
    markers = parse_resource_markers(_MAIN_TF)
    assert markers["aci_vrf.this"] == {"not_settable": ["NS-10"], "evidence": []}
    assert markers["aci_rest_managed.ntp_policy"]["not_settable"] == ["NS-18", "NS-22"]
    evidence = markers["aci_bgp_peer_connectivity_profile.this"]["evidence"]
    assert evidence == ["plan-verified only -- see aci_l3out_path_attachment above. No BGP session can ever establish on "
                        "this fabric (no switches)."]
    assert "aci_contract.this" not in markers, "a resource with no marker is not listed"
