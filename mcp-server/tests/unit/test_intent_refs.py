"""The rules that decide whether a delete is safe -- no Nautobot needed.

A delete that leaves a reference behind succeeds in Nautobot and fails the next
pipeline, so each rule is tested in both directions: the reference is found
when it exists, and nothing is reported when it does not (a false positive
would make an object undeletable).
"""
from __future__ import annotations

import pytest

from mcp_server import intent_refs as r

# One tenant that exercises every reference the rules know about.
TENANT_CF = {
    "aci_contracts": {
        "filters": [{"name": "web-flt"}, {"name": "unused-flt"}],
        "contracts": [
            {"name": "web-ct", "subjects": [{"name": "web-subj", "filters": ["web-flt"], "service_graph": "fw-graph"}]},
            {"name": "unused-ct", "subjects": []},
        ],
    },
    "aci_l3outs": {"l3outs": [{
        "name": "wan",
        "vrf": "prod",
        "domain": "wan-dom",
        "external_epgs": [{
            "name": "any",
            "provided_contracts": ["web-ct"],
            "route_control_profiles": [{"name": "export-map", "direction": "export"}],
        }],
        "route_control_profiles": [{"name": "export-map", "contexts": [{"name": "c1", "match_rule": "permit-web"}]}],
        "ospf_interfaces": [{"interface_key": "n101-e1/1", "policy": "ospf-p2p"}],
        "node_profiles": [{"name": "np", "interface_profiles": [{
            "name": "ip1", "nd_interface_policy": "nd-strict", "ingress_dpp_policy": "dpp-100m",
            "pim_v6_interface_policy": "pim-edge", "igmp_interface_policy": "igmp-v3",
            "custom_qos_policy": "cqos",
        }]}],
    }]},
    "aci_route_control": {"match_rules": [{"name": "permit-web"}, {"name": "unused-rule"}]},
    "aci_vrf_route_leaks": {"route_leaks": [{"name": "leak1", "source_vrf": "shared", "destination_vrf": "prod"}]},
    "aci_l4l7_services": {
        "devices": [{"name": "fw"}],
        "service_graphs": [{"name": "fw-graph", "contract": "web-ct", "device": "fw",
                            "consumer": {"redirect_policy": "pbr-in"}, "provider": {"redirect_policy": "pbr-out"}}],
        "redirect_policies": [{"name": "pbr-in", "ip_sla_policy": "sla-icmp",
                               "destinations": [{"ip": "10.0.0.5", "health_group": "hg1"}]}],
    },
}
BDS = [
    {"name": "web-bd", "vrfs": ["prod"], "cf": {"aci_bd_l3outs": ["wan"]}},
    {"name": "spare-bd", "vrfs": ["spare"], "cf": {}},
]
EPGS = [
    {"name": "web", "cf": {"aci_application_profile": "app", "aci_epg_bridge_domain": "web-bd",
                           "aci_epg_contracts": {"consumed": ["web-ct"]}}},
    {"name": "evpn-bd10", "cf": {"evpn_vrf": "evpn-vrf"}},
]


def _refs(kind, name, **kw):
    return r.tenant_references(kind, name, TENANT_CF, BDS, EPGS, **kw)


@pytest.mark.parametrize("kind,name,expect_in", [
    ("vrf", "prod", ["bridge domain 'web-bd'", "L3Out 'wan'", "VRF route leak 'leak1'"]),
    ("vrf", "shared", ["VRF route leak 'leak1'"]),
    ("vrf", "evpn-vrf", ["EVPN bridge domain 'evpn-bd10'"]),
    ("bridge_domain", "web-bd", ["EPG 'web'"]),
    ("contract", "web-ct", ["EPG 'web' consumes", "external EPG 'any' of L3Out 'wan' provides", "service graph 'fw-graph'"]),
    ("filter", "web-flt", ["subject 'web-subj' of contract 'web-ct'"]),
    ("l3out", "wan", ["bridge domain 'web-bd' advertises"]),
    ("match_rule", "permit-web", ["route map 'export-map'"]),
    ("ospf_interface_policy", "ospf-p2p", ["OSPF interface 'n101-e1/1'"]),
    ("nd_interface_policy", "nd-strict", ["as nd_interface_policy"]),
    ("dpp_policy", "dpp-100m", ["as ingress_dpp_policy"]),
    ("pim_interface_policy", "pim-edge", ["as pim_v6_interface_policy"]),
    ("igmp_interface_policy", "igmp-v3", ["as igmp_interface_policy"]),
    ("custom_qos_policy", "cqos", ["as custom_qos_policy"]),
    ("l4l7_device", "fw", ["service graph 'fw-graph'"]),
    ("service_graph", "fw-graph", ["contract 'web-ct' redirects"]),
    ("pbr_policy", "pbr-out", ["provider side"]),
    ("pbr_health_group", "hg1", ["destination 10.0.0.5"]),
    ("ip_sla_policy", "sla-icmp", ["redirect policy 'pbr-in'"]),
])
def test_a_reference_is_found(kind, name, expect_in):
    found = " | ".join(_refs(kind, name))
    for fragment in expect_in:
        assert fragment in found, f"{kind} '{name}': expected '{fragment}' in: {found or 'nothing'}"


@pytest.mark.parametrize("kind,name", [
    ("vrf", "spare-only-in-nothing"),
    ("bridge_domain", "spare-bd"),
    ("contract", "unused-ct"),
    ("filter", "unused-flt"),
    ("match_rule", "unused-rule"),
    ("l3out", "other"),
    ("ospf_interface_policy", "other"),
    ("nd_interface_policy", "other"),
    ("l4l7_device", "other"),
    ("epg", "web"),
    ("vrf_route_leak", "leak1"),
])
def test_an_unreferenced_object_reports_nothing(kind, name):
    """A false positive makes an object undeletable, which is the opposite
    failure and just as real."""
    assert _refs(kind, name) == []


def test_a_name_used_by_a_different_kind_is_not_a_reference():
    """'web-ct' is a contract. Deleting a FILTER called 'web-ct' must not be
    blocked by the contract's own bindings."""
    assert _refs("filter", "web-ct") == []


def test_route_map_references_are_scoped_to_its_own_l3out():
    assert _refs("route_control_profile", "export-map", l3out="wan")
    assert _refs("route_control_profile", "export-map", l3out="another-l3out") == []


def test_reading_tolerates_unset_and_malformed_fields():
    """Declared-but-unset Custom Fields come back as None -- the generator
    crashed on exactly that once (2026-09-15)."""
    assert r.tenant_references("contract", "x", {"aci_contracts": None, "aci_l3outs": {"l3outs": None}}) == []


# --- fabric ---------------------------------------------------------------

FABRIC_CF = {
    "aci_fabric_policies": {
        "vlan_pools": [{"name": "pool1"}],
        "physical_domains": [{"name": "phys1", "vlan_pool": "pool1"}],
        "l3_domains": [{"name": "wan-dom", "vlan_pool": "pool1"}],
        "aeps": [{"name": "aep1", "domains": ["phys1", {"name": "wan-dom", "type": "l3"}]}],
        "leaf_interface_policy_groups": [{"name": "ipg1", "aep": "aep1"}],
        "interface_selectors": [{"name": "sel1", "leaf_interface_profile": "lip101", "policy_group": "ipg1"}],
        "access_port_profiles": [{"name": "app1", "selectors": [{"name": "s1", "policy_group": "ipg2"}]}],
        "leaf_profiles": [{"name": "lp101", "access_port_profiles": ["app1"]}],
    },
    "aci_aaa_policies": {"local_users": [{"name": "ops", "security_domains": [{"name": "sec1"}]}]},
}
ALL_TENANTS = [
    {"name": "ACI:sales", "cf": TENANT_CF, "epgs": [
        {"name": "web", "cf": {"aci_epg_domains": {"domains": [{"name": "vmm1", "domain_type": "vmm"}]}}},
    ]},
    {"name": "ACI:hr", "cf": {"aci_l4l7_services": {"devices": [{"name": "fw2", "physical_domain": "phys1"}]}}, "epgs": []},
]


@pytest.mark.parametrize("kind,name,expect_in", [
    ("vlan_pool", "pool1", ["physical domain 'phys1'", "L3 domain 'wan-dom'"]),
    ("physical_domain", "phys1", ["AEP 'aep1'", "L4-L7 device 'fw2' in tenant 'ACI:hr'"]),
    ("l3_domain", "wan-dom", ["AEP 'aep1'", "L3Out 'wan' in tenant 'ACI:sales'"]),
    ("vmm_domain", "vmm1", ["EPG 'web' in tenant 'ACI:sales'"]),
    ("aep", "aep1", ["policy group 'ipg1'"]),
    ("leaf_interface_policy_group", "ipg1", ["interface selector 'sel1'"]),
    ("leaf_interface_policy_group", "ipg2", ["selector 's1' of access port profile 'app1'"]),
    ("leaf_interface_profile", "lip101", ["interface selector 'sel1'"]),
    ("access_port_profile", "app1", ["leaf profile 'lp101'"]),
    ("security_domain", "sec1", ["local user 'ops'"]),
])
def test_a_fabric_reference_is_found(kind, name, expect_in):
    found = " | ".join(r.fabric_references(kind, name, FABRIC_CF, ALL_TENANTS))
    for fragment in expect_in:
        assert fragment in found, f"{kind} '{name}': expected '{fragment}' in: {found or 'nothing'}"


def test_a_domain_type_must_match_not_just_the_name():
    """A physical and an L3 domain may share a name. Deleting the physical one
    must not be blocked by the AEP's L3 binding, and vice versa."""
    cf = {"aci_fabric_policies": {"aeps": [{"name": "a", "domains": [{"name": "same", "type": "l3"}]}]}}
    assert r.fabric_references("physical_domain", "same", cf, []) == []
    assert r.fabric_references("l3_domain", "same", cf, [])


def test_domains_are_checked_across_every_tenant():
    """The reason fabric deletes load all tenants: a check scoped to one
    tenant would pass while another tenant's device still uses the domain."""
    found = r.fabric_references("physical_domain", "phys1", {}, ALL_TENANTS)
    assert any("ACI:hr" in f for f in found)


@pytest.mark.parametrize("kind", ["interface_selector", "leaf_profile", "local_user"])
def test_fabric_kinds_nothing_refers_to(kind):
    assert r.fabric_references(kind, "anything", FABRIC_CF, ALL_TENANTS) == []


def test_pod_policy_group_assigned_to_the_pod_cannot_be_deleted():
    """Deleting the group would leave the pod selector pointing at nothing --
    the BGP route reflector policy silently stops applying."""
    cf = {"aci_fabric_policies": {"pod_policy_groups": [{"name": "pg1"}], "pod_profile": {"policy_group": "pg1"}}}
    found = r.fabric_references("pod_policy_group", "pg1", cf, [])
    assert found and "pod selector" in found[0]
    assert r.fabric_references("pod_policy_group", "other", cf, []) == []


def test_pod_policy_group_unassigned_has_no_references():
    assert r.fabric_references("pod_policy_group", "pg1", FABRIC_CF, ALL_TENANTS) == []


# --- helpers ----------------------------------------------------------------

def test_remove_named_removes_every_duplicate():
    """Older create_* tools appended duplicates. Removing only the first would
    leave the object in place while reporting success."""
    kept, removed = r.remove_named([{"name": "a"}, {"name": "b"}, {"name": "a"}], "a")
    assert kept == [{"name": "b"}]
    assert removed == 2


def test_remove_named_reports_zero_when_absent():
    kept, removed = r.remove_named([{"name": "b"}], "a")
    assert (kept, removed) == ([{"name": "b"}], 0)


@pytest.mark.parametrize("desc,expected", [
    ("ACI Bridge Domain: web-bd:sales", (False, None, "")),
    ("ACI Bridge Domain: web-bd:sales -- no-subnet", (True, None, "")),
    ("ACI Bridge Domain: web-bd:sales -- subnet-scope:public -- web tier", (False, "public", "web tier")),
    ("ACI Bridge Domain: web-bd:sales -- web tier -- 2nd part", (False, None, "web tier -- 2nd part")),
    ("free text, not an ACI description", (False, None, "free text, not an ACI description")),
    (None, (False, None, "")),
])
def test_parse_bd_description(desc, expected):
    assert r.parse_bd_description(desc) == expected


def test_compose_round_trips_create_bridge_domains_format():
    for desc in (
        "ACI Bridge Domain: web-bd:sales",
        "ACI Bridge Domain: web-bd:sales -- no-subnet -- note",
        "ACI Bridge Domain: web-bd:sales -- subnet-scope:public,shared -- web tier",
    ):
        no_subnet, marker, text = r.parse_bd_description(desc)
        assert r.compose_bd_description("web-bd", "sales", no_subnet=no_subnet, scope_marker=marker, text=text) == desc


def test_a_changed_description_keeps_the_bd_name_the_generator_reads():
    """The description IS the BD's name for the generator. Rewriting the user
    text must never change what bd_name_for_prefix returns."""
    composed = r.compose_bd_description("web-bd", "sales", text="anything: with a colon")
    assert r.bd_name_for_prefix("10.0.0.0/24", composed) == "web-bd"


def test_a_reference_is_reported_once_even_when_several_records_carry_it():
    """A two-subnet bridge domain is two Prefixes. Live run 2026-10-12 listed
    "bridge domain 'lc-bd1' is in this VRF" twice."""
    bds = [{"name": "bd", "vrfs": ["v"], "cf": {}}, {"name": "bd", "vrfs": ["v"], "cf": {}}]
    assert r.tenant_references("vrf", "v", {}, bds, []) == ["bridge domain 'bd' is in this VRF"]



# --- port-channel / vPC / management (2026-10-12) ------------------------------------

ACCESS_CF = {"aci_fabric_policies": {
    "aeps": [{"name": "AEP1"}],
    "lacp_policies": [{"name": "LACP_Active"}],
    "vpc_domains": [{"name": "vpc-101-102", "domain_id": 10, "node1": 101, "node2": 102}],
    "pc_vpc_policy_groups": [{"name": "Srv_vPC", "bundle_type": "vpc", "aep": "AEP1", "lacp_policy": "LACP_Active"}],
    "access_port_profiles": [{"name": "Leaf101", "selectors": [{"name": "srv", "policy_group": "Srv_vPC"}]}],
}}
ACCESS_TENANTS = [{"name": "ACI:sales", "cf": {}, "epgs": [{"name": "web", "cf": {"aci_static_paths": [
    {"path_type": "vpc", "node_id": 102, "node_id2": 101, "policy_group": "Srv_vPC", "encap": "vlan-10"},
]}}]}]


@pytest.mark.parametrize("kind,name,expect_in", [
    ("aep", "AEP1", ["PC/vPC policy group 'Srv_vPC' uses this AEP"]),
    ("lacp_policy", "LACP_Active", ["PC/vPC policy group 'Srv_vPC' uses this LACP policy"]),
    ("pc_vpc_policy_group", "Srv_vPC", ["selector 'srv' of access port profile 'Leaf101'",
                                        "EPG 'web' in tenant 'ACI:sales' is bound to vPC Srv_vPC"]),
    ("vpc_domain", "vpc-101-102", ["needs this vPC pair"]),
])
def test_access_references_are_found(kind, name, expect_in):
    found = " | ".join(r.fabric_references(kind, name, ACCESS_CF, ACCESS_TENANTS))
    for fragment in expect_in:
        assert fragment in found, f"{kind}: expected '{fragment}' in: {found or 'nothing'}"


def test_an_unrelated_pair_does_not_block_a_vpc_domain():
    """The binding in ACCESS_TENANTS stores 102 then 101 and is found above;
    a binding on another pair must not count."""
    tenants = [{"name": "t", "cf": {}, "epgs": [{"name": "e", "cf": {"aci_static_paths": [
        {"path_type": "vpc", "node_id": 103, "node_id2": 104, "policy_group": "X"}]}}]}]
    assert r.fabric_references("vpc_domain", "vpc-101-102", ACCESS_CF, tenants) == []


def test_an_inband_epg_is_referenced_only_by_in_band_addresses_naming_it():
    mgmt = [{"type": "in_band", "epg": "inb", "address": "10.49.0.101/24", "node": "leaf101"},
            {"type": "out_of_band", "epg": "default", "address": "10.48.0.101/24", "node": "leaf101"}]
    assert r.fabric_references("inband_mgmt_epg", "inb", {}, [], mgmt) == [
        "in-band management address 10.49.0.101/24 of node leaf101 uses this EPG"]
    assert r.fabric_references("inband_mgmt_epg", "other", {}, [], mgmt) == []


@pytest.mark.parametrize("a,b,same", [
    ({"node_id": 101, "module": 1, "port": 1}, {"node_id": 101, "module": 1, "port": 1, "encap": "vlan-9"}, True),
    ({"node_id": 101, "module": 1, "port": 1}, {"node_id": 101, "module": 1, "port": 2}, False),
    ({"path_type": "vpc", "node_id": 101, "node_id2": 102, "policy_group": "G"},
     {"path_type": "vpc", "node_id": 102, "node_id2": 101, "policy_group": "G"}, True),
    ({"path_type": "port_channel", "node_id": 101, "policy_group": "G"},
     {"path_type": "vpc", "node_id": 101, "node_id2": 102, "policy_group": "G"}, False),
])
def test_static_path_identity(a, b, same):
    assert (r.static_path_identity(a) == r.static_path_identity(b)) is same


# --- ESG / vzAny (2026-10-15) --------------------------------------------------

_ESG_CF = {"aci_endpoint_security_groups": {"esgs": [{
    "name": "web-esg", "application_profile": "ap", "vrf": "v1",
    "provided_contracts": ["web"], "consumed_contracts": ["db"],
    "epg_selectors": [{"application_profile": "ap", "endpoint_group": "web-epg"}],
}]}}


def test_an_esg_holds_its_vrf_and_contracts():
    assert any("ESG 'web-esg'" in f for f in r.tenant_references("vrf", "v1", _ESG_CF))
    assert any("ESG 'web-esg' provides" in f for f in r.tenant_references("contract", "web", _ESG_CF))
    assert any("ESG 'web-esg' consumes" in f for f in r.tenant_references("contract", "db", _ESG_CF))
    assert r.tenant_references("vrf", "v2", _ESG_CF) == []


def test_an_epg_selected_by_an_esg_cannot_be_deleted():
    found = r.tenant_references("epg", "web-epg", _ESG_CF, application_profile="ap")
    assert found and "ESG 'web-esg' selects this EPG" in found[0]
    assert r.tenant_references("epg", "web-epg", _ESG_CF, application_profile="other") == []


def test_a_contract_on_vzany_cannot_be_deleted():
    vrfs = [{"name": "v1", "cf": {"aci_vzany_contracts": {"provided": [], "consumed": ["shared"]}}}]
    found = r.tenant_references("contract", "shared", {}, vrfs=vrfs)
    assert found == ["vzAny of VRF 'v1' consumes this contract"]


# --- L3Out depth (2026-10-16) --------------------------------------------------

_L3D_CF = {"aci_l3outs": {"l3outs": [{
    "name": "out", "protocol": "bgp", "bgp_timers_policy": "t1", "bgp_best_path_policy": "bp",
    "node_profiles": [{"name": "np", "interface_profiles": [{"name": "ifp", "bfd_interface_policy": "bfd1"}]}],
    "external_epgs": [{"name": "ext", "subnets": [{"ip": "10.9.0.0/16", "bgp_route_summarization_policy": "sum"}]}],
}]}}
_L3D_VRFS = [{"name": "prod", "cf": {"aci_vrf_protocol_policies": {"bgp_timers_policy": "t1", "ospf_timers_policy": "ot",
                                                                   "route_tag_policy": "rt"}}}]


@pytest.mark.parametrize("kind,name,expected", [
    ("bfd_interface_policy", "bfd1", "interface profile 'ifp' of L3Out 'out' binds this policy as bfd_interface_policy"),
    ("bgp_timers_policy", "t1", "L3Out 'out' uses this as its bgp_timers_policy"),
    ("bgp_timers_policy", "t1", "VRF 'prod' uses this as its bgp_timers_policy"),
    ("bgp_best_path_policy", "bp", "L3Out 'out' uses this as its bgp_best_path_policy"),
    ("bgp_route_summarization_policy", "sum", "subnet 10.9.0.0/16 of external EPG 'ext' (L3Out 'out') summarizes with this policy"),
    ("ospf_timers_policy", "ot", "VRF 'prod' uses this as its ospf_timers_policy"),
    ("route_tag_policy", "rt", "VRF 'prod' uses this as its route_tag_policy"),
])
def test_l3out_depth_policies_in_use_cannot_be_deleted(kind, name, expected):
    assert expected in r.tenant_references(kind, name, _L3D_CF, vrfs=_L3D_VRFS)


def test_unused_l3out_depth_policies_have_no_references():
    for kind in ("bfd_interface_policy", "bgp_timers_policy", "bgp_best_path_policy",
                 "bgp_route_summarization_policy", "ospf_timers_policy", "route_tag_policy"):
        assert r.tenant_references(kind, "unused", _L3D_CF, vrfs=_L3D_VRFS) == []
        assert kind in r.TENANT_JSON_KINDS
