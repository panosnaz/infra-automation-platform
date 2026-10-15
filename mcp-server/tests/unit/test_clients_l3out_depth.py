"""Client tests for L3Out depth (2026-10-16), against the strict in-memory
fake of the pynautobot API."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.errors import NautobotError

from ._fake_nautobot import FakeApi

T = "ACI:sales"


@pytest.fixture
def lab():
    api = FakeApi()
    client = NautobotClient.__new__(NautobotClient)
    client._api = api
    tenant = api.tenancy.tenants.add(id="t1", name=T, custom_fields={"aci_l3outs": {"l3outs": [
        {"name": "bgp-out", "vrf": "prod", "protocol": "bgp", "external_epgs": [
            {"name": "ext", "subnets": [{"ip": "10.9.0.0/16", "scope": ["export-rtctrl"]}]}],
         "node_profiles": [{"name": "np", "nodes": [{"node_id": 101, "pod_id": 1}, {"node_id": 102, "pod_id": 1}],
                            "interface_profiles": [{"name": "ifp", "interfaces": []}]}]},
        {"name": "ospf-out", "vrf": "prod", "protocol": "ospf", "external_epgs": []},
    ]}})
    prod = api.ipam.vrfs.add(id="v1", name="prod", tenant=SimpleNamespace(id="t1"), custom_fields={})
    loc = api.dcim.locations.add(id="loc1", name="Lab", custom_fields={"aci_fabric_policies": {
        "vpc_domains": [{"name": "vpc", "domain_id": 9, "node1": 101, "node2": 102}],
        "pc_vpc_policy_groups": [{"name": "vpc-ipg", "bundle_type": "vpc"}, {"name": "pc-ipg", "bundle_type": "port_channel"}],
    }})
    client._get_location_or_raise = lambda name=None: loc
    return SimpleNamespace(api=api, client=client, tenant=tenant, prod=prod)


def _out(lab, name="bgp-out"):
    return next(o for o in lab.tenant.custom_fields["aci_l3outs"]["l3outs"] if o["name"] == name)


def _node(lab, node_id=101):
    return next(n for n in _out(lab)["node_profiles"][0]["nodes"] if n["node_id"] == node_id)


def _policies(lab):
    return lab.tenant.custom_fields["aci_protocol_policies"]


# --- tenant policies -------------------------------------------------------------

def test_protocol_policies_store_only_what_was_set_and_refuse_duplicates(lab):
    lab.client.create_bgp_timers_policy(T, "t1", keepalive_interval=30, hold_interval=90)
    lab.client.create_route_tag_policy(T, "rt", tag=100)
    assert _policies(lab) == {"bgp_timers_policies": [{"name": "t1", "keepalive_interval": 30, "hold_interval": 90}],
                              "route_tag_policies": [{"name": "rt", "tag": 100}]}
    with pytest.raises(NautobotError, match="BGP timers policy 't1' already exists"):
        lab.client.create_bgp_timers_policy(T, "t1")


def test_bfd_policy_lives_with_the_other_interface_policies(lab):
    lab.client.create_bfd_interface_policy(T, "bfd1", detect_multiplier=3)
    assert lab.tenant.custom_fields["aci_interface_policies"]["bfd_interface_policies"] == [
        {"name": "bfd1", "detect_multiplier": 3}]


@pytest.mark.parametrize("keepalive,hold,message", [
    (60, 60, r"hold interval \(60\) must be greater than the keepalive interval \(60\)"),
    (90, 60, "must be greater than the keepalive"),
    (30, 0, "a hold interval of 0 needs a keepalive of 0"),
    (None, 30, r"hold interval \(30\) must be greater than the keepalive interval \(60\)"),
])
def test_bgp_timer_rules_the_apic_enforces(lab, keepalive, hold, message):
    """APIC 6.2 answers HTTP 400 for each (probed 2026-10-16); 60/90 is accepted
    -- there is no 3x rule."""
    with pytest.raises(NautobotError, match=message):
        lab.client.create_bgp_timers_policy(T, "t1", keepalive_interval=keepalive, hold_interval=hold)
    lab.client.create_bgp_timers_policy(T, f"ok-{keepalive}-{hold}", keepalive_interval=60, hold_interval=90)


# --- static routes / loopbacks -------------------------------------------------------

def test_static_routes_create_and_delete(lab):
    lab.client.create_l3out_static_route(T, "bgp-out", "np", 101, "10.9.100.0/24",
                                         next_hops=[{"ip": "10.9.1.254", "preference": 1}], bfd=True)
    assert _node(lab)["static_routes"] == [{"prefix": "10.9.100.0/24", "bfd": True,
                                            "next_hops": [{"ip": "10.9.1.254", "preference": 1}]}]
    with pytest.raises(NautobotError, match="static route 10.9.100.0/24 already exists on node 101"):
        lab.client.create_l3out_static_route(T, "bgp-out", "np", 101, "10.9.100.0/24")
    with pytest.raises(NautobotError, match="node 999 is not in node profile 'np' .*known: 101, 102"):
        lab.client.create_l3out_static_route(T, "bgp-out", "np", 999, "10.9.100.0/24")
    lab.client.delete_l3out_static_route(T, "bgp-out", "np", 101, "10.9.100.0/24")
    assert "static_routes" not in _node(lab)
    with pytest.raises(NautobotError, match="no static route 10.9.100.0/24 on node 101"):
        lab.client.delete_l3out_static_route(T, "bgp-out", "np", 101, "10.9.100.0/24")


def test_loopbacks_create_and_delete(lab):
    lab.client.create_l3out_loopback(T, "bgp-out", "np", 102, "10.9.254.2")
    assert _node(lab, 102)["loopbacks"] == [{"ip": "10.9.254.2"}]
    with pytest.raises(NautobotError, match="loopback 10.9.254.2 already exists on node 102"):
        lab.client.create_l3out_loopback(T, "bgp-out", "np", 102, "10.9.254.2")
    lab.client.delete_l3out_loopback(T, "bgp-out", "np", 102, "10.9.254.2")
    assert "loopbacks" not in _node(lab, 102)


def test_unknown_l3out_and_node_profile_name_the_known_ones(lab):
    with pytest.raises(NautobotError, match="L3Out 'ghost' not found in tenant 'ACI:sales' \\(known: bgp-out, ospf-out\\)"):
        lab.client.create_l3out_loopback(T, "ghost", "np", 101, "10.9.254.1")
    with pytest.raises(NautobotError, match="Node profile 'ghost' not found in L3Out 'bgp-out' \\(known: np\\)"):
        lab.client.create_l3out_loopback(T, "bgp-out", "ghost", 101, "10.9.254.1")


# --- vPC SVI -------------------------------------------------------------------------

def test_vpc_svi_needs_a_vpc_group_and_a_vpc_domain_for_the_pair(lab):
    lab.client.create_l3out_vpc_svi(T, "bgp-out", "np", "ifp", 101, 102, "vpc-ipg", 94, "10.9.2.2/24", "10.9.2.3/24")
    iface = _out(lab)["node_profiles"][0]["interface_profiles"][0]["interfaces"][0]
    assert iface == {"path_type": "vpc", "node_id": 101, "node_id2": 102, "pod_id": 1, "policy_group": "vpc-ipg",
                     "svi": True, "vlan": 94, "side_a_ip": "10.9.2.2/24", "side_b_ip": "10.9.2.3/24"}
    with pytest.raises(NautobotError, match="already has a vPC SVI on nodes 101-102 / 'vpc-ipg'"):
        lab.client.create_l3out_vpc_svi(T, "bgp-out", "np", "ifp", 101, 102, "vpc-ipg", 95, "10.9.3.2/24", "10.9.3.3/24")
    with pytest.raises(NautobotError, match="'pc-ipg' is a port_channel policy group, not vpc"):
        lab.client.create_l3out_vpc_svi(T, "bgp-out", "np", "ifp", 101, 102, "pc-ipg", 94, "10.9.2.2/24", "10.9.2.3/24")
    with pytest.raises(NautobotError, match="no vPC domain pairs nodes 101 and 103"):
        lab.client.create_l3out_vpc_svi(T, "bgp-out", "np", "ifp", 101, 103, "vpc-ipg", 94, "10.9.2.2/24", "10.9.2.3/24")
    lab.client.delete_l3out_vpc_svi(T, "bgp-out", "np", "ifp", 101, 102, "vpc-ipg")
    assert _out(lab)["node_profiles"][0]["interface_profiles"][0]["interfaces"] == []


# --- policy references ----------------------------------------------------------------

def test_bgp_policies_on_an_l3out_need_bgp_and_declared_policies(lab):
    lab.client.create_bgp_timers_policy(T, "t1", keepalive_interval=30, hold_interval=90)
    lab.client.set_l3out_bgp_policies(T, "bgp-out", bgp_timers_policy="t1")
    assert _out(lab)["bgp_timers_policy"] == "t1"
    with pytest.raises(NautobotError, match="BGP best path policy 'ghost' not found in tenant 'ACI:sales' \\(known: none\\)"):
        lab.client.set_l3out_bgp_policies(T, "bgp-out", bgp_best_path_policy="ghost")
    with pytest.raises(NautobotError, match="L3Out 'ospf-out' is not a BGP L3Out"):
        lab.client.set_l3out_bgp_policies(T, "ospf-out", bgp_timers_policy="t1")
    lab.client.set_l3out_bgp_policies(T, "bgp-out", bgp_timers_policy="")
    assert "bgp_timers_policy" not in _out(lab), "an empty string clears the reference"


def test_subnet_summarization_and_its_removal(lab):
    lab.client.create_bgp_route_summarization_policy(T, "sum", as_set=True)
    lab.client.set_external_subnet_route_summarization(T, "bgp-out", "ext", "10.9.0.0/16", "sum")
    subnet = _out(lab)["external_epgs"][0]["subnets"][0]
    assert subnet["bgp_route_summarization_policy"] == "sum"
    with pytest.raises(NautobotError, match="subnet 10.8.0.0/16 not found on external EPG 'ext' \\(known: 10.9.0.0/16\\)"):
        lab.client.set_external_subnet_route_summarization(T, "bgp-out", "ext", "10.8.0.0/16", "sum")
    with pytest.raises(NautobotError, match="still referenced -- subnet 10.9.0.0/16"):
        lab.client.delete_tenant_object(T, "bgp_route_summarization_policy", "sum")
    lab.client.set_external_subnet_route_summarization(T, "bgp-out", "ext", "10.9.0.0/16", "")
    lab.client.delete_tenant_object(T, "bgp_route_summarization_policy", "sum")


def test_update_vrf_protocol_policies(lab):
    lab.client.create_ospf_timers_policy(T, "ot", max_ecmp=8)
    lab.client.update_vrf(T, "prod", ospf_timers_policy="ot")
    assert lab.prod.custom_fields["aci_vrf_protocol_policies"] == {"ospf_timers_policy": "ot"}
    with pytest.raises(NautobotError, match="Route tag policy 'ghost' not found"):
        lab.client.update_vrf(T, "prod", route_tag_policy="ghost")
    with pytest.raises(NautobotError, match="VRF 'prod' uses this as its ospf_timers_policy"):
        lab.client.delete_tenant_object(T, "ospf_timers_policy", "ot")
    lab.client.update_vrf(T, "prod", ospf_timers_policy="")
    assert lab.prod.custom_fields["aci_vrf_protocol_policies"] == {}
    intent = lab.client.get_tenant_intent(T)
    assert "protocol_policies" not in intent["vrfs"][0]


def test_bfd_binding_on_an_interface_profile_and_its_removal(lab):
    lab.client.create_bfd_interface_policy(T, "bfd1")
    lab.client.bind_l3out_interface_profile_policies(T, "bgp-out", "np", "ifp", bfd_interface_policy="bfd1")
    assert _out(lab)["node_profiles"][0]["interface_profiles"][0]["bfd_interface_policy"] == "bfd1"
    lab.client.bind_l3out_interface_profile_policies(T, "bgp-out", "np", "ifp", bfd_interface_policy="")
    assert "bfd_interface_policy" not in _out(lab)["node_profiles"][0]["interface_profiles"][0]
