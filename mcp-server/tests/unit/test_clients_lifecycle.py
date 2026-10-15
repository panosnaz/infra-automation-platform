"""Client-level tests for read / update / delete -- against an in-memory fake
of the pynautobot API, so what is asserted is what would be sent to Nautobot.

Two properties matter most and get their own tests:
  * a refused delete writes NOTHING (the refusal happens before any update or
    delete call), and
  * nested Custom Fields are never mutated in place -- pynautobot diffs a
    record against its cached copy, so in-place mutation silently sends
    nothing (the 2026-09-16 shallow-copy bug).
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
    tenant = api.tenancy.tenants.add(id="t1", name="ACI:sales", custom_fields={
        "aci_contracts": {
            "filters": [{"name": "web-flt"}],
            "contracts": [{"name": "web-ct", "subjects": [{"name": "s", "filters": ["web-flt"]}]},
                          {"name": "old-ct"}, {"name": "old-ct"}],
        },
        "aci_l3outs": {"l3outs": [{"name": "wan", "vrf": "prod",
                                   "route_control_profiles": [{"name": "map1"}],
                                   "external_epgs": [{"name": "any"}]}]},
    })
    t = SimpleNamespace(id="t1")
    prod = api.ipam.vrfs.add(id="v1", name="prod", tenant=t, custom_fields={})
    api.ipam.vrfs.add(id="v2", name="spare", tenant=t, custom_fields={})
    p1 = api.ipam.prefixes.add(id="p1", prefix="10.0.1.0/24", tenant=t,
                               description="ACI Bridge Domain: web-bd:sales -- subnet-scope:public -- web tier",
                               custom_fields={"aci_gateway_ip": "10.0.1.254/24"})
    p2 = api.ipam.prefixes.add(id="p2", prefix="10.0.2.0/24", tenant=t,
                               description="ACI Bridge Domain: web-bd:sales", custom_fields={})
    api.ipam.prefixes.add(id="p3", prefix="10.0.9.0/24", tenant=t,
                          description="ACI Bridge Domain: spare-bd:sales -- no-subnet", custom_fields={})
    for pid in ("p1", "p2"):
        api.ipam.vrf_prefix_assignments.add(vrf=SimpleNamespace(id="v1"), prefix=SimpleNamespace(id=pid))
    api.ipam.vlans.add(id="l1", name="web", vid=10, tenant=t, custom_fields={
        "aci_application_profile": "app", "aci_epg_bridge_domain": "web-bd",
        "aci_epg_contracts": {"provided": ["web-ct"], "consumed": []},
        "aci_epg_domains": {"domains": [{"name": "phys1", "domain_type": "physical"}]},
    })
    loc = api.dcim.locations.add(id="loc1", name="Lab", custom_fields={"aci_fabric_policies": {
        "vlan_pools": [{"name": "pool1"}, {"name": "pool2"}],
        "physical_domains": [{"name": "phys1", "vlan_pool": "pool1"}],
    }})
    return SimpleNamespace(api=api, client=client, tenant=tenant, prod=prod, p1=p1, p2=p2, loc=loc)


# --- read ---------------------------------------------------------------------

def test_get_tenant_intent_groups_a_multi_subnet_bd_into_one(lab):
    intent = lab.client.get_tenant_intent("ACI:sales")
    bds = {bd["name"]: bd for bd in intent["bridge_domains"]}
    assert set(bds) == {"web-bd", "spare-bd"}
    assert [s["prefix"] for s in bds["web-bd"]["subnets"]] == ["10.0.1.0/24", "10.0.2.0/24"]
    assert bds["web-bd"]["subnets"][0]["scope"] == "public"
    assert bds["web-bd"]["vrfs"] == ["prod"]
    assert bds["spare-bd"]["subnets"] == []  # no-subnet BD
    assert intent["application_profiles"][0]["epgs"][0]["name"] == "web"


def test_list_aci_tenants_counts(lab):
    [summary] = lab.client.list_aci_tenants()
    assert (summary["vrfs"], summary["bridge_domains"], summary["epgs"]) == (2, 2, 1)
    assert summary["json_intent"]["aci_contracts"] == {"filters": 1, "contracts": 3}
    assert summary["system_tenant"] is False


# --- update -------------------------------------------------------------------

def test_update_bd_applies_to_every_subnet_and_drops_the_old_scope_marker(lab):
    lab.client.update_bridge_domain("ACI:sales", "web-bd", subnet_scope="private", arp_flooding=True)

    for prefix in (lab.p1, lab.p2):
        assert prefix.custom_fields["aci_bd_arp_flooding"] is True
        assert prefix.custom_fields["aci_bd_subnet_scope"] == ""
        assert "subnet-scope" not in prefix.description, "the marker would keep the BD public"
    # user text and the gateway survive
    assert lab.p1.description == "ACI Bridge Domain: web-bd:sales -- web tier"
    assert lab.p1.custom_fields["aci_gateway_ip"] == "10.0.1.254/24"


def test_update_bd_without_a_scope_keeps_the_marker(lab):
    lab.client.update_bridge_domain("ACI:sales", "web-bd", description="new text")
    assert lab.p1.description == "ACI Bridge Domain: web-bd:sales -- subnet-scope:public -- new text"


def test_update_bd_refuses_an_undeclared_l3out(lab):
    with pytest.raises(NautobotError, match="do not exist"):
        lab.client.update_bridge_domain("ACI:sales", "web-bd", l3outs=["nope"])
    assert lab.p1.updates == []


def test_update_bd_names_the_known_bds_when_not_found(lab):
    with pytest.raises(NautobotError, match="spare-bd, web-bd"):
        lab.client.update_bridge_domain("ACI:sales", "missing", pim=True)


def test_update_vrf_writes_the_declared_custom_field_names(lab):
    lab.client.update_vrf("ACI:sales", "prod", ip_data_plane_learning=False,
                          policy_control_enforcement_mode="unenforced")
    assert lab.prod.custom_fields == {
        "aci_ip_data_plane_learning": False,
        "aci_policy_control_enforcement_mode": "unenforced",
    }


def test_update_epg_refuses_a_bridge_domain_that_does_not_exist(lab):
    with pytest.raises(NautobotError, match="does not exist"):
        lab.client.update_epg("ACI:sales", "app", "web", bridge_domain="nope")


def test_update_epg_moves_it(lab):
    lab.client.update_epg("ACI:sales", "app", "web", bridge_domain="spare-bd")
    vlan = lab.api.ipam.vlans.get(name="web")
    assert vlan.custom_fields["aci_epg_bridge_domain"] == "spare-bd"
    assert vlan.custom_fields["aci_epg_contracts"] == {"provided": ["web-ct"], "consumed": []}


# --- delete -------------------------------------------------------------------

def test_a_referenced_contract_is_refused_and_nothing_is_written(lab):
    with pytest.raises(NautobotError, match="EPG 'web' provides"):
        lab.client.delete_tenant_object("ACI:sales", "contract", "web-ct")
    assert lab.tenant.updates == []


def test_an_unreferenced_contract_is_removed_with_its_duplicates(lab):
    result = lab.client.delete_tenant_object("ACI:sales", "contract", "old-ct")
    assert result["removed"] == 2
    written = lab.tenant.updates[-1]["custom_fields"]["aci_contracts"]["contracts"]
    assert [c["name"] for c in written] == ["web-ct"]
    # the rest of the tenant's intent is preserved
    assert lab.tenant.custom_fields["aci_l3outs"]["l3outs"][0]["name"] == "wan"


def test_deleting_something_absent_names_what_exists(lab):
    with pytest.raises(NautobotError, match="known: old-ct, old-ct, web-ct"):
        lab.client.delete_tenant_object("ACI:sales", "contract", "ghost")


def test_a_vrf_with_bridge_domains_is_refused(lab):
    with pytest.raises(NautobotError, match="bridge domain 'web-bd' is in this VRF"):
        lab.client.delete_tenant_object("ACI:sales", "vrf", "prod")
    assert lab.prod.deleted is False


def test_an_empty_vrf_is_deleted(lab):
    lab.client.delete_tenant_object("ACI:sales", "vrf", "spare")
    assert lab.api.ipam.vrfs.get(name="spare") is None


def test_a_bd_in_use_by_an_epg_is_refused(lab):
    with pytest.raises(NautobotError, match="EPG 'web'"):
        lab.client.delete_tenant_object("ACI:sales", "bridge_domain", "web-bd")
    assert not lab.p1.deleted and not lab.p2.deleted


def test_deleting_a_bd_deletes_every_one_of_its_prefixes(lab):
    lab.client.update_epg("ACI:sales", "app", "web", bridge_domain="spare-bd")
    result = lab.client.delete_tenant_object("ACI:sales", "bridge_domain", "web-bd")
    assert sorted(result["prefixes_deleted"]) == ["10.0.1.0/24", "10.0.2.0/24"]
    assert lab.p1.deleted and lab.p2.deleted


def test_deleting_a_route_map_edits_only_its_l3out(lab):
    lab.client.delete_tenant_object("ACI:sales", "route_control_profile", "map1", l3out="wan")
    out = lab.tenant.custom_fields["aci_l3outs"]["l3outs"][0]
    assert out["route_control_profiles"] == []
    assert out["external_epgs"] == [{"name": "any"}]


def test_a_domain_bound_by_an_epg_in_any_tenant_is_refused(lab):
    with pytest.raises(NautobotError, match="EPG 'web' in tenant 'ACI:sales'"):
        lab.client.delete_fabric_object("physical_domain", "phys1", location="Lab")
    assert lab.loc.updates == []


def test_a_vlan_pool_used_by_a_domain_is_refused_but_an_unused_one_goes(lab):
    with pytest.raises(NautobotError, match="physical domain 'phys1'"):
        lab.client.delete_fabric_object("vlan_pool", "pool1", location="Lab")
    lab.client.delete_fabric_object("vlan_pool", "pool2", location="Lab")
    pools = lab.loc.custom_fields["aci_fabric_policies"]["vlan_pools"]
    assert [p["name"] for p in pools] == ["pool1"]


def test_unbind_epg_contract(lab):
    lab.client.unbind_epg_contract("ACI:sales", "app", "web", "web-ct", "provided")
    assert lab.api.ipam.vlans.get(name="web").custom_fields["aci_epg_contracts"]["provided"] == []
    with pytest.raises(NautobotError, match="does not have contract"):
        lab.client.unbind_epg_contract("ACI:sales", "app", "web", "web-ct", "provided")


def test_unbind_epg_domain_matches_name_and_type(lab):
    with pytest.raises(NautobotError, match="not bound"):
        lab.client.unbind_epg_domain("ACI:sales", "app", "web", "phys1", "vmm")
    lab.client.unbind_epg_domain("ACI:sales", "app", "web", "phys1", "physical")
    assert lab.api.ipam.vlans.get(name="web").custom_fields["aci_epg_domains"]["domains"] == []


def test_delete_tenant_removes_children_then_the_tenant(lab):
    result = lab.client.delete_tenant("ACI:sales")
    assert result["deleted"] == {"epgs_and_vlans": 1, "prefixes": 3, "vrfs": 2}
    assert lab.api.tenancy.tenants.all() == []
    assert "DESTROY" in result["deploy"]


def test_delete_tenant_refuses_when_it_owns_devices_and_deletes_nothing(lab):
    lab.api.dcim.devices.add(name="leaf101", tenant=SimpleNamespace(id="t1"))
    with pytest.raises(NautobotError, match="device 'leaf101'"):
        lab.client.delete_tenant("ACI:sales")
    assert len(lab.api.ipam.vrfs.all()) == 2


def test_the_client_itself_refuses_system_tenants(lab):
    """Not only the schema: any other caller of the client is stopped too."""
    with pytest.raises(NautobotError, match="system tenant"):
        lab.client.delete_tenant("ACI:common")


def test_get_fabric_intent_lists_the_fabric_nodes_at_the_location(lab):
    lab.api.dcim.devices.add(id="d101", name="leaf101", location=SimpleNamespace(id="loc1"), serial="S1",
                             role=SimpleNamespace(name="leaf"), custom_fields={"aci_node_id": 101, "aci_pod_id": 1})
    lab.api.dcim.devices.add(id="dx", name="not-aci", location=SimpleNamespace(id="loc1"), serial="", custom_fields={})
    lab.client._get_location_or_raise = lambda name=None: lab.loc
    intent = lab.client.get_fabric_intent()
    assert intent["location"] == "Lab"
    assert intent["fabric_nodes"] == [{"name": "leaf101", "role": "leaf", "node_id": 101, "pod_id": 1,
                                       "serial": "S1", "management": []}]
    assert [p["name"] for p in intent["fabric_policies"]["vlan_pools"]] == ["pool1", "pool2"]


def test_delete_tenant_removes_its_own_empty_namespace(lab):
    lab.api.ipam.namespaces.add(id="ns1", name="ACI:sales")
    result = lab.client.delete_tenant("ACI:sales")
    assert result["namespace_deleted"] is True
    assert lab.api.ipam.namespaces.get(name="ACI:sales") is None


def test_delete_tenant_keeps_a_namespace_something_else_still_uses(lab):
    ns = lab.api.ipam.namespaces.add(id="ns1", name="ACI:sales")
    lab.api.ipam.prefixes.add(prefix="192.0.2.0/24", namespace=SimpleNamespace(id=ns.id), tenant=None)
    result = lab.client.delete_tenant("ACI:sales")
    assert result["namespace_deleted"] is False
    assert lab.api.ipam.namespaces.get(name="ACI:sales") is ns
