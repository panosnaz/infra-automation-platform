"""Client tests for Endpoint Security Groups and vzAny (2026-10-15), against
the strict in-memory fake of the pynautobot API."""
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
    tenant = api.tenancy.tenants.add(id="t1", name=T, custom_fields={
        "aci_contracts": {"contracts": [{"name": "web-ct"}, {"name": "db-ct"}]},
    })
    t = SimpleNamespace(id="t1")
    prod = api.ipam.vrfs.add(id="v1", name="prod", tenant=t, custom_fields={})
    api.ipam.vrfs.add(id="v2", name="dev", tenant=t, custom_fields={})
    api.ipam.prefixes.add(id="p1", prefix="10.0.1.0/24", tenant=t,
                          description="ACI Bridge Domain: web-bd:sales", custom_fields={})
    api.ipam.prefixes.add(id="p2", prefix="10.0.2.0/24", tenant=t,
                          description="ACI Bridge Domain: dev-bd:sales", custom_fields={})
    api.ipam.vrf_prefix_assignments.add(vrf=SimpleNamespace(id="v1"), prefix=SimpleNamespace(id="p1"))
    api.ipam.vrf_prefix_assignments.add(vrf=SimpleNamespace(id="v2"), prefix=SimpleNamespace(id="p2"))
    api.ipam.vlans.add(id="l1", name="web", vid=10, tenant=t, custom_fields={
        "aci_application_profile": "app", "aci_epg_bridge_domain": "web-bd"})
    api.ipam.vlans.add(id="l2", name="dev-web", vid=20, tenant=t, custom_fields={
        "aci_application_profile": "app", "aci_epg_bridge_domain": "dev-bd"})
    return SimpleNamespace(api=api, client=client, tenant=tenant, prod=prod)


def _esgs(lab):
    return lab.tenant.custom_fields["aci_endpoint_security_groups"]["esgs"]


def _esg(lab, client=None):
    (client or lab.client).create_esg(T, "app", "web-esg", "prod")


# --- ESG -----------------------------------------------------------------------

def test_create_esg_stores_only_what_was_set_and_needs_a_known_vrf(lab):
    result = lab.client.create_esg(T, "app", "web-esg", "prod", description="web tier", intra_esg_isolation=True)
    assert _esgs(lab) == [{"name": "web-esg", "application_profile": "app", "vrf": "prod",
                           "description": "web tier", "intra_esg_isolation": True}]
    assert "tenant webhook" in result["deploy"]
    with pytest.raises(NautobotError, match="VRF 'nope' not found in tenant 'ACI:sales' \\(known: dev, prod\\)"):
        lab.client.create_esg(T, "app", "x-esg", "nope")


def test_esg_names_are_unique_in_the_tenant(lab):
    _esg(lab)
    with pytest.raises(NautobotError, match="ESG 'web-esg' already exists .*application profile 'app'"):
        lab.client.create_esg(T, "other-ap", "web-esg", "prod")


def test_update_esg_changes_only_what_is_passed(lab):
    _esg(lab)
    lab.client.update_esg(T, "web-esg", shutdown=True)
    lab.client.update_esg(T, "web-esg", preferred_group_member=False)
    assert _esgs(lab)[0] == {"name": "web-esg", "application_profile": "app", "vrf": "prod",
                             "shutdown": True, "preferred_group_member": False}
    with pytest.raises(NautobotError, match="ESG 'ghost' not found .*known: web-esg"):
        lab.client.update_esg(T, "ghost", shutdown=True)


# --- selectors -------------------------------------------------------------------

def test_epg_selector_needs_the_epg_in_the_esgs_vrf(lab):
    _esg(lab)
    lab.client.create_esg_epg_selector(T, "web-esg", "app", "web")
    assert _esgs(lab)[0]["epg_selectors"] == [{"application_profile": "app", "endpoint_group": "web"}]
    with pytest.raises(NautobotError, match="EPG 'dev-web' is in VRF 'dev'.*ESG 'web-esg' is in VRF 'prod'"):
        lab.client.create_esg_epg_selector(T, "web-esg", "app", "dev-web")
    with pytest.raises(NautobotError, match="EPG 'ghost' not found"):
        lab.client.create_esg_epg_selector(T, "web-esg", "app", "ghost")


def test_an_epg_can_be_selected_by_only_one_esg(lab):
    _esg(lab)
    lab.client.create_esg(T, "app", "other-esg", "prod")
    lab.client.create_esg_epg_selector(T, "web-esg", "app", "web")
    with pytest.raises(NautobotError, match="already selected by ESG 'web-esg'"):
        lab.client.create_esg_epg_selector(T, "other-esg", "app", "web")


def test_an_ip_subnet_can_be_in_only_one_esg_per_vrf(lab):
    _esg(lab)
    lab.client.create_esg(T, "app", "other-esg", "prod")
    lab.client.create_esg(T, "app", "dev-esg", "dev")
    lab.client.create_esg_ip_subnet_selector(T, "web-esg", "10.0.1.0/24")
    with pytest.raises(NautobotError, match="already selected by ESG 'web-esg' in VRF 'prod'"):
        lab.client.create_esg_ip_subnet_selector(T, "other-esg", "10.0.1.0/24")
    lab.client.create_esg_ip_subnet_selector(T, "dev-esg", "10.0.1.0/24")  # another VRF: allowed
    assert _esgs(lab)[0]["ip_subnet_selectors"] == [{"value": "10.0.1.0/24"}]


def test_tag_selectors_and_duplicates(lab):
    _esg(lab)
    lab.client.create_esg_tag_selector(T, "web-esg", "app", "web", "equals")
    with pytest.raises(NautobotError, match="already has a tag selector app=web"):
        lab.client.create_esg_tag_selector(T, "web-esg", "app", "web", "regex")
    assert _esgs(lab)[0]["tag_selectors"] == [{"key": "app", "value": "web", "operator": "equals"}]


def test_delete_selector_removes_exactly_one_and_leaves_no_residue(lab):
    _esg(lab)
    lab.client.create_esg_ip_subnet_selector(T, "web-esg", "10.0.1.0/24")
    lab.client.create_esg_tag_selector(T, "web-esg", "app", "web")
    lab.client.delete_esg_selector(T, "web-esg", "ip_subnet", subnet="10.0.1.0/24")
    assert "ip_subnet_selectors" not in _esgs(lab)[0]
    with pytest.raises(NautobotError, match="has no ip_subnet selector 10.0.1.0/24"):
        lab.client.delete_esg_selector(T, "web-esg", "ip_subnet", subnet="10.0.1.0/24")
    lab.client.delete_esg_selector(T, "web-esg", "tag", key="app", value="web")
    assert set(_esgs(lab)[0]) == {"name", "application_profile", "vrf"}


# --- contracts ---------------------------------------------------------------------

def test_esg_contracts_need_a_known_contract(lab):
    _esg(lab)
    lab.client.bind_esg_contract(T, "web-esg", "web-ct", "provided")
    with pytest.raises(NautobotError, match="already provides 'web-ct'"):
        lab.client.bind_esg_contract(T, "web-esg", "web-ct", "provided")
    with pytest.raises(NautobotError, match="Contract 'ghost' not found in tenant 'ACI:sales' \\(known: db-ct, web-ct\\)"):
        lab.client.bind_esg_contract(T, "web-esg", "ghost", "consumed")
    assert _esgs(lab)[0]["provided_contracts"] == ["web-ct"]
    lab.client.unbind_esg_contract(T, "web-esg", "web-ct", "provided")
    assert "provided_contracts" not in _esgs(lab)[0]
    with pytest.raises(NautobotError, match="does not provide 'web-ct'"):
        lab.client.unbind_esg_contract(T, "web-esg", "web-ct", "provided")


def test_vzany_contracts_live_on_the_vrf(lab):
    result = lab.client.bind_vzany_contract(T, "prod", "db-ct", "consumed")
    assert lab.prod.custom_fields["aci_vzany_contracts"] == {"consumed": ["db-ct"]}
    assert "EVERY EPG and ESG" in result["note"]
    assert "does NOT fire the tenant webhook" in result["deploy"]
    with pytest.raises(NautobotError, match="already consumes 'db-ct'"):
        lab.client.bind_vzany_contract(T, "prod", "db-ct", "consumed")
    lab.client.unbind_vzany_contract(T, "prod", "db-ct", "consumed")
    assert lab.prod.custom_fields["aci_vzany_contracts"] == {}


# --- deletes guarded by the new references ------------------------------------------

def test_deletes_refuse_while_an_esg_or_vzany_uses_the_object(lab):
    _esg(lab)
    lab.client.create_esg_epg_selector(T, "web-esg", "app", "web")
    lab.client.bind_vzany_contract(T, "prod", "web-ct", "provided")
    with pytest.raises(NautobotError, match="ESG 'web-esg' selects this EPG"):
        lab.client.delete_tenant_object(T, "epg", "web", application_profile="app")
    with pytest.raises(NautobotError, match="vzAny of VRF 'prod' provides this contract"):
        lab.client.delete_tenant_object(T, "contract", "web-ct")
    with pytest.raises(NautobotError, match="ESG 'web-esg' is in this VRF"):
        lab.client.delete_tenant_object(T, "vrf", "prod")
    lab.client.delete_tenant_object(T, "esg", "web-esg")
    assert lab.tenant.custom_fields.get("aci_endpoint_security_groups") in (None, {})


def test_update_vrf_sets_the_preferred_group(lab):
    lab.client.update_vrf(T, "prod", preferred_group=True)
    assert lab.prod.custom_fields["aci_vrf_preferred_group"] is True
    intent = lab.client.get_tenant_intent(T)
    assert next(v for v in intent["vrfs"] if v["name"] == "prod")["preferred_group"] is True


def test_a_tag_selector_can_be_in_only_one_esg_per_vrf(lab):
    """APIC 6.2 rejects the second with HTTP 400 ("Property (key,value)
    duplicate ... in VRF") -- probed 2026-10-15."""
    _esg(lab)
    lab.client.create_esg(T, "app", "other-esg", "prod")
    lab.client.create_esg(T, "app", "dev-esg", "dev")
    lab.client.create_esg_tag_selector(T, "web-esg", "app", "web")
    with pytest.raises(NautobotError, match="tag selector app=web is already in ESG 'web-esg' in VRF 'prod'"):
        lab.client.create_esg_tag_selector(T, "other-esg", "app", "web")
    lab.client.create_esg_tag_selector(T, "dev-esg", "app", "web")  # another VRF: allowed


def test_vzany_can_provide_only_vrf_scoped_contracts(lab):
    """APIC 6.2 answers HTTP 400 "vzAny cannot be used as provider for this
    contract" unless the contract's scope is context (VRF); consuming works for
    any scope -- probed 2026-10-15. An unset scope is APIC's default, context."""
    lab.client.create_contract(T, "wide-ct", "wide-flt", scope="tenant")
    with pytest.raises(NautobotError, match="vzAny can only provide a contract whose scope is 'context'.*'wide-ct' is 'tenant'"):
        lab.client.bind_vzany_contract(T, "prod", "wide-ct", "provided")
    lab.client.bind_vzany_contract(T, "prod", "wide-ct", "consumed")
    lab.client.bind_vzany_contract(T, "prod", "web-ct", "provided")  # no scope set: APIC default context
