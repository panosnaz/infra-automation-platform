"""Every attribute the generator writes into the NetAsCode YAML must be read
by the Terraform resource that deploys it -- otherwise the intent stops at the
YAML, the plan shows nothing and every tool reports success.

Found live 2026-10-18 (pipeline 70): `aci_vrf.this` had never set
`description` -- not since the module's first commit -- so `create_vrf` /
`update_vrf` descriptions reached Nautobot and the YAML and never the APIC.
Its block even said "exactly like `description` above already does", which is
why a text search for the word passed: comments are stripped below.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_MAIN_TF = Path(__file__).resolve().parents[2] / "platform" / "terraform" / "aci" / "main.tf"

# Keys the generator itself emits on each object kind (transformer.py), and
# the resource that deploys that kind.
GENERATED = {
    "aci_tenant.this": ("description",),
    "aci_vrf.this": ("description",),
    "aci_application_epg.this": ("description",),
    # Named CDP / LLDP interface policies (2026-10-30): the intent keys are the
    # provider's own (non-deprecated) attribute names.
    "aci_cdp_interface_policy.named": ("name", "admin_state", "description"),
    "aci_lldp_interface_policy.named": ("name", "receive_state", "transmit_state", "description"),
}


def _resource_body(address: str) -> str:
    rtype, name = address.split(".")
    text = _MAIN_TF.read_text(encoding="utf-8")
    match = re.search(rf'^resource "{rtype}" "{name}" {{\n(.*?)^}}', text, re.S | re.M)
    assert match, f"{address} not found in main.tf"
    return "\n".join(line.split("#", 1)[0] for line in match.group(1).splitlines())


@pytest.mark.parametrize("address", sorted(GENERATED))
def test_generated_keys_are_assigned_by_their_resource(address):
    body = _resource_body(address)
    missing = [key for key in GENERATED[address] if not re.search(rf"^\s*{key}\s*=", body, re.M)]
    assert missing == [], f"{address} never assigns {missing}: the YAML carries it, the APIC never gets it"


def test_comments_do_not_count_as_assignments():
    assert "description" not in "\n".join(line.split("#", 1)[0] for line in ["  # like `description` above"])


def test_a_policy_group_selects_the_named_cdp_and_lldp_policies():
    body = _resource_body("aci_leaf_access_port_policy_group.this")
    for rtype, key in (("aci_cdp_interface_policy", "cdp_policy"), ("aci_lldp_interface_policy", "lldp_policy")):
        assert f"{rtype}.named[each.value.{key}]" in body, f"the group never uses {rtype}.named"


def test_the_bgp_protocol_profile_exists_only_for_explicit_bgp_policies():
    """A BGP L3Out without a timers or best-path policy must not get a BGP
    Protocol Profile (bgpProtP): the APIC default timers apply without one, and
    the change owner asked that none be created unless timers differ
    (2026-10-30). Until then every BGP L3Out got an empty profile."""
    body = _resource_body("aci_l3out_bgp_protocol_profile.this")
    for_each = re.search(r"^\s*for_each\s*=(.*?)^\s*logical_node_profile_dn", body, re.S | re.M).group(1)
    assert "bgp_timers_policy" in for_each and "bgp_best_path_policy" in for_each, for_each
