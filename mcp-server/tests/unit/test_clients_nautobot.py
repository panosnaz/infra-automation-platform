"""Client-level tests for the payloads NautobotClient actually writes.

The tool-dispatch tests in test_tools_aci.py stop at the client boundary --
they assert the right keyword arguments arrive. That leaves the shape of the
JSON Custom Field itself untested, and that shape is what Terraform reads. A
key that is present-but-null and a key that is absent are different things to
the generator, so they get a test.
"""
from __future__ import annotations

import pytest

from mcp_server.clients.nautobot import NautobotClient, NautobotError


class _FakeLocation:
    def __init__(self, custom_fields: dict | None = None, name: str = "Isolated Lab Site"):
        # `name` matters: every location-scoped client method now reports the
        # RESOLVED Location back, so a caller who let it auto-resolve can see
        # where the write landed instead of "Location 'None'".
        self.name = name
        self.custom_fields = custom_fields or {}
        self.updates: list[dict] = []

    def update(self, payload: dict) -> bool:
        self.updates.append(payload)
        return True


@pytest.fixture
def client_and_location(monkeypatch):
    client = NautobotClient.__new__(NautobotClient)  # no HTTP session needed
    location = _FakeLocation()
    monkeypatch.setattr(
        NautobotClient, "_get_location_or_raise", lambda self, name: location
    )
    return client, location


def _written_domain(location: _FakeLocation) -> dict:
    payload = location.updates[-1]["custom_fields"]["aci_fabric_policies"]
    return payload["vmm_domains"][-1]


def test_vmm_domain_without_a_controller_omits_the_controller_key(client_and_location):
    """Not `"controller": null` -- the key must be ABSENT. main.tf builds
    aci_vmm_controller only for domains carrying this key, so emitting it
    with a null value would make Terraform reach toward a vCenter that was
    deliberately not configured. This is what lets an L4-L7 VIRTUAL device
    appear in APIC with no vCenter at all (live-verified 2026-09-15).
    """
    client, location = client_and_location

    client.create_vmm_domain(
        location="ACI-Lab", name="vCenter_VMM", vlan_pool="vCenter_VMM_Pool"
    )

    domain = _written_domain(location)
    assert "controller" not in domain
    assert "credential" not in domain
    assert domain == {
        "name": "vCenter_VMM",
        "vendor": "VMware",
        "vlan_pool": "vCenter_VMM_Pool",
    }


def test_vmm_domain_with_a_controller_still_emits_it(client_and_location):
    """The positive case, so the omission above cannot be satisfied by a
    client that simply never writes a controller."""
    client, location = client_and_location

    client.create_vmm_domain(
        location="ACI-Lab",
        name="vCenter_VMM",
        controller_name="vCenter",
        host_or_ip="192.168.10.62",
        root_cont_name="DC",
        credential_name="vc-cred",
    )

    domain = _written_domain(location)
    assert domain["controller"] == {
        "name": "vCenter",
        "host_or_ip": "192.168.10.62",
        "root_cont_name": "DC",
        "dvs_version": "unmanaged",
    }
    assert domain["credential"] == {"name": "vc-cred"}


def test_a_second_vmm_domain_does_not_drop_the_first(client_and_location):
    """aci_fabric_policies is a single JSON blob holding a list; each write
    is a read-modify-write of that whole list. Appending must preserve what
    is already there."""
    client, location = client_and_location
    location.custom_fields = {
        "aci_fabric_policies": {"vmm_domains": [{"name": "existing", "vendor": "VMware"}]}
    }

    client.create_vmm_domain(location="ACI-Lab", name="vCenter_VMM")

    written = location.updates[-1]["custom_fields"]["aci_fabric_policies"]["vmm_domains"]
    assert [d["name"] for d in written] == ["existing", "vCenter_VMM"]


# ---------------------------------------------------------------------------
# Concrete devices (2026-09-15).
#
# create_concrete_device is the only create_* that EDITS an existing entry
# rather than appending a new one, because a concrete device has no meaning
# apart from its parent. The LIf-to-CIf binding it writes is the part that
# actually clears APIC's "LIf has no relation to CIf" fault, so it is tested
# directly rather than inferred from the dispatch test.
# ---------------------------------------------------------------------------

class _FakeTenant:
    def __init__(self, custom_fields=None, name="ACI:acme"):
        self.name = name
        self.custom_fields = custom_fields or {}
        self.updates = []

    def update(self, payload):
        self.updates.append(payload)
        self.custom_fields = payload.get("custom_fields", self.custom_fields)
        return True


def _tenant_with_device(**device_overrides):
    device = {
        "name": "FW",
        "device_type": "VIRTUAL",
        "logical_interfaces": [{"name": "db_int"}, {"name": "backup_int"}],
    }
    device.update(device_overrides)
    return _FakeTenant({"aci_l4l7_services": {"devices": [device]}})


@pytest.fixture
def client_and_tenant(monkeypatch):
    client = NautobotClient.__new__(NautobotClient)
    holder = {}

    def _set(tenant):
        holder["tenant"] = tenant
        return tenant

    monkeypatch.setattr(
        NautobotClient, "_get_tenant_or_raise", lambda self, name: holder["tenant"]
    )
    return client, _set


_VIRTUAL_IFACES = [
    {"name": "cif1", "logical_interface": "db_int", "vnic_name": "Network adapter 2"},
    {"name": "cif2", "logical_interface": "backup_int", "vnic_name": "Network adapter 3"},
]


def _written_device(tenant):
    return tenant.updates[-1]["custom_fields"]["aci_l4l7_services"]["devices"][0]


def test_concrete_device_binds_each_logical_interface_to_its_concrete_one(client_and_tenant):
    """This binding is the whole point: without relation_vns_rs_c_if_att_n the
    device stays invalid however complete the rest of the graph looks."""
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_tenant_with_device())

    client.create_concrete_device(
        tenant="ACI:acme", device="FW", name="ASAv_cdev", interfaces=_VIRTUAL_IFACES,
        vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
    )

    device = _written_device(tenant)
    by_name = {li["name"]: li for li in device["logical_interfaces"]}
    assert by_name["db_int"]["concrete_interfaces"] == ["ASAv_cdev/cif1"]
    assert by_name["backup_int"]["concrete_interfaces"] == ["ASAv_cdev/cif2"]


def test_virtual_concrete_device_builds_the_controller_dn(client_and_tenant):
    """vnsRsCIfAttN resolves the VM's vNICs through this DN. Getting its shape
    wrong is silent -- APIC just never resolves the VM."""
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_tenant_with_device())

    client.create_concrete_device(
        tenant="ACI:acme", device="FW", name="ASAv_cdev", interfaces=_VIRTUAL_IFACES,
        vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
    )

    cdev = _written_device(tenant)["concrete_devices"][0]
    assert cdev["vm_name"] == "ASAv-1"
    assert cdev["vmm_controller_dn"] == "uni/vmmp-VMware/dom-vCenter_VMM/ctrlr-vCenter"
    assert [i["vnic_name"] for i in cdev["interfaces"]] == ["Network adapter 2", "Network adapter 3"]
    assert "node_id" not in cdev["interfaces"][0]


def test_physical_concrete_device_writes_path_fields_not_a_controller(client_and_tenant):
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_tenant_with_device(
        device_type="PHYSICAL", logical_interfaces=[{"name": "consumer"}]
    ))

    client.create_concrete_device(
        tenant="ACI:acme", device="FW", name="fw1", device_type="PHYSICAL",
        interfaces=[{"name": "eth1", "logical_interface": "consumer",
                     "node_id": 101, "pod_id": 1, "module": 1, "port": 30}],
    )

    cdev = _written_device(tenant)["concrete_devices"][0]
    assert "vmm_controller_dn" not in cdev
    assert "vm_name" not in cdev
    assert cdev["interfaces"][0] == {"name": "eth1", "node_id": 101, "pod_id": 1,
                                     "module": 1, "port": 30}


def test_concrete_device_on_a_missing_parent_is_refused(client_and_tenant):
    """Writing it anyway would produce orphaned intent no generator reads --
    the same silent-no-op shape as finding F-01."""
    client, set_tenant = client_and_tenant
    set_tenant(_tenant_with_device(name="OtherFW"))

    with pytest.raises(NautobotError, match="does not exist in tenant"):
        client.create_concrete_device(
            tenant="ACI:acme", device="FW", name="ASAv_cdev", interfaces=_VIRTUAL_IFACES,
            vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
        )


def test_concrete_interface_bound_to_an_unknown_logical_interface_is_refused(client_and_tenant):
    client, set_tenant = client_and_tenant
    set_tenant(_tenant_with_device(logical_interfaces=[{"name": "db_int"}]))

    with pytest.raises(NautobotError, match="has no logical interface"):
        client.create_concrete_device(
            tenant="ACI:acme", device="FW", name="ASAv_cdev", interfaces=_VIRTUAL_IFACES,
            vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
        )


def test_duplicate_concrete_device_is_refused(client_and_tenant):
    client, set_tenant = client_and_tenant
    set_tenant(_tenant_with_device(concrete_devices=[{"name": "ASAv_cdev"}]))

    with pytest.raises(NautobotError, match="already exists"):
        client.create_concrete_device(
            tenant="ACI:acme", device="FW", name="ASAv_cdev", interfaces=_VIRTUAL_IFACES,
            vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
        )


def test_a_second_concrete_device_does_not_drop_the_first_binding(client_and_tenant):
    """An HA pair: two concrete devices fronted by the same logical interface.
    The second must append to concrete_interfaces, not replace it."""
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_tenant_with_device(
        concrete_devices=[{"name": "ASAv_a"}],
        logical_interfaces=[{"name": "db_int", "concrete_interfaces": ["ASAv_a/cif1"]}],
    ))

    client.create_concrete_device(
        tenant="ACI:acme", device="FW", name="ASAv_b",
        interfaces=[{"name": "cif1", "logical_interface": "db_int", "vnic_name": "Network adapter 2"}],
        vm_name="ASAv-2", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
    )

    device = _written_device(tenant)
    assert device["logical_interfaces"][0]["concrete_interfaces"] == ["ASAv_a/cif1", "ASAv_b/cif1"]
    assert [c["name"] for c in device["concrete_devices"]] == ["ASAv_a", "ASAv_b"]


# ---------------------------------------------------------------------------
# L3Out interface policies (2026-09-16).
#
# All five kinds share ONE Custom Field keyed by kind, so the read-modify-write
# has to preserve sibling kinds. The binding method edits an existing profile
# nested three levels down inside aci_l3outs, so it also has to refuse every
# level that might not exist.
# ---------------------------------------------------------------------------

def _written_policies(tenant):
    return tenant.updates[-1]["custom_fields"]["aci_interface_policies"]


def test_policy_write_drops_unset_attributes(client_and_tenant):
    """An omitted attribute must mean "let APIC default it", not "write null".
    A null would reach the generator and then Terraform as an explicit value."""
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_FakeTenant())

    client.create_nd_interface_policy(
        tenant="ACI:acme", name="ND_Pol", hop_limit=64, mtu=None, description=""
    )

    entry = _written_policies(tenant)["nd_interface_policies"][0]
    assert entry == {"name": "ND_Pol", "hop_limit": 64}


def test_each_policy_kind_lands_under_its_own_key(client_and_tenant):
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_FakeTenant())

    client.create_nd_interface_policy(tenant="ACI:acme", name="ND")
    client.create_dpp_policy(tenant="ACI:acme", name="DPP", rate=100, rate_unit="mega")
    client.create_pim_interface_policy(tenant="ACI:acme", name="PIM")
    client.create_igmp_interface_policy(tenant="ACI:acme", name="IGMP")
    client.create_custom_qos_policy(
        tenant="ACI:acme", name="CQ", dscp_to_priority_maps=[{"from": "EF"}]
    )

    written = _written_policies(tenant)
    assert [k for k in written] == [
        "nd_interface_policies", "dpp_policies", "pim_interface_policies",
        "igmp_interface_policies", "custom_qos_policies",
    ]
    assert written["dpp_policies"][0]["rate_unit"] == "mega"
    assert written["custom_qos_policies"][0]["dscp_to_priority_maps"] == [{"from": "EF"}]


def test_a_duplicate_policy_name_is_refused(client_and_tenant):
    client, set_tenant = client_and_tenant
    set_tenant(_FakeTenant({"aci_interface_policies": {"nd_interface_policies": [{"name": "ND"}]}}))

    with pytest.raises(NautobotError, match="already exists"):
        client.create_nd_interface_policy(tenant="ACI:acme", name="ND")


def _tenant_with_l3out():
    return _FakeTenant({"aci_l3outs": {"l3outs": [{
        "name": "Edge",
        "node_profiles": [{"name": "NP1", "interface_profiles": [{"name": "IP1"}]}],
    }]}})


def _written_profile(tenant):
    l3outs = tenant.updates[-1]["custom_fields"]["aci_l3outs"]["l3outs"]
    return l3outs[0]["node_profiles"][0]["interface_profiles"][0]


def test_binding_policies_updates_the_profile_in_place(client_and_tenant):
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_tenant_with_l3out())

    client.bind_l3out_interface_profile_policies(
        tenant="ACI:acme", l3out="Edge", node_profile="NP1", interface_profile="IP1",
        nd_interface_policy="ND_Pol", qos_priority="level3",
    )

    profile = _written_profile(tenant)
    assert profile["name"] == "IP1"
    assert profile["nd_interface_policy"] == "ND_Pol"
    assert profile["qos_priority"] == "level3"


def test_binding_again_does_not_drop_earlier_bindings(client_and_tenant):
    """Day-2 operation: adding a policer later must not clear the ND policy
    bound last week."""
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_FakeTenant({"aci_l3outs": {"l3outs": [{
        "name": "Edge",
        "node_profiles": [{"name": "NP1", "interface_profiles": [
            {"name": "IP1", "nd_interface_policy": "ND_Pol"}
        ]}],
    }]}}))

    client.bind_l3out_interface_profile_policies(
        tenant="ACI:acme", l3out="Edge", node_profile="NP1", interface_profile="IP1",
        ingress_dpp_policy="In_100M",
    )

    profile = _written_profile(tenant)
    assert profile["nd_interface_policy"] == "ND_Pol"
    assert profile["ingress_dpp_policy"] == "In_100M"


@pytest.mark.parametrize(
    "kwargs,expected",
    [({"l3out": "Nope"}, "L3Out 'Nope' does not exist"),
     ({"node_profile": "Nope"}, "Node profile 'Nope' does not exist"),
     ({"interface_profile": "Nope"}, "Interface profile 'Nope' does not exist")],
)
def test_binding_to_something_that_does_not_exist_is_refused(client_and_tenant, kwargs, expected):
    """Three levels of nesting, three ways to write intent nothing reads."""
    client, set_tenant = client_and_tenant
    set_tenant(_tenant_with_l3out())
    call = {"tenant": "ACI:acme", "l3out": "Edge", "node_profile": "NP1",
            "interface_profile": "IP1", "nd_interface_policy": "ND_Pol"}
    call.update(kwargs)

    with pytest.raises(NautobotError, match=expected):
        client.bind_l3out_interface_profile_policies(**call)


# ---------------------------------------------------------------------------
# Route control (2026-09-16).
#
# Match rules are tenant-scoped and live in their own Custom Field. Route maps
# hang off an L3Out, so they are written INTO aci_l3outs -- which makes them
# subject to the same pynautobot shallow-copy trap that made
# create_l3out_node_profile silently write nothing.
# ---------------------------------------------------------------------------

def _tenant_with_l3out_and_epg():
    return _FakeTenant({"aci_l3outs": {"l3outs": [{
        "name": "OSPF_L3Out",
        "external_epgs": [{"name": "Cat_ExtNet", "subnets": [
            {"ip": "172.16.200.200/32", "scope": ["export-rtctrl"]},
        ]}],
    }]}})


def _written_l3out(tenant):
    return tenant.updates[-1]["custom_fields"]["aci_l3outs"]["l3outs"][0]


def test_match_rule_lands_in_its_own_custom_field(client_and_tenant):
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_FakeTenant())

    client.create_match_rule(
        tenant="ACI:acme", name="match-permit-prefix-out",
        prefixes=[{"ip": "172.16.200.200/32", "aggregate": False}],
        description="permit the Nexus loopback",
    )

    rules = tenant.updates[-1]["custom_fields"]["aci_route_control"]["match_rules"]
    assert rules[0]["name"] == "match-permit-prefix-out"
    assert rules[0]["prefixes"][0]["ip"] == "172.16.200.200/32"


def test_duplicate_match_rule_is_refused(client_and_tenant):
    client, set_tenant = client_and_tenant
    set_tenant(_FakeTenant({"aci_route_control": {"match_rules": [{"name": "r1"}]}}))

    with pytest.raises(NautobotError, match="already exists"):
        client.create_match_rule(tenant="ACI:acme", name="r1", prefixes=[{"ip": "1.1.1.1/32"}])


def test_route_map_is_written_into_its_l3out(client_and_tenant):
    """Regression guard for the shallow-copy trap: this edits a nested dict
    inside aci_l3outs, which is exactly the shape that silently wrote nothing
    before _get_l3out_or_raise started deep-copying."""
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_tenant_with_l3out_and_epg())

    client.create_route_control_profile(
        tenant="ACI:acme", l3out="OSPF_L3Out", name="Uni-Route-Profile-OUT",
        contexts=[{"name": "permit-explicit", "order": 0, "action": "permit",
                   "match_rule": "match-permit-prefix-out"}],
    )

    profiles = _written_l3out(tenant)["route_control_profiles"]
    assert profiles[0]["name"] == "Uni-Route-Profile-OUT"
    assert profiles[0]["type"] == "global"
    assert profiles[0]["contexts"][0]["match_rule"] == "match-permit-prefix-out"


def test_route_map_on_a_missing_l3out_is_refused(client_and_tenant):
    client, set_tenant = client_and_tenant
    set_tenant(_tenant_with_l3out_and_epg())

    with pytest.raises(NautobotError, match="does not exist in tenant"):
        client.create_route_control_profile(
            tenant="ACI:acme", l3out="Nope", name="rm",
            contexts=[{"name": "c", "order": 0, "action": "permit"}],
        )


def test_binding_a_route_map_to_a_missing_epg_is_refused(client_and_tenant):
    client, set_tenant = client_and_tenant
    set_tenant(_tenant_with_l3out_and_epg())

    with pytest.raises(NautobotError, match="External EPG 'Nope' does not exist"):
        client.bind_external_epg_route_control_profile(
            tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Nope",
            route_control_profile="rm", direction="export",
        )


def test_binding_the_same_route_map_twice_is_refused(client_and_tenant):
    client, set_tenant = client_and_tenant
    set_tenant(_FakeTenant({"aci_l3outs": {"l3outs": [{
        "name": "OSPF_L3Out",
        "external_epgs": [{"name": "Cat_ExtNet", "route_control_profiles": [
            {"name": "rm", "direction": "export"}]}],
    }]}}))

    with pytest.raises(NautobotError, match="already bound"):
        client.bind_external_epg_route_control_profile(
            tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
            route_control_profile="rm", direction="export",
        )


def test_the_same_route_map_may_be_bound_in_both_directions(client_and_tenant):
    """Import and export are independent bindings of one map."""
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_FakeTenant({"aci_l3outs": {"l3outs": [{
        "name": "OSPF_L3Out",
        "external_epgs": [{"name": "Cat_ExtNet", "route_control_profiles": [
            {"name": "rm", "direction": "export"}]}],
    }]}}))

    client.bind_external_epg_route_control_profile(
        tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
        route_control_profile="rm", direction="import",
    )

    bindings = _written_l3out(tenant)["external_epgs"][0]["route_control_profiles"]
    assert sorted(b["direction"] for b in bindings) == ["export", "import"]


def test_subnet_scope_is_replaced_not_merged(client_and_tenant):
    """Merging would leave export-rtctrl in place, which is the exact flag the
    caller is trying to remove."""
    client, set_tenant = client_and_tenant
    tenant = set_tenant(_tenant_with_l3out_and_epg())

    result = client.set_external_epg_subnet_scope(
        tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
        ip="172.16.200.200/32", scope=["import-security"],
    )

    subnet = _written_l3out(tenant)["external_epgs"][0]["subnets"][0]
    assert subnet["scope"] == ["import-security"]
    assert result["previous_scope"] == ["export-rtctrl"]


def test_scope_change_on_a_missing_subnet_is_refused(client_and_tenant):
    client, set_tenant = client_and_tenant
    set_tenant(_tenant_with_l3out_and_epg())

    with pytest.raises(NautobotError, match="Subnet '9.9.9.9/32' does not exist"):
        client.set_external_epg_subnet_scope(
            tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
            ip="9.9.9.9/32", scope=["import-security"],
        )


# ---------------------------------------------------------------------------
# Location auto-resolution (2026-09-17).
#
# Eight schemas hardcoded location="ACI-Lab". That is the upstream lab's
# Location name; this lab's is "Isolated Lab Site", so eight tools were
# unusable here while being correct there. A Location name is a fact about
# the environment, not about the code -- no literal default can be right for
# both labs at once, and the two repos share this file.
# ---------------------------------------------------------------------------

class _Loc:
    def __init__(self, name, custom_fields=None):
        self.name = name
        self.custom_fields = custom_fields or {}


class _Locations:
    def __init__(self, locations):
        self._locations = locations

    def all(self):
        return list(self._locations)

    def get(self, name=None, **_):
        return next((l for l in self._locations if l.name == name), None)


def _client_with_locations(locations):
    """`api` is a lazy property with no setter, so the cached `_api` it returns
    is seeded directly rather than patching the property."""
    client = NautobotClient.__new__(NautobotClient)
    dcim = type("_Dcim", (), {"locations": _Locations(locations)})()
    client._api = type("_Api", (), {"dcim": dcim})()
    return client


def test_an_explicit_location_still_wins():
    """Any caller passing location= must behave exactly as before -- the
    upstream repo passes "ACI-Lab" explicitly in places."""
    client = _client_with_locations([_Loc("ACI-Lab"), _Loc("Isolated Lab Site")])

    assert client._get_location_or_raise("ACI-Lab").name == "ACI-Lab"


def test_an_explicit_location_that_does_not_exist_still_raises():
    client = _client_with_locations([_Loc("Isolated Lab Site")])

    with pytest.raises(NautobotError, match="Location 'ACI-Lab' not found"):
        client._get_location_or_raise("ACI-Lab")


def test_a_single_location_resolves_without_being_named():
    """Works in this lab and in the upstream one, with no argument and no
    hardcoded name in either."""
    for only in ("Isolated Lab Site", "ACI-Lab"):
        client = _client_with_locations([_Loc(only)])

        assert client._get_location_or_raise().name == only


def test_a_location_carrying_aci_intent_is_preferred():
    """Adding a Location for an unrelated project -- a Catalyst Center site,
    say -- must not make the ACI tools ambiguous."""
    client = _client_with_locations([
        _Loc("Catalyst Center Site", {"cc_fabric_policies": {"sites": []}}),
        _Loc("Isolated Lab Site", {"aci_fabric_policies": {"vlan_pools": [{"name": "P"}]}}),
    ])

    assert client._get_location_or_raise().name == "Isolated Lab Site"


def test_two_locations_carrying_aci_intent_refuse_to_guess():
    """Two ACI fabrics is real ambiguity. Writing intent to the wrong site is
    silent and hard to spot, so this fails naming both."""
    client = _client_with_locations([
        _Loc("Fabric A", {"aci_fabric_policies": {"vlan_pools": [{"name": "A"}]}}),
        _Loc("Fabric B", {"aci_fabric_policies": {"vlan_pools": [{"name": "B"}]}}),
    ])

    with pytest.raises(NautobotError, match="Fabric A, Fabric B"):
        client._get_location_or_raise()


def test_two_locations_with_no_aci_intent_also_refuse_to_guess():
    """Before any ACI intent exists there is nothing to prefer on, so an
    ambiguous fabric must still be named rather than guessed."""
    client = _client_with_locations([_Loc("Site 1"), _Loc("Site 2")])

    with pytest.raises(NautobotError, match="pass location="):
        client._get_location_or_raise()


def test_no_locations_at_all_says_what_to_do():
    client = _client_with_locations([])

    with pytest.raises(NautobotError, match="No Nautobot Location exists"):
        client._get_location_or_raise()
