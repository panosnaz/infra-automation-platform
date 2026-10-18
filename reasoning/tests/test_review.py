"""Workflow `review-plan` (ADR-022 roadmap 2): a plain-language summary of a
pending Terraform plan, read-only. Each test pins one thing the approver must
be told -- or must never be told falsely."""
from __future__ import annotations

import copy

from platform_reasoning import review
from platform_reasoning.mcp_reader import READ_ONLY_TOOLS

PLAN = {
    "found": True,
    "pipeline": {"id": 66, "status": "manual", "ref": "copilot/aci-platform-comparison", "sha": "1a2b3c4d5e6f",
                 "web_url": "http://gitlab/p/66"},
    "plan_job": {"id": 660, "status": "success"},
    "apply_job": {"id": 661, "status": "manual"},
    "awaiting_approval": True,
    "summary": {"add": 1, "change": 1, "destroy": 0},
    "counted": {"add": 1, "change": 1, "destroy": 0},
    "consistent": True,
    "changes": [
        {"address": 'aci_vrf.this["sales/approval-demo"]', "resource": "aci_vrf.this", "type": "aci_vrf",
         "key": "sales/approval-demo", "action": "create"},
        {"address": 'aci_vrf.this["sales/Presales_VRF"]', "resource": "aci_vrf.this", "type": "aci_vrf",
         "key": "sales/Presales_VRF", "action": "update"},
    ],
    "drift": [],
    "markers": {"aci_vrf.this": {"evidence": [], "not_settable": [
        {"id": "NS-10", "title": "Further VRF / BD / EPG attributes"}]}},
}


def plan(**changes):
    p = copy.deepcopy(PLAN)
    p.update(changes)
    return p


def test_counts_are_in_plain_words_and_nothing_deleted_is_said_plainly():
    s = review.summarise(plan())
    assert s.lines["create"] == ["1 VRF: sales/approval-demo"]
    assert s.lines["update"] == ["1 VRF: sales/Presales_VRF"]
    assert s.headline == "Creates 1, changes 1, deletes 0. Nothing is deleted or replaced."
    assert s.risk == "low"


def test_every_deletion_and_replacement_is_called_out_by_name():
    changes = PLAN["changes"] + [
        {"address": 'aci_contract.this["sales/old_ct"]', "resource": "aci_contract.this", "type": "aci_contract",
         "key": "sales/old_ct", "action": "delete"},
        {"address": 'aci_subnet.this["sales/BD/10.0.1.254/24"]', "resource": "aci_subnet.this", "type": "aci_subnet",
         "key": "sales/BD/10.0.1.254/24", "action": "replace"},
    ]
    s = review.summarise(plan(changes=changes, summary={"add": 2, "change": 1, "destroy": 2},
                              counted={"add": 2, "change": 1, "destroy": 2}))
    assert s.risk == "review deletions"
    assert "DELETES 1" in s.headline and "REPLACES 1" in s.headline
    assert s.lines["delete"] == ["1 contract: sales/old_ct"]
    assert s.lines["replace"] == ["1 BD subnet: sales/BD/10.0.1.254/24"]


def test_caveats_of_what_changes_are_listed():
    s = review.summarise(plan())
    assert s.caveats == ["VRF: NS-10 not yet settable -- Further VRF / BD / EPG attributes"]


def test_a_list_that_does_not_add_up_is_never_presented_as_complete():
    s = review.summarise(plan(consistent=False, counted={"add": 1, "change": 0, "destroy": 0}))
    assert s.risk == "incomplete"
    assert "does not add up" in s.headline and "read the job log" in s.headline


def test_no_changes_says_approving_would_apply_nothing():
    s = review.summarise(plan(changes=[], summary={"add": 0, "change": 0, "destroy": 0},
                              counted={"add": 0, "change": 0, "destroy": 0}, markers={}))
    assert s.headline == "No changes: approving would apply nothing."


def test_drift_is_reported():
    s = review.summarise(plan(drift=[{"address": "x", "type": "aci_bridge_domain", "key": "sales/BD", "kind": "changed"}]))
    assert s.drift == ["bridge domain sales/BD changed outside Terraform since the last apply"]


def test_a_plan_that_did_not_succeed_is_not_summarised():
    s = review.summarise(plan(plan_job={"id": 1, "status": "failed"}, reason="terraform_plan failed -- there is no plan to summarise"))
    assert s.risk == "no plan" and "no plan to summarise" in s.headline


def test_the_report_approves_nothing_and_says_whose_decision_it_is():
    text = review.render(review.summarise(plan()), reads=["get_plan_changes"])
    assert "WAITING FOR YOUR APPROVAL" in text
    assert "This review approves nothing" in text and "http://gitlab/p/66" in text
    assert "0 writes" in text


def test_a_superseded_plan_is_the_first_thing_said():
    s = review.summarise(plan(superseded_by=67))
    assert s.headline.startswith("OUTDATED: pipeline 67 planned this branch after this one")
    assert s.risk == "outdated"


def test_names_read_naturally():
    assert review._plural(8, review.friendly("aci_filter_entry")) == "8 filter entries"
    assert review._plural(2, review.friendly("aci_destination_of_redirected_traffic")) == "2 PBR destinations"
    assert review._plural(3, review.friendly("aci_ranges")) == "3 VLAN ranges"
    assert review._plural(2, review.friendly("aci_epg_to_static_path")) == "2 EPG static paths"


def test_review_plan_needs_only_read_tools():
    assert review.REQUIRED_TOOLS <= READ_ONLY_TOOLS


def test_every_allowlisted_tool_is_named_as_a_read():
    """Stronger than rejecting known write prefixes: a write tool with an
    unusual name (decommission_tenant, migrate_...) would pass that test."""
    assert all(t.startswith(("get_", "list_", "show_")) for t in READ_ONLY_TOOLS)


async def test_the_graph_reads_one_tool_and_writes_nothing():
    class _Reader:
        def __init__(self):
            self.calls = []

        async def call(self, tool, **arguments):
            self.calls.append(tool)
            return copy.deepcopy(PLAN)

    reader = _Reader()
    state = await review.review(reader, pipeline_id=66)
    assert reader.calls == ["get_plan_changes"]
    assert "Creates 1, changes 1, deletes 0" in state["report"]
