"""Client-level tests for the fabric-wide policy tools (2026-10-13), against
the strict fake in _fake_nautobot.py."""
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
    loc = api.dcim.locations.add(id="loc1", name="Lab", custom_fields={"aci_fabric_policies": {"vlan_pools": [{"name": "keep"}]}})
    client._get_location_or_raise = lambda name=None: loc
    return SimpleNamespace(client=client, loc=loc)


def _fp(lab):
    return lab.loc.custom_fields["aci_fabric_policies"]


def test_singletons_merge_and_keep_other_intent(lab):
    lab.client.set_isis_policy(None, mtu=1492)
    lab.client.set_isis_policy(None, redistrib_metric=60)
    assert _fp(lab)["isis"] == {"mtu": 1492, "redistrib_metric": 60}
    assert _fp(lab)["vlan_pools"] == [{"name": "keep"}]


def test_snmp_system_location_is_written_where_terraform_reads_it(lab):
    """main.tf reads `location` for sysLocation; the tool calls it
    system_location so it cannot be confused with a Nautobot Location."""
    lab.client.set_snmp_policy(None, admin_state="enabled", system_location="DC1 Row 4")
    assert _fp(lab)["snmp"] == {"admin_state": "enabled", "location": "DC1 Row 4"}


def test_ntp_servers_create_update_delete(lab):
    lab.client.create_ntp_server(None, "10.0.0.1", preferred=True)
    with pytest.raises(NautobotError, match="already exists"):
        lab.client.create_ntp_server(None, "10.0.0.1")
    lab.client.update_ntp_server(None, "10.0.0.1", max_poll=8)
    assert _fp(lab)["ntp"]["servers"] == [{"address": "10.0.0.1", "preferred": True, "min_poll": 4, "max_poll": 8}]
    with pytest.raises(NautobotError, match="cannot exceed"):
        lab.client.update_ntp_server(None, "10.0.0.1", min_poll=9)
    lab.client.delete_ntp_server(None, "10.0.0.1")
    assert "ntp" not in _fp(lab), "the last server gone and no other NTP intent: no residue"


def test_deleting_an_unknown_server_names_the_known_ones(lab):
    lab.client.create_dns_server(None, "10.0.0.53")
    with pytest.raises(NautobotError, match="known: 10.0.0.53"):
        lab.client.delete_dns_server(None, "10.9.9.9")


def test_only_one_default_dns_domain(lab):
    lab.client.create_dns_domain(None, "a.example.com", is_default=True)
    lab.client.create_dns_domain(None, "b.example.com", is_default=True)
    domains = {d["name"]: d["is_default"] for d in _fp(lab)["dns"]["domains"]}
    assert domains == {"a.example.com": False, "b.example.com": True}


def test_snmp_community_stores_only_the_reference(lab):
    result = lab.client.create_snmp_community(None, "ro-monitoring")
    assert _fp(lab)["snmp"]["communities"] == [{"ref": "ro-monitoring"}]
    assert "snmp_community_strings" in result["secret"]


def test_reset_removes_the_intent_and_says_what_happens(lab):
    lab.client.set_coop_policy(None, "compatible")
    result = lab.client.reset_fabric_policy(None, "coop")
    assert "coop" not in _fp(lab)
    assert "KEEPS the last COOP type" in result["effect"]
    lab.client.set_fault_lifecycle_policy(None, retain=7200)
    assert "restores APIC's default" in lab.client.reset_fabric_policy(None, "fault_lifecycle")["effect"]
    with pytest.raises(NautobotError, match="nothing to reset"):
        lab.client.reset_fabric_policy(None, "ntp")


# --- BGP route reflector policy / pod assignment (2026-10-14) -----------------

def _switches(lab):
    for name, nid, role in (("spine1001", 1001, "spine"), ("leaf101", 101, "leaf")):
        lab.client._api.dcim.devices.add(id=f"d{nid}", name=name, serial="", location=SimpleNamespace(id="loc1"),
                                         role=SimpleNamespace(name=role), custom_fields={"aci_node_id": nid, "aci_pod_id": 1})


def test_route_reflector_policy_sets_the_as_and_warns(lab):
    result = lab.client.set_bgp_route_reflector_policy(None, 65099)
    assert _fp(lab)["bgp_route_reflector"] == {"asn": 65099}
    assert "resets every MP-BGP session" in result["warning"]


def test_route_reflector_nodes_resolve_by_name_or_node_id_and_only_spines(lab):
    _switches(lab)
    lab.client.set_bgp_route_reflector_policy(None, 65099)
    lab.client.create_bgp_route_reflector_node(None, "1001")
    assert _fp(lab)["bgp_route_reflector"]["nodes"] == [{"node_id": 1001, "pod_id": 1}]
    with pytest.raises(NautobotError, match=r"'spine1001' \(node 1001\) is already a route reflector"):
        lab.client.create_bgp_route_reflector_node(None, "spine1001")
    with pytest.raises(NautobotError, match="'leaf101' is a leaf, not a spine"):
        lab.client.create_bgp_route_reflector_node(None, "leaf101")
    with pytest.raises(NautobotError, match="No fabric switch '1999'"):
        lab.client.create_bgp_route_reflector_node(None, "1999")
    lab.client.delete_bgp_route_reflector_node(None, 1001)
    assert _fp(lab)["bgp_route_reflector"] == {"asn": 65099}, "the AS stays when the last node goes"
    with pytest.raises(NautobotError, match="not found"):
        lab.client.delete_bgp_route_reflector_node(None, 1001)


def test_assigning_a_pod_policy_group_needs_the_group(lab):
    with pytest.raises(NautobotError, match="Pod Policy Group 'pg1' does not exist"):
        lab.client.assign_pod_policy_group(None, "pg1")
    lab.client.create_pod_policy_group(None, "pg1")
    lab.client.assign_pod_policy_group(None, "pg1")
    assert _fp(lab)["pod_profile"] == {"policy_group": "pg1"}


def test_an_assigned_pod_policy_group_cannot_be_deleted(lab):
    lab.client.create_pod_policy_group(None, "pg1")
    lab.client.assign_pod_policy_group(None, "pg1")
    with pytest.raises(NautobotError, match="pod selector"):
        lab.client.delete_fabric_object("pod_policy_group", "pg1")
    lab.client.reset_fabric_policy(None, "pod_profile")
    lab.client.delete_fabric_object("pod_policy_group", "pg1")
    assert "pod_policy_groups" not in _fp(lab)
