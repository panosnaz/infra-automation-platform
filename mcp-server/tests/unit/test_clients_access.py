"""Client-level tests for port-channels, vPC, static paths and node management
addresses -- against the strict in-memory fake in _fake_nautobot.py.

Each ACI rule the client enforces is tested in both directions, and every
refusal is checked to have written nothing.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.errors import NautobotError

from ._fake_nautobot import FakeApi


@pytest.fixture
def lab():
    api = FakeApi()
    client = NautobotClient.__new__(NautobotClient)
    client._api = api
    loc = api.dcim.locations.add(id="loc1", name="Lab", custom_fields={"aci_fabric_policies": {
        "aeps": [{"name": "AEP1"}],
        "leaf_interface_policy_groups": [{"name": "Access_IPG", "aep": "AEP1"}],
    }})
    client._get_location_or_raise = lambda name=None: loc
    for nid in (101, 102, 103, 104):
        api.dcim.devices.add(id=f"d{nid}", name=f"leaf{nid}", serial="", location=SimpleNamespace(id="loc1"),
                             role=SimpleNamespace(name="leaf"), custom_fields={"aci_node_id": nid, "aci_pod_id": 1})
    tenant = api.tenancy.tenants.add(id="t1", name="ACI:sales", custom_fields={})
    vlan = api.ipam.vlans.add(id="l1", name="web", vid=10, tenant=SimpleNamespace(id="t1"), custom_fields={
        "aci_application_profile": "app", "aci_epg_bridge_domain": "bd",
    })
    return SimpleNamespace(api=api, client=client, loc=loc, tenant=tenant, vlan=vlan)


def _fabric(lab):
    return lab.loc.custom_fields["aci_fabric_policies"]


def _vpc_ready(lab):
    lab.client.create_lacp_policy(None, "LACP_Active", "active")
    lab.client.create_vpc_domain(None, "vpc-101-102", 10, 101, 102)
    lab.client.create_pc_vpc_policy_group(None, "Srv1_vPC", "vpc", aep="AEP1", lacp_policy="LACP_Active")
    lab.client.create_pc_vpc_policy_group(None, "Srv2_PC", "port_channel", aep="AEP1", lacp_policy="LACP_Active")


# --- LACP / vPC domain ----------------------------------------------------------

def test_lacp_policy_is_stored_and_a_duplicate_refused(lab):
    lab.client.create_lacp_policy(None, "LACP_Active", "active", min_links=2)
    assert _fabric(lab)["lacp_policies"] == [{"name": "LACP_Active", "mode": "active", "min_links": 2}]
    with pytest.raises(NautobotError, match="already exists"):
        lab.client.create_lacp_policy(None, "LACP_Active", "passive")


def test_update_lacp_refuses_min_above_max(lab):
    lab.client.create_lacp_policy(None, "L", "active", max_links=4)
    with pytest.raises(NautobotError, match="min_links cannot exceed"):
        lab.client.update_lacp_policy(None, "L", min_links=8)


def test_vpc_domain_needs_both_leaves_in_the_inventory(lab):
    with pytest.raises(NautobotError, match=r"\[999\] are not in the Nautobot fabric inventory"):
        lab.client.create_vpc_domain(None, "v", 10, 101, 999)
    assert lab.loc.updates == []


def test_a_leaf_can_be_in_only_one_vpc_pair(lab):
    lab.client.create_vpc_domain(None, "v1", 10, 101, 102)
    with pytest.raises(NautobotError, match="only one vPC pair"):
        lab.client.create_vpc_domain(None, "v2", 11, 102, 103)


def test_vpc_domain_ids_are_unique(lab):
    lab.client.create_vpc_domain(None, "v1", 10, 101, 102)
    with pytest.raises(NautobotError, match="already used"):
        lab.client.create_vpc_domain(None, "v2", 10, 103, 104)


def test_moving_a_vpc_pair_is_refused_while_an_epg_uses_it(lab):
    _vpc_ready(lab)
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10",
                                          path_type="vpc", node_id2=102, policy_group="Srv1_vPC")
    with pytest.raises(NautobotError, match="Unbind those static paths first"):
        lab.client.update_vpc_domain(None, "vpc-101-102", node1=103, node2=104)
    # changing only the domain ID does not touch the pair, so it is allowed
    lab.client.update_vpc_domain(None, "vpc-101-102", domain_id=20)
    assert _fabric(lab)["vpc_domains"][0]["domain_id"] == 20


# --- PC/vPC policy group -----------------------------------------------------------

def test_bundle_group_refuses_an_unknown_aep_or_lacp(lab):
    with pytest.raises(NautobotError, match="AEP 'nope'"):
        lab.client.create_pc_vpc_policy_group(None, "G", "vpc", aep="nope")
    with pytest.raises(NautobotError, match="LACP policy 'nope'"):
        lab.client.create_pc_vpc_policy_group(None, "G", "vpc", lacp_policy="nope")
    assert lab.loc.updates == []


def test_bundle_group_cannot_share_a_name_with_an_access_group(lab):
    """Selectors name their policy group and main.tf resolves the name across
    both kinds, so a shared name would be ambiguous."""
    with pytest.raises(NautobotError, match="access-port policy group"):
        lab.client.create_pc_vpc_policy_group(None, "Access_IPG", "port_channel")


def test_bundle_group_without_lacp_warns_that_it_is_static(lab):
    result = lab.client.create_pc_vpc_policy_group(None, "G", "port_channel", aep="AEP1")
    assert "mode 'off'" in result["warning"]


# --- static paths ----------------------------------------------------------------

def _paths(lab):
    return lab.api.ipam.vlans.get(name="web").custom_fields["aci_static_paths"]


def test_a_second_static_path_does_not_remove_the_first(lab):
    """The bug this change fixed: every call used to REPLACE the EPG's list."""
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10", module=1, port=1)
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10", module=1, port=2)
    assert [(p["node_id"], p["port"]) for p in _paths(lab)] == [(101, 1), (101, 2)]


def test_the_same_path_again_replaces_only_itself(lab):
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10", module=1, port=1)
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-20", module=1, port=1)
    assert [p["encap"] for p in _paths(lab)] == ["vlan-20"]


def test_a_port_path_keeps_its_original_shape(lab):
    """Existing port bindings carry no path_type; main.tf keys them by
    node/module/port. Writing path_type would change nothing functionally but
    a key change would make Terraform replace every existing binding."""
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10", module=1, port=1)
    assert "path_type" not in _paths(lab)[0]


def test_vpc_binding_is_stored_with_its_pair_and_group(lab):
    _vpc_ready(lab)
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 102, "vlan-10",
                                          path_type="vpc", node_id2=101, policy_group="Srv1_vPC")
    assert _paths(lab) == [{"pod_id": 1, "node_id": 102, "encap": "vlan-10", "mode": "regular",
                            "path_type": "vpc", "policy_group": "Srv1_vPC", "node_id2": 101}]


def test_vpc_binding_needs_a_vpc_domain_for_exactly_that_pair(lab):
    _vpc_ready(lab)
    with pytest.raises(NautobotError, match=r"No vPC domain pairs nodes \[103, 104\]"):
        lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 103, "vlan-10",
                                              path_type="vpc", node_id2=104, policy_group="Srv1_vPC")
    assert lab.vlan.updates == []


def test_binding_type_must_match_the_group_type(lab):
    _vpc_ready(lab)
    with pytest.raises(NautobotError, match="is a vpc group, but this is a port_channel binding"):
        lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10",
                                              path_type="port_channel", policy_group="Srv1_vPC")


def test_unbind_removes_only_that_path(lab):
    _vpc_ready(lab)
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10", module=1, port=1)
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10",
                                          path_type="vpc", node_id2=102, policy_group="Srv1_vPC")
    # the pair given in the other order is the same vPC
    lab.client.unbind_epg_static_path("ACI:sales", "app", "web",
                                      {"path_type": "vpc", "node_id": 102, "node_id2": 101, "policy_group": "Srv1_vPC"})
    assert [p.get("path_type", "port") for p in _paths(lab)] == ["port"]
    with pytest.raises(NautobotError, match="no binding to"):
        lab.client.unbind_epg_static_path("ACI:sales", "app", "web",
                                          {"path_type": "vpc", "node_id": 101, "node_id2": 102, "policy_group": "Srv1_vPC"})


# --- deletes with references -------------------------------------------------------

def test_a_bundle_group_bound_by_an_epg_cannot_be_deleted(lab):
    _vpc_ready(lab)
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10",
                                          path_type="port_channel", policy_group="Srv2_PC")
    with pytest.raises(NautobotError, match="EPG 'web' in tenant 'ACI:sales' is bound to port-channel Srv2_PC"):
        lab.client.delete_fabric_object("pc_vpc_policy_group", "Srv2_PC")


def test_an_lacp_policy_in_use_cannot_be_deleted(lab):
    _vpc_ready(lab)
    with pytest.raises(NautobotError, match="PC/vPC policy group 'Srv1_vPC' uses this LACP policy"):
        lab.client.delete_fabric_object("lacp_policy", "LACP_Active")


def test_a_vpc_domain_in_use_cannot_be_deleted_but_an_idle_one_can(lab):
    _vpc_ready(lab)
    lab.client.create_static_path_binding("ACI:sales", "app", "web", 1, 101, "vlan-10",
                                          path_type="vpc", node_id2=102, policy_group="Srv1_vPC")
    with pytest.raises(NautobotError, match="needs this vPC pair"):
        lab.client.delete_fabric_object("vpc_domain", "vpc-101-102")
    lab.client.unbind_epg_static_path("ACI:sales", "app", "web",
                                      {"path_type": "vpc", "node_id": 101, "node_id2": 102, "policy_group": "Srv1_vPC"})
    lab.client.delete_fabric_object("vpc_domain", "vpc-101-102")
    assert "vpc_domains" not in _fabric(lab)


# --- management addresses -----------------------------------------------------------

def test_oob_address_creates_mgmt0_the_ip_and_its_parent_prefix(lab):
    result = lab.client.create_node_mgmt_address(101, "out_of_band", "10.48.0.101/24", "10.48.0.1")
    assert result["created_interface"] == "mgmt0"
    assert result["created_parent_prefix"] == "10.48.0.0/24"
    [ip] = lab.api.ipam.ip_addresses.items
    assert ip.custom_fields == {"aci_mgmt_type": "out_of_band", "aci_mgmt_gateway": "10.48.0.1", "aci_mgmt_epg": "default"}
    assert ip.namespace.id == "ns-global"
    assert ip.device.id == "d101"


def test_an_existing_parent_prefix_is_reused_not_duplicated(lab):
    lab.api.ipam.prefixes.add(prefix="10.48.0.0/16")
    result = lab.client.create_node_mgmt_address("leaf101", "out_of_band", "10.48.0.101/24", "10.48.0.1")
    assert "created_parent_prefix" not in result
    assert len(lab.api.ipam.prefixes.items) == 1


def test_one_address_per_switch_per_type(lab):
    lab.client.create_node_mgmt_address(101, "out_of_band", "10.48.0.101/24", "10.48.0.1")
    with pytest.raises(NautobotError, match="already has an out_of_band"):
        lab.client.create_node_mgmt_address(101, "out_of_band", "10.48.0.111/24", "10.48.0.1")


def test_an_unknown_switch_is_refused_naming_the_roster(lab):
    with pytest.raises(NautobotError, match=r"known nodes: 101 \(leaf101\)"):
        lab.client.create_node_mgmt_address(999, "out_of_band", "10.48.0.9/24", "10.48.0.1")


def test_in_band_needs_a_declared_epg(lab):
    with pytest.raises(NautobotError, match="create_inband_mgmt_epg"):
        lab.client.create_node_mgmt_address(101, "in_band", "10.49.0.101/24", "10.49.0.1", epg="inb-epg")
    assert lab.api.ipam.ip_addresses.items == []
    lab.client.create_inband_mgmt_epg(None, "inb-epg", 99)
    lab.client.create_node_mgmt_address(101, "in_band", "10.49.0.101/24", "10.49.0.1", epg="inb-epg")
    assert lab.api.dcim.interfaces.get(name="inband-mgmt") is not None


def test_update_gateway_in_place_and_address_by_replacement(lab):
    lab.client.create_node_mgmt_address(101, "out_of_band", "10.48.0.101/24", "10.48.0.1")
    lab.client.update_node_mgmt_address(101, "out_of_band", gateway="10.48.0.254")
    [ip] = lab.api.ipam.ip_addresses.items
    assert ip.custom_fields["aci_mgmt_gateway"] == "10.48.0.254"
    lab.client.update_node_mgmt_address(101, "out_of_band", address="10.48.0.201/24")
    [ip] = lab.api.ipam.ip_addresses.items
    assert ip.address == "10.48.0.201/24" and ip.custom_fields["aci_mgmt_gateway"] == "10.48.0.254"
    assert ip.device.id == "d101"


def test_delete_mgmt_address_keeps_the_interface(lab):
    lab.client.create_node_mgmt_address(101, "out_of_band", "10.48.0.101/24", "10.48.0.1")
    lab.client.delete_node_mgmt_address(101, "out_of_band")
    assert lab.api.ipam.ip_addresses.items == []
    assert lab.api.dcim.interfaces.get(name="mgmt0") is not None


def test_an_inband_epg_in_use_cannot_be_deleted(lab):
    lab.client.create_inband_mgmt_epg(None, "inb-epg", 99)
    lab.client.create_node_mgmt_address(101, "in_band", "10.49.0.101/24", "10.49.0.1", epg="inb-epg")
    with pytest.raises(NautobotError, match="10.49.0.101/24 of node leaf101 uses this EPG"):
        lab.client.delete_fabric_object("inband_mgmt_epg", "inb-epg")


def test_fabric_intent_shows_each_nodes_management_addresses(lab):
    lab.client.create_node_mgmt_address(101, "out_of_band", "10.48.0.101/24", "10.48.0.1")
    nodes = {n["node_id"]: n for n in lab.client.get_fabric_intent()["fabric_nodes"]}
    assert nodes[101]["management"] == [
        {"type": "out_of_band", "address": "10.48.0.101/24", "gateway": "10.48.0.1", "epg": "default"}
    ]
    assert nodes[102]["management"] == []


def test_deleting_the_last_entry_removes_the_key_too(lab):
    """A delete leaves intent as it found it: no `lacp_policies: []` residue
    on a Location that had no LACP policies before (found by the live run's
    snapshot comparison, 2026-10-12)."""
    lab.client.create_lacp_policy(None, "L", "active")
    lab.client.delete_fabric_object("lacp_policy", "L")
    assert "lacp_policies" not in _fabric(lab)
