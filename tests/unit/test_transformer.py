"""Unit tests for platform/python/generator/transformer.py.

No live Nautobot required -- builds fixture dicts matching the shape
NautobotClient.get_tenants()/get_prefixes() return (see client.py's GraphQL
queries) and asserts on build_netascode_yaml()'s output.

Covers ADR-020 Phase A item 1 (VRF/Bridge Domain attribute depth): custom
field values must appear in the generated YAML when set, and must be
omitted entirely when unset/null, so Terraform's own ACI defaults apply
(see main.tf's `lookup(..., null)`/`try(..., null)` pattern).
"""
from __future__ import annotations

import pytest

from generator.transformer import (
    FabricInventoryError,
    PolicyReferenceError,
    build_netascode_yaml,
)


def _device(name: str, node_id: int | None, role: str = "leaf", pod_id: int | None = None,
            serial: str = "", interfaces: list[str] | None = None) -> dict:
    """Shape matching NautobotClient.get_devices() -- see client.py's
    _QUERY_DEVICES."""
    cf: dict = {}
    if node_id is not None:
        cf["aci_node_id"] = node_id
    if pod_id is not None:
        cf["aci_pod_id"] = pod_id
    return {
        "name": name,
        "serial": serial,
        "role": {"name": role},
        "device_type": {"model": "Nexus 9000v"},
        "location": {"name": "Isolated Lab Site"},
        "interfaces": [{"name": i, "enabled": True, "description": ""} for i in (interfaces or [])],
        "_custom_field_data": cf,
    }


def _tenant_with_static_path(node_id: int) -> list[dict]:
    """A minimal tenant whose EPG binds a static path on `node_id`."""
    return [{
        "name": "ACI:sales",
        "description": "",
        "vrfs": [],
        "_custom_field_data": {},
    }]


def _vlan_with_static_path(node_id: int) -> dict:
    return {
        "name": "Web_EPG",
        "vid": 11,
        "description": "",
        "tenant": {"name": "ACI:sales"},
        "_custom_field_data": {
            "aci_application_profile": "eCommerce_AP",
            "aci_epg_bridge_domain": "Presales_BD",
            "aci_static_paths": [
                {"node_id": node_id, "pod_id": 1, "module": 1, "port": 10, "encap": "vlan-11", "mode": "regular"}
            ],
        },
    }


def _tenant(name: str, vrfs: list[dict] | None = None) -> dict:
    return {"name": name, "description": "", "vrfs": vrfs or []}


def _prefix(prefix: str, tenant: str, bd_name: str, vrf: str, custom_fields: dict | None = None) -> dict:
    return {
        "prefix": prefix,
        "description": f"ACI Bridge Domain: {bd_name}:{tenant}",
        "tenant": {"name": tenant},
        "vrfs": [{"name": vrf}],
        "_custom_field_data": custom_fields or {},
    }


def test_baseline_output_unchanged_when_no_custom_fields_set():
    """Regression guard: existing Tenant/VRF/BD/Subnet behavior must be
    byte-for-byte unaffected when no ADR-020 custom fields are populated."""
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf", "description": "d"}])]
    prefixes = [_prefix("10.0.0.0/24", "ACI:acme", "acme-bd", "acme-vrf")]

    result = build_netascode_yaml(tenants, prefixes)

    tenant = result["apic"]["tenants"][0]
    assert tenant["vrfs"][0] == {"name": "acme-vrf", "description": "d"}
    bd = tenant["bridge_domains"][0]
    assert set(bd.keys()) == {"name", "unicast_routing", "subnets", "vrf"}


def test_explicit_aci_gateway_ip_overrides_prefix_network_host_guess():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    prefix = _prefix("10.0.1.0/24", "ACI:acme", "acme-bd", "acme-vrf", {"aci_gateway_ip": "10.0.1.254/24"})

    bd = build_netascode_yaml(tenants, [prefix])["apic"]["tenants"][0]["bridge_domains"][0]

    assert bd["subnets"][0]["ip"] == "10.0.1.254/24"


def test_l3out_trunk_mode_maps_to_provider_regular_mode():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    tenants[0]["_custom_field_data"] = {
        "aci_l3outs": {
            "l3outs": [{
                "name": "bgp-out",
                "vrf": "acme-vrf",
                "node_profiles": [{
                    "name": "node-profile",
                    "interface_profiles": [{
                        "name": "interface-profile",
                        "interfaces": [{"node_id": 101, "mode": "trunk"}],
                    }],
                }],
            }]
        }
    }

    l3out = build_netascode_yaml(tenants, [])["apic"]["tenants"][0]["l3outs"][0]

    assert l3out["node_profiles"][0]["interface_profiles"][0]["interfaces"][0]["mode"] == "regular"


def test_l3out_shared_security_scope_includes_import_security():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    tenants[0]["_custom_field_data"] = {
        "aci_l3outs": {"l3outs": [{"name": "ospf-out", "vrf": "acme-vrf", "external_epgs": [{"name": "ext", "subnets": [{"ip": "10.0.0.0/24", "scope": ["shared-security"]}]}]}]}
    }

    subnet = build_netascode_yaml(tenants, [])["apic"]["tenants"][0]["l3outs"][0]["external_epgs"][0]["subnets"][0]

    assert subnet["scope"] == ["shared-security", "import-security"]


def test_bridge_domain_can_leave_subnet_under_epg():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "shared-vrf"}])]
    prefixes = [
        {
            **_prefix("192.0.2.0/32", "ACI:acme", "shared-bd", "shared-vrf"),
            "description": "ACI Bridge Domain: shared-bd:acme -- no-subnet",
        }
    ]

    bd = build_netascode_yaml(tenants, prefixes)["apic"]["tenants"][0]["bridge_domains"][0]

    assert bd == {"name": "shared-bd", "unicast_routing": True, "vrf": "shared-vrf"}


def test_epg_subnet_is_emitted_under_epg():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "shared-vrf"}])]
    prefixes = [_prefix("192.0.2.0/32", "ACI:acme", "shared-bd", "shared-vrf")]
    vlans = [{
        "name": "shared-epg",
        "tenant": {"name": "ACI:acme"},
        "_custom_field_data": {
            "aci_application_profile": "app",
            "aci_epg_bridge_domain": "shared-bd",
            "aci_epg_subnets": {"subnets": [{"ip": "10.0.4.254/24", "scope": ["shared"]}]},
        },
    }]

    epg = build_netascode_yaml(tenants, prefixes, vlans=vlans)["apic"]["tenants"][0]["application_profiles"][0]["endpoint_groups"][0]

    assert epg["subnets"] == [{"ip": "10.0.4.254/24", "scope": ["shared"]}]


def test_vrf_attribute_depth_emitted_when_custom_fields_set():
    tenants = [
        _tenant(
            "ACI:acme",
            vrfs=[
                {
                    "name": "acme-vrf",
                    "_custom_field_data": {
                        "aci_ip_data_plane_learning": False,
                        "aci_policy_control_enforcement_direction": "egress",
                        "aci_policy_control_enforcement_mode": "unenforced",
                    },
                }
            ],
        )
    ]

    result = build_netascode_yaml(tenants, prefixes=[])

    vrf = result["apic"]["tenants"][0]["vrfs"][0]
    assert vrf["ip_data_plane_learning"] == "disabled"
    assert vrf["policy_control_enforcement_direction"] == "egress"
    assert vrf["policy_control_enforcement_mode"] == "unenforced"


def test_vrf_ip_data_plane_learning_true_maps_to_enabled():
    tenants = [
        _tenant(
            "ACI:acme",
            vrfs=[{"name": "acme-vrf", "_custom_field_data": {"aci_ip_data_plane_learning": True}}],
        )
    ]

    result = build_netascode_yaml(tenants, prefixes=[])

    assert result["apic"]["tenants"][0]["vrfs"][0]["ip_data_plane_learning"] == "enabled"


def test_bridge_domain_attribute_depth_emitted_when_custom_fields_set():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    prefixes = [
        _prefix(
            "10.0.0.0/24",
            "ACI:acme",
            "acme-bd",
            "acme-vrf",
            custom_fields={
                "aci_bd_mac": "00:11:22:33:44:55",
                "aci_bd_arp_flooding": True,
                "aci_bd_advertise_host_routes": True,
                "aci_bd_l2_unknown_unicast": "flood",
                "aci_bd_l3_unknown_multicast": "opt-flood",
                "aci_bd_multi_destination": "drop",
                "aci_bd_ep_move_detect_mode": "garp",
                "aci_bd_pim": True,
            },
        )
    ]

    result = build_netascode_yaml(tenants, prefixes)

    bd = result["apic"]["tenants"][0]["bridge_domains"][0]
    assert bd["mac"] == "00:11:22:33:44:55"
    assert bd["arp_flooding"] is True
    assert bd["advertise_host_routes"] is True
    assert bd["l2_unknown_unicast"] == "flood"
    assert bd["l3_unknown_multicast"] == "opt-flood"
    assert bd["multi_destination"] == "drop"
    assert bd["ep_move_detect_mode"] == "garp"
    assert bd["pim"] is True


def test_bridge_domain_boolean_false_is_still_emitted_not_treated_as_unset():
    """An explicit False must be distinguished from "never set" (None) --
    both are falsy in Python, but only None should be omitted."""
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    prefixes = [
        _prefix(
            "10.0.0.0/24",
            "ACI:acme",
            "acme-bd",
            "acme-vrf",
            custom_fields={"aci_bd_arp_flooding": False, "aci_bd_pim": False},
        )
    ]

    result = build_netascode_yaml(tenants, prefixes)

    bd = result["apic"]["tenants"][0]["bridge_domains"][0]
    assert bd["arp_flooding"] is False
    assert bd["pim"] is False


def test_bridge_domain_omits_attributes_entirely_when_custom_fields_unset():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    prefixes = [_prefix("10.0.0.0/24", "ACI:acme", "acme-bd", "acme-vrf", custom_fields={})]

    result = build_netascode_yaml(tenants, prefixes)

    bd = result["apic"]["tenants"][0]["bridge_domains"][0]
    for key in (
        "mac",
        "arp_flooding",
        "advertise_host_routes",
        "l2_unknown_unicast",
        "l3_unknown_multicast",
        "multi_destination",
        "ep_move_detect_mode",
        "pim",
    ):
        assert key not in bd


def test_bridge_domain_omits_attributes_when_custom_field_explicitly_null():
    """Nautobot returns explicit `null` (not a missing key) for a custom
    field that exists but was never set on this particular object --
    handled the same as an absent key."""
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    prefixes = [
        _prefix(
            "10.0.0.0/24",
            "ACI:acme",
            "acme-bd",
            "acme-vrf",
            custom_fields={"aci_bd_arp_flooding": None, "aci_bd_mac": None},
        )
    ]

    result = build_netascode_yaml(tenants, prefixes)

    bd = result["apic"]["tenants"][0]["bridge_domains"][0]
    assert "arp_flooding" not in bd
    assert "mac" not in bd


def _vlan(name: str, tenant: str, vid: int = 100, description: str = "", custom_fields: dict | None = None) -> dict:
    return {
        "name": name,
        "vid": vid,
        "description": description,
        "tenant": {"name": tenant},
        "_custom_field_data": custom_fields or {},
    }


def test_baseline_output_has_no_application_profiles_when_no_vlans_given():
    """Regression guard: build_netascode_yaml must remain callable without
    the vlans parameter (backward compatibility for existing callers)."""
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]

    result = build_netascode_yaml(tenants, prefixes=[])

    assert "application_profiles" not in result["apic"]["tenants"][0]


def test_vlan_without_both_epg_custom_fields_is_skipped():
    """Opt-in requirement: a VLAN missing either aci_application_profile or
    aci_epg_bridge_domain must not produce an EPG (it's an ordinary IPAM
    VLAN unrelated to ACI)."""
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    vlans = [
        _vlan("plain-vlan", "ACI:acme"),
        _vlan("half-set", "ACI:acme", custom_fields={"aci_application_profile": "web-ap"}),
    ]

    result = build_netascode_yaml(tenants, prefixes=[], vlans=vlans)

    assert "application_profiles" not in result["apic"]["tenants"][0]


def test_application_profile_and_epg_emitted_when_both_custom_fields_set():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    vlans = [
        _vlan(
            "web-epg",
            "ACI:acme",
            description="Web tier",
            custom_fields={
                "aci_application_profile": "web-ap",
                "aci_epg_bridge_domain": "web-bd",
            },
        )
    ]

    result = build_netascode_yaml(tenants, prefixes=[], vlans=vlans)

    aps = result["apic"]["tenants"][0]["application_profiles"]
    assert aps == [
        {
            "name": "web-ap",
            "endpoint_groups": [
                {"name": "web-epg", "bridge_domain": "web-bd", "description": "Web tier"}
            ],
        }
    ]


def test_epgs_grouped_by_application_profile_name():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    vlans = [
        _vlan(
            "web-epg",
            "ACI:acme",
            custom_fields={"aci_application_profile": "web-ap", "aci_epg_bridge_domain": "web-bd"},
        ),
        _vlan(
            "db-epg",
            "ACI:acme",
            custom_fields={"aci_application_profile": "web-ap", "aci_epg_bridge_domain": "db-bd"},
        ),
        _vlan(
            "other-epg",
            "ACI:acme",
            custom_fields={"aci_application_profile": "other-ap", "aci_epg_bridge_domain": "other-bd"},
        ),
    ]

    result = build_netascode_yaml(tenants, prefixes=[], vlans=vlans)

    aps = {ap["name"]: ap for ap in result["apic"]["tenants"][0]["application_profiles"]}
    assert {epg["name"] for epg in aps["web-ap"]["endpoint_groups"]} == {"web-epg", "db-epg"}
    assert {epg["name"] for epg in aps["other-ap"]["endpoint_groups"]} == {"other-epg"}


def test_epg_preferred_group_member_only_emitted_when_true():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    vlans = [
        _vlan(
            "web-epg",
            "ACI:acme",
            custom_fields={
                "aci_application_profile": "web-ap",
                "aci_epg_bridge_domain": "web-bd",
                "aci_epg_preferred_group_member": True,
            },
        ),
        _vlan(
            "db-epg",
            "ACI:acme",
            custom_fields={
                "aci_application_profile": "web-ap",
                "aci_epg_bridge_domain": "db-bd",
                "aci_epg_preferred_group_member": False,
            },
        ),
    ]

    result = build_netascode_yaml(tenants, prefixes=[], vlans=vlans)

    epgs = {e["name"]: e for e in result["apic"]["tenants"][0]["application_profiles"][0]["endpoint_groups"]}
    assert epgs["web-epg"]["preferred_group_member"] is True
    assert "preferred_group_member" not in epgs["db-epg"]


def _tenant_with_contracts(name: str, aci_contracts: dict | None = None) -> dict:
    return {
        "name": name,
        "description": "",
        "vrfs": [],
        "_custom_field_data": {"aci_contracts": aci_contracts} if aci_contracts is not None else {},
    }


def test_baseline_output_has_no_filters_or_contracts_when_custom_field_unset():
    """Regression guard: tenants without the aci_contracts custom field (or
    with no _custom_field_data at all) must not get filters/contracts keys."""
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]

    result = build_netascode_yaml(tenants, prefixes=[])

    tenant = result["apic"]["tenants"][0]
    assert "filters" not in tenant
    assert "contracts" not in tenant


def test_filters_and_contracts_emitted_from_custom_field():
    tenants = [
        _tenant_with_contracts(
            "ACI:acme",
            aci_contracts={
                "filters": [
                    {
                        "name": "web-filter",
                        "entries": [
                            {
                                "name": "http",
                                "ether_type": "ip",
                                "ip_protocol": "tcp",
                                "dest_from_port": "http",
                                "dest_to_port": "http",
                            }
                        ],
                    }
                ],
                "contracts": [
                    {
                        "name": "web-to-db",
                        "scope": "context",
                        "subjects": [{"name": "web-to-db-subj", "filters": ["web-filter"]}],
                    }
                ],
            },
        )
    ]

    result = build_netascode_yaml(tenants, prefixes=[])

    tenant = result["apic"]["tenants"][0]
    assert tenant["filters"] == [
        {
            "name": "web-filter",
            "entries": [
                {
                    "name": "http",
                    "ether_type": "ip",
                    "ip_protocol": "tcp",
                    "dest_from_port": "http",
                    "dest_to_port": "http",
                }
            ],
        }
    ]
    assert tenant["contracts"] == [
        {
            "name": "web-to-db",
            "scope": "context",
            "subjects": [{"name": "web-to-db-subj", "filters": ["web-filter"]}],
        }
    ]


def test_epg_provided_and_consumed_contracts_emitted_only_when_set():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    vlans = [
        _vlan(
            "web-epg",
            "ACI:acme",
            custom_fields={
                "aci_application_profile": "web-ap",
                "aci_epg_bridge_domain": "web-bd",
                "aci_epg_contracts": {"provided": ["web-to-db"]},
            },
        ),
        _vlan(
            "db-epg",
            "ACI:acme",
            custom_fields={
                "aci_application_profile": "web-ap",
                "aci_epg_bridge_domain": "db-bd",
                "aci_epg_contracts": {"consumed": ["web-to-db"]},
            },
        ),
        _vlan(
            "no-contracts-epg",
            "ACI:acme",
            custom_fields={"aci_application_profile": "web-ap", "aci_epg_bridge_domain": "other-bd"},
        ),
    ]

    result = build_netascode_yaml(tenants, prefixes=[], vlans=vlans)

    epgs = {e["name"]: e for e in result["apic"]["tenants"][0]["application_profiles"][0]["endpoint_groups"]}
    assert epgs["web-epg"]["provided_contracts"] == ["web-to-db"]
    assert "consumed_contracts" not in epgs["web-epg"]
    assert epgs["db-epg"]["consumed_contracts"] == ["web-to-db"]
    assert "provided_contracts" not in epgs["db-epg"]
    assert "provided_contracts" not in epgs["no-contracts-epg"]
    assert "consumed_contracts" not in epgs["no-contracts-epg"]


def test_epg_domains_emitted_only_when_set():
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]
    vlans = [
        _vlan(
            "web-epg",
            "ACI:acme",
            custom_fields={
                "aci_application_profile": "web-ap",
                "aci_epg_bridge_domain": "web-bd",
                "aci_epg_domains": {
                    "domains": [
                        {"name": "phys-dom", "domain_type": "physical"},
                        {"name": "vmm-dom", "domain_type": "vmm", "resolution_immediacy": "immediate"},
                    ]
                },
            },
        ),
        _vlan(
            "no-domains-epg",
            "ACI:acme",
            custom_fields={"aci_application_profile": "web-ap", "aci_epg_bridge_domain": "other-bd"},
        ),
    ]

    result = build_netascode_yaml(tenants, prefixes=[], vlans=vlans)

    epgs = {e["name"]: e for e in result["apic"]["tenants"][0]["application_profiles"][0]["endpoint_groups"]}
    assert epgs["web-epg"]["domains"] == [
        {"name": "phys-dom", "domain_type": "physical"},
        {"name": "vmm-dom", "domain_type": "vmm", "resolution_immediacy": "immediate"},
    ]
    assert "domains" not in epgs["no-domains-epg"]


def test_baseline_output_has_no_l3outs_when_custom_field_unset():
    """Regression guard: tenants without the aci_l3outs custom field must
    not get an l3outs key."""
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]

    result = build_netascode_yaml(tenants, prefixes=[])

    assert "l3outs" not in result["apic"]["tenants"][0]


def test_l3outs_emitted_from_custom_field():
    tenants = [
        _tenant_with_contracts(
            "ACI:acme",
            aci_contracts=None,
        )
    ]
    tenants[0]["_custom_field_data"] = {
        "aci_l3outs": {
            "l3outs": [
                {
                    "name": "l3out-internet",
                    "vrf": "acme-vrf",
                    "description": "Internet L3Out",
                    "external_epgs": [
                        {
                            "name": "ext-epg-internet",
                            "provided_contracts": ["web-to-db"],
                            "subnets": [{"ip": "0.0.0.0/0", "scope": ["import-security"], "aggregate": "shared-rtctrl"}],
                        }
                    ],
                }
            ]
        }
    }

    result = build_netascode_yaml(tenants, prefixes=[])

    tenant = result["apic"]["tenants"][0]
    assert tenant["l3outs"] == [
        {
            "name": "l3out-internet",
            "vrf": "acme-vrf",
            "description": "Internet L3Out",
            "external_epgs": [
                {
                    "name": "ext-epg-internet",
                    "provided_contracts": ["web-to-db"],
                    "subnets": [{"ip": "0.0.0.0/0", "scope": ["import-security"], "aggregate": "shared-rtctrl"}],
                }
            ],
        }
    ]


def _location(name: str, aci_fabric_policies: dict | None = None) -> dict:
    return {
        "name": name,
        "_custom_field_data": {"aci_fabric_policies": aci_fabric_policies} if aci_fabric_policies is not None else {},
    }


def test_baseline_output_has_no_fabric_or_access_policies_when_locations_unset():
    """Regression guard: build_netascode_yaml must remain callable without
    the locations parameter (backward compatibility), and must not add
    fabric_policies/access_policies keys when no location has the custom
    field set."""
    tenants = [_tenant("ACI:acme", vrfs=[{"name": "acme-vrf"}])]

    result = build_netascode_yaml(tenants, prefixes=[])

    assert "fabric_policies" not in result["apic"]
    assert "access_policies" not in result["apic"]

    result = build_netascode_yaml(tenants, prefixes=[], locations=[_location("ACI-Lab")])

    assert "fabric_policies" not in result["apic"]
    assert "access_policies" not in result["apic"]


def test_fabric_and_access_policies_emitted_from_location_custom_field():
    locations = [
        _location(
            "ACI-Lab",
            aci_fabric_policies={
                "vlan_pools": [
                    {
                        "name": "pool1",
                        "alloc_mode": "static",
                        "ranges": [{"from": "vlan-100", "to": "vlan-200", "alloc_mode": "static", "role": "external"}],
                    }
                ],
                "physical_domains": [{"name": "phys1", "vlan_pool": "pool1"}],
                "aeps": [{"name": "aep1", "domains": ["phys1"]}],
                "leaf_interface_policy_groups": [{"name": "ipg1", "aep": "aep1"}],
            },
        )
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert result["apic"]["fabric_policies"] == {
        "vlan_pools": [
            {
                "name": "pool1",
                "alloc_mode": "static",
                "ranges": [{"from": "vlan-100", "to": "vlan-200", "alloc_mode": "static", "role": "external"}],
            }
        ]
    }
    assert result["apic"]["access_policies"] == {
        "physical_domains": [{"name": "phys1", "vlan_pool": "pool1"}],
        "aeps": [{"name": "aep1", "domains": ["phys1"]}],
        "leaf_interface_policy_groups": [{"name": "ipg1", "aep": "aep1"}],
    }


def test_fabric_and_access_policies_aggregated_across_multiple_locations():
    locations = [
        _location("site-a", aci_fabric_policies={"vlan_pools": [{"name": "pool-a", "alloc_mode": "static"}]}),
        _location("site-b", aci_fabric_policies={"vlan_pools": [{"name": "pool-b", "alloc_mode": "dynamic"}]}),
        _location("site-c"),
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    names = {p["name"] for p in result["apic"]["fabric_policies"]["vlan_pools"]}
    assert names == {"pool-a", "pool-b"}


def test_vmm_domains_emitted_from_location_custom_field():
    locations = [
        _location(
            "ACI-Lab",
            aci_fabric_policies={
                "vmm_domains": [
                    {
                        "name": "vmm1",
                        "vendor": "VMware",
                        "vlan_pool": "pool1",
                        "controller": {
                            "name": "vc1",
                            "host_or_ip": "vcenter.example.com",
                            "root_cont_name": "Datacenter1",
                        },
                        "credential": {"name": "vc1-cred"},
                    }
                ],
            },
        )
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert result["apic"]["fabric_policies"]["vmm_domains"] == [
        {
            "name": "vmm1",
            "vendor": "VMware",
            "vlan_pool": "pool1",
            "controller": {
                "name": "vc1",
                "host_or_ip": "vcenter.example.com",
                "root_cont_name": "Datacenter1",
            },
            "credential": {"name": "vc1-cred"},
        }
    ]


def test_vmm_domains_absent_when_unset():
    locations = [_location("ACI-Lab", aci_fabric_policies={"vlan_pools": [{"name": "pool1", "alloc_mode": "static"}]})]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert "vmm_domains" not in result["apic"]["fabric_policies"]


def test_vmm_domains_aggregated_across_multiple_locations():
    locations = [
        _location("site-a", aci_fabric_policies={"vmm_domains": [{"name": "vmm-a", "vendor": "VMware"}]}),
        _location("site-b", aci_fabric_policies={"vmm_domains": [{"name": "vmm-b", "vendor": "VMware"}]}),
        _location("site-c"),
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    names = {d["name"] for d in result["apic"]["fabric_policies"]["vmm_domains"]}
    assert names == {"vmm-a", "vmm-b"}


def test_coop_and_isis_policies_emitted_from_location_custom_field():
    locations = [
        _location(
            "ACI-Lab",
            aci_fabric_policies={
                "coop": {"type": "strict"},
                "isis": {"mtu": 1492, "redistrib_metric": 60},
            },
        )
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert result["apic"]["fabric_policies"]["coop"] == {"type": "strict"}
    assert result["apic"]["fabric_policies"]["isis"] == {"mtu": 1492, "redistrib_metric": 60}


def test_coop_and_isis_policies_absent_when_unset():
    locations = [_location("ACI-Lab", aci_fabric_policies={"vlan_pools": [{"name": "pool1", "alloc_mode": "static"}]})]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert "coop" not in result["apic"]["fabric_policies"]
    assert "isis" not in result["apic"]["fabric_policies"]


def test_coop_and_isis_policies_singleton_last_location_wins():
    locations = [
        _location("site-a", aci_fabric_policies={"coop": {"type": "strict"}}),
        _location("site-b", aci_fabric_policies={"coop": {"type": "lax"}}),
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert result["apic"]["fabric_policies"]["coop"] == {"type": "lax"}


def test_pod_policy_groups_emitted_and_aggregated_across_locations():
    locations = [
        _location("site-a", aci_fabric_policies={"pod_policy_groups": [{"name": "pod-pg-a"}]}),
        _location("site-b", aci_fabric_policies={"pod_policy_groups": [{"name": "pod-pg-b"}]}),
        _location("site-c"),
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    names = {g["name"] for g in result["apic"]["fabric_policies"]["pod_policy_groups"]}
    assert names == {"pod-pg-a", "pod-pg-b"}


def test_pod_policy_groups_absent_when_unset():
    locations = [_location("ACI-Lab", aci_fabric_policies={"vlan_pools": [{"name": "pool1", "alloc_mode": "static"}]})]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert "pod_policy_groups" not in result["apic"]["fabric_policies"]


def test_fault_and_syslog_policies_emitted_from_location_custom_field():
    locations = [
        _location(
            "ACI-Lab",
            aci_fabric_policies={
                "fault_lifecycle": {"soak": 120, "retain": 3600, "clear": 120},
                "syslog_system_msg": {"admin_state": "monitor"},
                "syslog_rate_limit": {"enabled": True, "limit_per_sec": 500},
            },
        )
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert result["apic"]["fabric_policies"]["fault_lifecycle"] == {"soak": 120, "retain": 3600, "clear": 120}
    assert result["apic"]["fabric_policies"]["syslog_system_msg"] == {"admin_state": "monitor"}
    assert result["apic"]["fabric_policies"]["syslog_rate_limit"] == {"enabled": True, "limit_per_sec": 500}


def test_fault_and_syslog_policies_absent_when_unset():
    locations = [_location("ACI-Lab", aci_fabric_policies={"vlan_pools": [{"name": "pool1", "alloc_mode": "static"}]})]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert "fault_lifecycle" not in result["apic"]["fabric_policies"]
    assert "syslog_system_msg" not in result["apic"]["fabric_policies"]
    assert "syslog_rate_limit" not in result["apic"]["fabric_policies"]


def test_fault_and_syslog_policies_singleton_last_location_wins():
    locations = [
        _location("site-a", aci_fabric_policies={"syslog_rate_limit": {"enabled": True, "limit_per_sec": 500}}),
        _location("site-b", aci_fabric_policies={"syslog_rate_limit": {"enabled": False, "limit_per_sec": 100}}),
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert result["apic"]["fabric_policies"]["syslog_rate_limit"] == {"enabled": False, "limit_per_sec": 100}


def _location_aaa(name: str, aci_aaa_policies: dict | None = None) -> dict:
    return {
        "name": name,
        "_custom_field_data": {"aci_aaa_policies": aci_aaa_policies} if aci_aaa_policies is not None else {},
    }


def test_aaa_policies_emitted_from_location_custom_field():
    locations = [
        _location_aaa(
            "ACI-Lab",
            aci_aaa_policies={
                "security_domains": [{"name": "phase-f-domain", "description": "test"}],
                "local_users": [
                    {
                        "name": "phase-f-user",
                        "email": "test@example.com",
                        "security_domains": [{"name": "phase-f-domain", "roles": [{"name": "read-all", "priv_type": "readPriv"}]}],
                    }
                ],
            },
        )
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert result["apic"]["aaa_policies"]["security_domains"] == [{"name": "phase-f-domain", "description": "test"}]
    assert result["apic"]["aaa_policies"]["local_users"] == [
        {
            "name": "phase-f-user",
            "email": "test@example.com",
            "security_domains": [{"name": "phase-f-domain", "roles": [{"name": "read-all", "priv_type": "readPriv"}]}],
        }
    ]


def test_aaa_policies_absent_when_unset():
    result = build_netascode_yaml([], prefixes=[], locations=[_location_aaa("ACI-Lab")])

    assert "aaa_policies" not in result["apic"]


def test_aaa_policies_aggregated_across_multiple_locations():
    locations = [
        _location_aaa("site-a", aci_aaa_policies={"security_domains": [{"name": "domain-a"}]}),
        _location_aaa("site-b", aci_aaa_policies={"local_users": [{"name": "user-b"}]}),
        _location_aaa("site-c"),
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)

    assert result["apic"]["aaa_policies"]["security_domains"] == [{"name": "domain-a"}]
    assert result["apic"]["aaa_policies"]["local_users"] == [{"name": "user-b"}]


# Ported from copilot/aci-platform-comparison (2026-09-08).
def test_l4l7_services_emitted_from_tenant_custom_field():
    tenants = [
        {
            "name": "ACI:acme",
            "description": "",
            "vrfs": [],
            "_custom_field_data": {
                "aci_l4l7_services": {
                    "devices": [
                        {
                            "name": "fw",
                            "service_type": "FW",
                            "logical_interfaces": [{"name": "inside"}, {"name": "outside"}],
                        }
                    ],
                    "service_graphs": [
                        {"name": "fw-graph", "contract": "web-to-db", "device": "fw"}
                    ],
                    "redirect_policies": [
                        {"name": "web-pbr", "destinations": [{"ip": "10.0.0.10", "mac": "00:11:22:33:44:55"}]}
                    ],
                }
            },
        }
    ]

    result = build_netascode_yaml(tenants, prefixes=[])

    assert result["apic"]["tenants"][0]["services"] == {
        "devices": [
            {
                "name": "fw",
                "service_type": "FW",
                "logical_interfaces": [{"name": "inside"}, {"name": "outside"}],
            }
        ],
        "service_graphs": [{"name": "fw-graph", "contract": "web-to-db", "device": "fw"}],
        "redirect_policies": [
            {"name": "web-pbr", "destinations": [{"ip": "10.0.0.10", "mac": "00:11:22:33:44:55"}]}
        ],
    }


def test_vrf_route_leaks_emitted_from_tenant_custom_field():
    tenants = [
        {
            "name": "ACI:shared-services",
            "description": "",
            "vrfs": [],
            "_custom_field_data": {
                "aci_vrf_route_leaks": {
                    "route_leaks": [
                        {
                            "name": "shared-to-app",
                            "source_vrf": "Shared_Services_VRF",
                            "destination_vrf": "App_VRF",
                            "subnet": "10.10.10.0/24",
                            "allow_l3out_advertisement": False,
                        },
                        {
                            "name": "l3out-to-app",
                            "source_vrf": "External_VRF",
                            "destination_vrf": "App_VRF",
                            "subnet": "172.16.200.200/32",
                            "allow_l3out_advertisement": True,
                        },
                    ]
                }
            },
        }
    ]

    result = build_netascode_yaml(tenants, prefixes=[])

    assert result["apic"]["tenants"][0]["vrf_route_leaks"][1]["allow_l3out_advertisement"] is True
    assert result["apic"]["tenants"][0]["vrf_route_leaks"][0]["source_vrf"] == "Shared_Services_VRF"


def test_access_bindings_and_l3out_protocol_intent_are_preserved():
    """Ported from copilot/aci-platform-comparison, adapted: that branch's
    EPG-to-domain binding (aci_physical_domains/aci_vmm_domains) was not
    ported (see _build_application_profiles()'s own comment) -- only the
    static_paths and L3Out protocol portions apply here. Domain binding is
    covered separately by test_epg_domains_emitted_only_when_set (the
    aci_epg_domains + bind_epg_domain path)."""
    tenants = [
        {
            "name": "ACI:acme",
            "description": "",
            "vrfs": [],
            "_custom_field_data": {
                "aci_l3outs": {
                    "l3outs": [
                        {
                            "name": "BGP_L3Out",
                            "vrf": "app-vrf",
                            "protocol": "bgp",
                            "node_profiles": [{"name": "L101", "nodes": [{"node_id": 101}]}],
                        }
                    ]
                }
            },
        }
    ]
    vlans = [
        {
            "name": "web-epg",
            "tenant": {"name": "ACI:acme"},
            "description": "",
            "_custom_field_data": {
                "aci_application_profile": "web-ap",
                "aci_epg_bridge_domain": "web-bd",
                "aci_static_paths": [{"pod_id": 1, "node_id": 101, "module": 1, "port": 5, "encap": "vlan-120", "mode": "regular"}],
            },
        }
    ]
    result = build_netascode_yaml(tenants, prefixes=[], vlans=vlans)

    assert result["apic"]["tenants"][0]["l3outs"][0]["protocol"] == "bgp"
    epg = result["apic"]["tenants"][0]["application_profiles"][0]["endpoint_groups"][0]
    assert epg["static_paths"][0]["port"] == 5


def test_xml_compatible_access_hierarchy_emitted_from_location_policy():
    locations = [
        _location(
            "ACI-Lab",
            aci_fabric_policies={
                "access_port_profiles": [
                    {
                        "name": "LEAF101_IFP",
                        "selectors": [
                            {
                                "name": "Ext_Nexus",
                                "policy_group": "ExtL3_IPG",
                                "blocks": [{"name": "portblk_ext_nexus", "from_card": 1, "to_card": 1, "from_port": 4, "to_port": 4}],
                            }
                        ],
                    }
                ],
                "leaf_profiles": [
                    {
                        "name": "LEAF101_SWP",
                        "access_port_profiles": ["LEAF101_IFP"],
                        "selectors": [
                            {"name": "LEAF101_Sel", "node_blocks": [{"name": "nodeblk_101_101", "from_node": 101, "to_node": 101}]}
                        ],
                    }
                ],
            },
        )
    ]

    result = build_netascode_yaml([], prefixes=[], locations=locations)
    access = result["apic"]["access_policies"]

    assert access["access_port_profiles"][0]["selectors"][0]["blocks"][0]["from_port"] == 4
    assert access["leaf_profiles"][0]["selectors"][0]["node_blocks"][0]["from_node"] == 101


# ---------------------------------------------------------------------------
# Fabric inventory (2026-09-14) -- leaf/spine switches sourced from Nautobot
# DCIM Devices, and validation of every node reference against them.
#
# This exists because the APIC accepts a `topology/pod-N/paths-M/...` DN
# naming a switch that does not exist and silently leaves the relation at
# `state: unformed` -- no Terraform error, no pipeline failure, no fault
# naming the intent that caused it. Generation time is the only place the
# mistake is still cheap to catch, so these tests guard a real silent-failure
# mode rather than a formatting preference.
# ---------------------------------------------------------------------------

def test_fabric_inventory_emitted_from_leaf_and_spine_devices():
    result = build_netascode_yaml(
        tenants=[], prefixes=[],
        devices=[
            _device("leaf-a", 101, "leaf", pod_id=1, serial="FDO23100852", interfaces=["eth1/4"]),
            _device("spine-1", 1001, "spine", pod_id=1, serial="FDO2306FG77"),
        ],
    )

    nodes = result["apic"]["fabric_inventory"]["nodes"]
    assert [n["node_id"] for n in nodes] == [101, 1001]
    assert nodes[0]["role"] == "leaf"
    assert nodes[0]["serial"] == "FDO23100852"
    assert nodes[0]["interfaces"] == [{"name": "eth1/4", "enabled": True}]
    assert nodes[1]["role"] == "spine"
    # A spine with no modeled interfaces is normal, not an error.
    assert "interfaces" not in nodes[1]


def test_fabric_inventory_absent_when_no_devices_given():
    """Callers predating this parameter must be unaffected -- no inventory
    key at all, rather than an empty one."""
    result = build_netascode_yaml(tenants=[], prefixes=[])
    assert "fabric_inventory" not in result["apic"]


def test_non_fabric_devices_are_ignored():
    """The APIC controller and any unrelated Device in the same Nautobot
    must not be mistaken for a switch. Opt-in by role, same rule as
    EPG-from-VLAN."""
    result = build_netascode_yaml(
        tenants=[], prefixes=[],
        devices=[
            _device("apic1", 1, role="controller"),
            _device("jump-host", 50, role="server"),
            _device("leaf-a", 101, role="leaf"),
        ],
    )

    nodes = result["apic"]["fabric_inventory"]["nodes"]
    assert [n["name"] for n in nodes] == ["leaf-a"]


def test_fabric_device_without_node_id_is_excluded_with_a_warning(capsys):
    """A switch missing aci_node_id cannot be resolved to a DN, so it is
    excluded -- but silently dropping it would make the later validation
    error baffling, hence the warning."""
    result = build_netascode_yaml(
        tenants=[], prefixes=[],
        devices=[_device("leaf-a", None, "leaf"), _device("leaf-b", 102, "leaf")],
    )

    nodes = result["apic"]["fabric_inventory"]["nodes"]
    assert [n["name"] for n in nodes] == ["leaf-b"]
    assert "leaf-a" in capsys.readouterr().err


def test_fabric_inventory_pod_id_defaults_to_one_when_unset():
    """Safe for a single-pod fabric and matches what the generator assumed
    implicitly before inventory existed. A multi-pod fabric must set it."""
    result = build_netascode_yaml(
        tenants=[], prefixes=[], devices=[_device("leaf-a", 101, "leaf", pod_id=None)]
    )
    assert result["apic"]["fabric_inventory"]["nodes"][0]["pod_id"] == 1


def test_fabric_inventory_pod_id_is_carried_through_when_set():
    result = build_netascode_yaml(
        tenants=[], prefixes=[], devices=[_device("leaf-a", 201, "leaf", pod_id=2)]
    )
    assert result["apic"]["fabric_inventory"]["nodes"][0]["pod_id"] == 2


def test_fabric_inventory_is_sorted_by_node_id_for_determinism():
    """The generate_nac CI job runs the generator twice and diffs the output.
    Nautobot does not guarantee Device ordering, so unstable ordering here
    would fail that determinism gate intermittently."""
    result = build_netascode_yaml(
        tenants=[], prefixes=[],
        devices=[
            _device("spine-1", 1001, "spine"),
            _device("leaf-b", 102, "leaf"),
            _device("leaf-a", 101, "leaf"),
        ],
    )
    assert [n["node_id"] for n in result["apic"]["fabric_inventory"]["nodes"]] == [101, 102, 1001]


def test_static_path_referencing_an_unknown_node_is_rejected():
    with pytest.raises(FabricInventoryError) as exc:
        build_netascode_yaml(
            tenants=_tenant_with_static_path(999),
            prefixes=[],
            vlans=[_vlan_with_static_path(999)],
            devices=[_device("leaf-a", 101, "leaf")],
        )

    message = str(exc.value)
    assert "node 999" in message
    assert "Web_EPG" in message          # names the offending intent
    assert "101 (leaf-a, leaf)" in message  # names what inventory does contain


def test_static_path_referencing_a_known_node_is_accepted():
    result = build_netascode_yaml(
        tenants=_tenant_with_static_path(101),
        prefixes=[],
        vlans=[_vlan_with_static_path(101)],
        devices=[_device("leaf-a", 101, "leaf")],
    )
    epg = result["apic"]["tenants"][0]["application_profiles"][0]["endpoint_groups"][0]
    assert epg["static_paths"][0]["node_id"] == 101


def test_l3out_interface_referencing_an_unknown_node_is_rejected():
    tenants = [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {"aci_l3outs": {"l3outs": [{
            "name": "BGP_L3Out", "vrf": "Presales_VRF",
            "node_profiles": [{
                "name": "L101",
                "nodes": [{"node_id": 101, "pod_id": 1}],
                "interface_profiles": [{
                    "name": "IP1",
                    "interfaces": [{"node_id": 777, "pod_id": 1, "module": 1, "port": 4}],
                }],
            }],
        }]}},
    }]

    with pytest.raises(FabricInventoryError) as exc:
        build_netascode_yaml(tenants=tenants, prefixes=[], devices=[_device("leaf-a", 101, "leaf")])

    assert "node 777" in str(exc.value)
    assert "interface profile 'IP1'" in str(exc.value)


def test_validation_is_skipped_when_no_inventory_exists():
    """Without inventory there is nothing to validate against. Failing here
    would break every deployment that has not yet modeled its switches."""
    result = build_netascode_yaml(
        tenants=_tenant_with_static_path(999), prefixes=[], vlans=[_vlan_with_static_path(999)], devices=[]
    )
    assert "fabric_inventory" not in result["apic"]


def test_validation_can_be_disabled_explicitly():
    """Escape hatch for inspecting known-broken intent -- must not be the
    default, or the silent-failure mode returns."""
    result = build_netascode_yaml(
        tenants=_tenant_with_static_path(999),
        prefixes=[],
        vlans=[_vlan_with_static_path(999)],
        devices=[_device("leaf-a", 101, "leaf")],
        validate_node_references=False,
    )
    assert result["apic"]["fabric_inventory"]["nodes"][0]["node_id"] == 101


def test_fabric_inventory_omits_serial_when_the_device_has_none():
    """Terraform registers APIC fabric membership with
    `for_each = { ... if lookup(n, "serial", "") != "" }`, keyed by serial --
    ACI matches a booting switch to its intended node ID by serial number.
    A device with no serial must therefore be present in inventory (so node
    references still validate) but carry no `serial` key, so Terraform
    skips registering it rather than creating a membership entry keyed by
    an empty string."""
    result = build_netascode_yaml(
        tenants=[], prefixes=[],
        devices=[_device("leaf-a", 101, "leaf", serial=""), _device("leaf-b", 102, "leaf", serial="FDO23041G37")],
    )

    nodes = {n["name"]: n for n in result["apic"]["fabric_inventory"]["nodes"]}
    assert "serial" not in nodes["leaf-a"]
    assert nodes["leaf-b"]["serial"] == "FDO23041G37"
    # Both still validate node references -- registration and validation are
    # independent concerns.
    assert {n["node_id"] for n in nodes.values()} == {101, 102}


def test_l4l7_services_emit_health_groups_and_ip_sla_policies():
    """PBR resilience objects (2026-09-15). Without a health group bound to
    a destination and an IP SLA policy behind it, a redirect policy keeps
    sending traffic to a dead destination -- so these have to survive the
    generator, not just exist in Terraform."""
    tenants = [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {"aci_l4l7_services": {
            "health_groups": [{"name": "fw-hg"}],
            "ip_sla_policies": [{"name": "fw-icmp", "sla_type": "icmp", "frequency": 5}],
            "redirect_policies": [{
                "name": "web-pbr",
                "ip_sla_policy": "fw-icmp",
                "threshold_enable": True,
                "min_threshold_percent": 20,
                "max_threshold_percent": 80,
                "destinations": [
                    {"ip": "10.0.0.10", "health_group": "fw-hg"},
                    {"ip": "10.0.0.11", "health_group": "fw-hg"},
                ],
            }],
        }},
    }]

    services = build_netascode_yaml(tenants=tenants, prefixes=[])["apic"]["tenants"][0]["services"]

    assert services["health_groups"] == [{"name": "fw-hg"}]
    assert services["ip_sla_policies"][0]["sla_type"] == "icmp"
    policy = services["redirect_policies"][0]
    assert policy["ip_sla_policy"] == "fw-icmp"
    assert [d["ip"] for d in policy["destinations"]] == ["10.0.0.10", "10.0.0.11"]
    assert all(d["health_group"] == "fw-hg" for d in policy["destinations"])


def test_l4l7_services_omit_resilience_keys_when_unset():
    """Same only-emit-when-set rule as every other generator key -- an empty
    health_groups list must not appear at all."""
    tenants = [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {"aci_l4l7_services": {"devices": [{"name": "fw"}]}},
    }]

    services = build_netascode_yaml(tenants=tenants, prefixes=[])["apic"]["tenants"][0]["services"]

    assert "health_groups" not in services
    assert "ip_sla_policies" not in services


def test_l4l7_concrete_interface_referencing_an_unknown_node_is_rejected():
    """A concrete interface resolves to the same topology/pod-N/paths-M DN as
    a static path, so a typo'd node is just as silent -- APIC accepts it and
    leaves the path attachment unformed."""
    tenants = [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {"aci_l4l7_services": {"devices": [{
            "name": "fw",
            "concrete_devices": [{"name": "fw1", "interfaces": [
                {"name": "eth1", "node_id": 999, "pod_id": 1, "module": 1, "port": 30}]}],
        }]}},
    }]

    with pytest.raises(FabricInventoryError) as exc:
        build_netascode_yaml(tenants=tenants, prefixes=[], devices=[_device("leaf-a", 101, "leaf")])

    assert "node 999" in str(exc.value)
    assert "concrete interface 'eth1'" in str(exc.value)


def test_l4l7_concrete_interface_on_a_known_node_is_accepted():
    tenants = [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {"aci_l4l7_services": {"devices": [{
            "name": "fw",
            "concrete_devices": [{"name": "fw1", "interfaces": [
                {"name": "eth1", "node_id": 101, "pod_id": 1, "module": 1, "port": 30}]}],
            "logical_interfaces": [{"name": "consumer", "concrete_interfaces": ["fw1/eth1"]}],
        }]}},
    }]

    services = build_netascode_yaml(
        tenants=tenants, prefixes=[], devices=[_device("leaf-a", 101, "leaf")]
    )["apic"]["tenants"][0]["services"]

    assert services["devices"][0]["concrete_devices"][0]["interfaces"][0]["node_id"] == 101
    assert services["devices"][0]["logical_interfaces"][0]["concrete_interfaces"] == ["fw1/eth1"]


def test_declared_but_unset_custom_field_does_not_crash_the_generator():
    """A DECLARED-but-unset Nautobot Custom Field is returned as an explicit
    None, not as a missing key -- so `.get(key, {})` never applies its
    default and `None.get(...)` raises. This crashed the generator the moment
    aci_ospf_interface_policies was declared in Nautobot (2026-09-15). Every
    JSON custom field the transformer reads must tolerate an explicit None.
    """
    tenants = [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {
            "aci_ospf_interface_policies": None,
            "aci_contracts": None,
            "aci_l3outs": None,
            "aci_vrf_route_leaks": None,
            "aci_l4l7_services": None,
        },
    }]

    result = build_netascode_yaml(tenants=tenants, prefixes=[])

    tenant = result["apic"]["tenants"][0]
    for key in ("ospf_interface_policies", "contracts", "filters", "l3outs", "vrf_route_leaks", "services"):
        assert key not in tenant, f"{key} should be omitted when its Custom Field is unset"


# ---------------------------------------------------------------------------
# Concrete devices (2026-09-15).
#
# main.tf has read `vnic_name` since the concrete-device work landed, but
# nothing upstream could produce it -- a grep for it across the repo returned
# exactly one hit, in main.tf itself. These tests pin the generator end of
# that path now that create_concrete_device exists to write it.
# ---------------------------------------------------------------------------

def _tenant_with_concrete_device(**device_overrides):
    device = {
        "name": "FW",
        "device_type": "VIRTUAL",
        "vmm_domain": "vCenter_VMM",
        "concrete_devices": [{
            "name": "ASAv_cdev",
            "vm_name": "ASAv-1",
            "vmm_controller_dn": "uni/vmmp-VMware/dom-vCenter_VMM/ctrlr-vCenter",
            "interfaces": [
                {"name": "cif1", "vnic_name": "Network adapter 2"},
                {"name": "cif2", "vnic_name": "Network adapter 3"},
            ],
        }],
        "logical_interfaces": [
            {"name": "db_int", "concrete_interfaces": ["ASAv_cdev/cif1"]},
            {"name": "backup_int", "concrete_interfaces": ["ASAv_cdev/cif2"]},
        ],
    }
    device.update(device_overrides)
    return [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {"aci_l4l7_services": {"devices": [device]}},
    }]


def test_virtual_concrete_device_survives_the_generator_intact():
    result = build_netascode_yaml(tenants=_tenant_with_concrete_device(), prefixes=[])

    device = result["apic"]["tenants"][0]["services"]["devices"][0]
    cdev = device["concrete_devices"][0]
    assert cdev["vm_name"] == "ASAv-1"
    assert cdev["vmm_controller_dn"] == "uni/vmmp-VMware/dom-vCenter_VMM/ctrlr-vCenter"
    assert [i["vnic_name"] for i in cdev["interfaces"]] == ["Network adapter 2", "Network adapter 3"]
    assert device["logical_interfaces"][0]["concrete_interfaces"] == ["ASAv_cdev/cif1"]


def test_concrete_devices_key_absent_when_none_are_declared():
    """The negative half. A device with no concrete devices must not emit an
    empty `concrete_devices` key -- main.tf's lookup would then iterate an
    empty list rather than skipping, and the absence is the signal."""
    tenants = [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {"aci_l4l7_services": {"devices": [
            {"name": "FW", "device_type": "VIRTUAL", "logical_interfaces": [{"name": "db_int"}]}
        ]}},
    }]

    result = build_netascode_yaml(tenants=tenants, prefixes=[])

    device = result["apic"]["tenants"][0]["services"]["devices"][0]
    assert "concrete_devices" not in device
    assert "concrete_interfaces" not in device["logical_interfaces"][0]


def test_physical_concrete_device_node_is_validated_against_the_fabric_roster():
    """A concrete interface path names a leaf. That reference goes through the
    same fatal roster validation as every other pathep- DN, so a typo fails
    the generator instead of silently producing an unformed relation."""
    tenants = _tenant_with_concrete_device(
        device_type="PHYSICAL",
        concrete_devices=[{
            "name": "fw1",
            "interfaces": [{"name": "eth1", "node_id": 999, "pod_id": 1, "module": 1, "port": 30}],
        }],
        logical_interfaces=[{"name": "consumer", "concrete_interfaces": ["fw1/eth1"]}],
    )
    with pytest.raises(FabricInventoryError, match="999"):
        build_netascode_yaml(tenants=tenants, prefixes=[],
                             devices=[_device("leaf-a", 101, "leaf")])


# ---------------------------------------------------------------------------
# L3Out Logical Interface Profile sub-policies (2026-09-16).
#
# The reference validation here exists because the Terraform provider only
# resolves these relations at APPLY time -- a plan renders whatever string it
# is handed and reports success. Measured: all seven relations failed at once
# with "Relation target dn <name> not found" after a clean plan.
# ---------------------------------------------------------------------------

_POLICY_CF = {
    "nd_interface_policies": [{"name": "ND_Pol", "hop_limit": 64}],
    "dpp_policies": [{"name": "In_100M", "rate": 100, "rate_unit": "mega"},
                     {"name": "Out_50M", "rate": 50, "rate_unit": "mega"}],
    "pim_interface_policies": [{"name": "PIM_Pol"}, {"name": "PIM6_Pol"}],
    "igmp_interface_policies": [{"name": "IGMP_Pol", "version": "v3"}],
    "custom_qos_policies": [{"name": "CQos"}],
}


def _tenant_with_policies(profile_overrides=None, policies=_POLICY_CF):
    profile = {"name": "IP1"}
    if profile_overrides:
        profile.update(profile_overrides)
    return [{
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {
            "aci_interface_policies": policies,
            "aci_l3outs": {"l3outs": [{
                "name": "Edge", "vrf": "v",
                "node_profiles": [{"name": "NP1", "interface_profiles": [profile]}],
            }]},
        },
    }]


def test_interface_policies_emitted_when_set():
    result = build_netascode_yaml(tenants=_tenant_with_policies(), prefixes=[])

    tenant = result["apic"]["tenants"][0]
    assert [p["name"] for p in tenant["nd_interface_policies"]] == ["ND_Pol"]
    assert [p["name"] for p in tenant["dpp_policies"]] == ["In_100M", "Out_50M"]
    assert [p["name"] for p in tenant["pim_interface_policies"]] == ["PIM_Pol", "PIM6_Pol"]
    assert tenant["igmp_interface_policies"][0]["version"] == "v3"
    assert tenant["custom_qos_policies"][0]["name"] == "CQos"


def test_interface_policy_keys_absent_when_unset():
    """The negative half. An empty key would make Terraform iterate an empty
    map instead of skipping the resource entirely."""
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [],
                "_custom_field_data": {"aci_interface_policies": None}}]

    result = build_netascode_yaml(tenants=tenants, prefixes=[])

    tenant = result["apic"]["tenants"][0]
    for key in ("nd_interface_policies", "dpp_policies", "pim_interface_policies",
                "igmp_interface_policies", "custom_qos_policies"):
        assert key not in tenant


def test_all_seven_policy_references_resolve():
    result = build_netascode_yaml(tenants=_tenant_with_policies({
        "qos_priority": "level3",
        "nd_interface_policy": "ND_Pol",
        "ingress_dpp_policy": "In_100M",
        "egress_dpp_policy": "Out_50M",
        "pim_interface_policy": "PIM_Pol",
        "pim_v6_interface_policy": "PIM6_Pol",
        "igmp_interface_policy": "IGMP_Pol",
        "custom_qos_policy": "CQos",
    }), prefixes=[])

    profile = result["apic"]["tenants"][0]["l3outs"][0]["node_profiles"][0]["interface_profiles"][0]
    assert profile["qos_priority"] == "level3"
    assert profile["nd_interface_policy"] == "ND_Pol"


@pytest.mark.parametrize(
    "ref_key,kind",
    [("nd_interface_policy", "nd_interface_policies"),
     ("ingress_dpp_policy", "dpp_policies"),
     ("egress_dpp_policy", "dpp_policies"),
     ("pim_interface_policy", "pim_interface_policies"),
     ("pim_v6_interface_policy", "pim_interface_policies"),
     ("igmp_interface_policy", "igmp_interface_policies"),
     ("custom_qos_policy", "custom_qos_policies")],
)
def test_a_dangling_policy_reference_is_fatal(ref_key, kind):
    with pytest.raises(PolicyReferenceError) as exc:
        build_netascode_yaml(tenants=_tenant_with_policies({ref_key: "Nope"}), prefixes=[])

    message = str(exc.value)
    assert "Nope" in message and ref_key in message and kind in message
    assert "ACI:sales" in message or "sales" in message


def test_the_error_names_what_is_actually_declared():
    """A dangling reference is usually a typo, so the message lists the real
    names rather than only saying the reference is wrong."""
    with pytest.raises(PolicyReferenceError, match="In_100M, Out_50M"):
        build_netascode_yaml(
            tenants=_tenant_with_policies({"ingress_dpp_policy": "In_100Mb"}), prefixes=[]
        )


def test_the_error_explains_that_default_is_not_valid():
    """`default` is the single most likely wrong guess, so the message says so
    explicitly rather than just reporting it as missing."""
    with pytest.raises(PolicyReferenceError, match="'default' is NOT valid"):
        build_netascode_yaml(
            tenants=_tenant_with_policies({"nd_interface_policy": "default"}), prefixes=[]
        )


def test_a_literal_dn_reference_is_allowed_through():
    """The documented escape hatch: a full uni/... DN points at a policy this
    platform does not manage, so there is nothing local to validate it
    against and main.tf passes it straight to APIC."""
    result = build_netascode_yaml(tenants=_tenant_with_policies({
        "nd_interface_policy": "uni/tn-common/ndifpol-default"
    }), prefixes=[])

    profile = result["apic"]["tenants"][0]["l3outs"][0]["node_profiles"][0]["interface_profiles"][0]
    assert profile["nd_interface_policy"] == "uni/tn-common/ndifpol-default"


def test_a_profile_with_no_policy_references_is_fine():
    build_netascode_yaml(tenants=_tenant_with_policies(), prefixes=[])


def test_policy_references_are_scoped_per_tenant():
    """A policy declared in one tenant must not satisfy a reference from
    another -- the DN main.tf builds is tenant-scoped."""
    tenants = _tenant_with_policies({"nd_interface_policy": "ND_Pol"})
    tenants.append({
        "name": "ACI:other", "description": "", "vrfs": [],
        "_custom_field_data": {
            "aci_interface_policies": None,
            "aci_l3outs": {"l3outs": [{
                "name": "OtherEdge", "vrf": "v",
                "node_profiles": [{"name": "NP", "interface_profiles": [
                    {"name": "IP", "nd_interface_policy": "ND_Pol"}
                ]}],
            }]},
        },
    })

    with pytest.raises(PolicyReferenceError, match="other"):
        build_netascode_yaml(tenants=tenants, prefixes=[])


# ---------------------------------------------------------------------------
# Route control + BD-to-L3Out (2026-09-16).
#
# A route-map context pointing at a match rule that does not exist matches
# nothing, and an ACI route map ends in an implicit deny -- so the result is
# advertising NO routes, with no error and no fault. Worth failing generation
# over.
# ---------------------------------------------------------------------------

def _rc_tenant(contexts=None, match_rules=("match-permit-prefix-out",), epg_bindings=None,
               bd_l3outs=None):
    tenant = {
        "name": "ACI:sales", "description": "", "vrfs": [],
        "_custom_field_data": {
            "aci_route_control": {
                "match_rules": [{"name": n, "prefixes": [{"ip": "172.16.200.200/32"}]}
                                for n in match_rules]
            },
            "aci_l3outs": {"l3outs": [{
                "name": "OSPF_L3Out", "vrf": "v",
                "route_control_profiles": [{
                    "name": "Uni-Route-Profile-OUT", "type": "global",
                    "contexts": contexts if contexts is not None else [
                        {"name": "permit-explicit", "order": 0, "action": "permit",
                         "match_rule": "match-permit-prefix-out"}],
                }],
                "external_epgs": [{"name": "Cat_ExtNet",
                                   "route_control_profiles": epg_bindings or []}],
            }]},
        },
    }
    return [tenant]


def test_match_rules_emitted_when_set():
    result = build_netascode_yaml(tenants=_rc_tenant(), prefixes=[])

    tenant = result["apic"]["tenants"][0]
    assert [r["name"] for r in tenant["match_rules"]] == ["match-permit-prefix-out"]
    profile = tenant["l3outs"][0]["route_control_profiles"][0]
    assert profile["type"] == "global"


def test_match_rules_key_absent_when_unset():
    """The negative half."""
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [],
                "_custom_field_data": {"aci_route_control": None}}]

    result = build_netascode_yaml(tenants=tenants, prefixes=[])

    assert "match_rules" not in result["apic"]["tenants"][0]


def test_a_context_naming_a_missing_match_rule_is_fatal():
    with pytest.raises(PolicyReferenceError) as exc:
        build_netascode_yaml(
            tenants=_rc_tenant(contexts=[{"name": "c", "order": 0, "action": "permit",
                                          "match_rule": "typo-rule"}]),
            prefixes=[],
        )

    message = str(exc.value)
    assert "typo-rule" in message
    assert "implicit deny" in message, "the message must explain WHY this is fatal"


def test_a_context_with_no_match_rule_is_allowed():
    """Matches everything -- a legitimate final catch-all deny."""
    build_netascode_yaml(
        tenants=_rc_tenant(contexts=[{"name": "catch-all", "order": 9, "action": "deny"}]),
        prefixes=[],
    )


def test_an_epg_binding_a_missing_route_map_is_fatal():
    with pytest.raises(PolicyReferenceError, match="Nope"):
        build_netascode_yaml(
            tenants=_rc_tenant(epg_bindings=[{"name": "Nope", "direction": "export"}]),
            prefixes=[],
        )


def test_an_epg_binding_a_declared_route_map_is_allowed():
    build_netascode_yaml(
        tenants=_rc_tenant(epg_bindings=[{"name": "Uni-Route-Profile-OUT", "direction": "export"}]),
        prefixes=[],
    )


def test_bd_public_scope_and_l3out_association_travel_together():
    """`public` was hardcoded False until 2026-09-16, so no BD subnet this
    platform created could ever be advertised out of an L3Out. Both halves are
    asserted together because neither does anything alone."""
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [],
                "_custom_field_data": {"aci_l3outs": {"l3outs": [{"name": "OSPF_L3Out", "vrf": "v"}]}}}]
    prefixes = [{"prefix": "10.0.3.0/24",
                 "description": "ACI Bridge Domain: Transit_BD:sales",
                 "tenant": {"name": "ACI:sales"},
                 "vrfs": [{"name": "Presales_VRF"}],
                 "_custom_field_data": {"aci_gateway_ip": "10.0.3.254/24",
                                        "aci_bd_subnet_scope": "public",
                                        "aci_bd_l3outs": ["OSPF_L3Out"]}}]

    result = build_netascode_yaml(tenants=tenants, prefixes=prefixes)

    bd = result["apic"]["tenants"][0]["bridge_domains"][0]
    assert bd["subnets"][0]["public"] is True
    assert bd["subnets"][0]["private"] is False
    assert bd["l3outs"] == ["OSPF_L3Out"]


def test_bd_defaults_to_private_when_no_scope_asked_for():
    """Every BD that existed before this change must keep its old shape."""
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [], "_custom_field_data": {}}]
    prefixes = [{"prefix": "10.0.2.0/24",
                 "description": "ACI Bridge Domain: DB_BD:sales",
                 "tenant": {"name": "ACI:sales"},
                 "vrfs": [{"name": "Presales_VRF"}],
                 "_custom_field_data": {"aci_gateway_ip": "10.0.2.254/24"}}]

    result = build_netascode_yaml(tenants=tenants, prefixes=prefixes)

    subnet = result["apic"]["tenants"][0]["bridge_domains"][0]["subnets"][0]
    assert subnet["public"] is False and subnet["private"] is True


def test_bd_associated_with_an_undeclared_l3out_is_fatal():
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [], "_custom_field_data": {}}]
    prefixes = [{"prefix": "10.0.3.0/24",
                 "description": "ACI Bridge Domain: Transit_BD:sales",
                 "tenant": {"name": "ACI:sales"},
                 "vrfs": [{"name": "Presales_VRF"}],
                 "_custom_field_data": {"aci_gateway_ip": "10.0.3.254/24",
                                        "aci_bd_l3outs": ["Nope"]}}]

    with pytest.raises(PolicyReferenceError, match="Nope"):
        build_netascode_yaml(tenants=tenants, prefixes=prefixes)


# ---------------------------------------------------------------------------
# Multi-subnet bridge domains (2026-09-16).
#
# Nautobot models a BD as a Prefix, so two prefixes naming the same BD are two
# SUBNETS of one bridge domain. Appending them blindly produced duplicate BD
# names, which Terraform rejects with "Duplicate object key".
# ---------------------------------------------------------------------------

def _bd_prefix(net, gw, **cf):
    return {"prefix": net, "description": "ACI Bridge Domain: DB_BD:sales",
            "tenant": {"name": "ACI:sales"}, "vrfs": [{"name": "Presales_VRF"}],
            "_custom_field_data": {"aci_gateway_ip": gw, **cf}}


def test_two_prefixes_naming_one_bd_become_one_bd_with_two_subnets():
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [],
                "_custom_field_data": {"aci_l3outs": {"l3outs": [{"name": "OSPF_L3Out", "vrf": "v"}]}}}]
    prefixes = [_bd_prefix("10.0.2.0/24", "10.0.2.254/24"),
                _bd_prefix("10.0.3.0/24", "10.0.3.254/24",
                           aci_bd_subnet_scope="public", aci_bd_l3outs=["OSPF_L3Out"])]

    bds = build_netascode_yaml(tenants=tenants, prefixes=prefixes)["apic"]["tenants"][0]["bridge_domains"]

    assert len(bds) == 1, "two prefixes for one BD must not produce two bridge domains"
    assert [s["ip"] for s in bds[0]["subnets"]] == ["10.0.2.254/24", "10.0.3.254/24"]
    assert bds[0]["l3outs"] == ["OSPF_L3Out"]


def test_merged_bd_keeps_per_subnet_scope():
    """The two subnets of one BD may differ -- one private, one advertised."""
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [],
                "_custom_field_data": {"aci_l3outs": {"l3outs": [{"name": "OSPF_L3Out", "vrf": "v"}]}}}]
    prefixes = [_bd_prefix("10.0.2.0/24", "10.0.2.254/24"),
                _bd_prefix("10.0.3.0/24", "10.0.3.254/24",
                           aci_bd_subnet_scope="public", aci_bd_l3outs=["OSPF_L3Out"])]

    subnets = build_netascode_yaml(tenants=tenants, prefixes=prefixes)["apic"]["tenants"][0]["bridge_domains"][0]["subnets"]

    assert subnets[0]["private"] is True and subnets[0]["public"] is False
    assert subnets[1]["public"] is True and subnets[1]["private"] is False


def test_bd_level_attributes_do_not_depend_on_prefix_order():
    """BD-level attributes belong to the bridge domain, not a subnet. The
    first prefix that sets one wins; a later one must not silently overwrite
    it, or output would depend on Nautobot's row order."""
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [], "_custom_field_data": {}}]
    prefixes = [_bd_prefix("10.0.2.0/24", "10.0.2.254/24", aci_bd_mac="00:11:22:33:44:55"),
                _bd_prefix("10.0.3.0/24", "10.0.3.254/24", aci_bd_mac="00:99:99:99:99:99")]

    bd = build_netascode_yaml(tenants=tenants, prefixes=prefixes)["apic"]["tenants"][0]["bridge_domains"][0]

    assert bd["mac"] == "00:11:22:33:44:55"


def test_distinct_bd_names_still_produce_distinct_bridge_domains():
    """The merge must key on BD name, not collapse everything."""
    tenants = [{"name": "ACI:sales", "description": "", "vrfs": [], "_custom_field_data": {}}]
    prefixes = [
        {"prefix": "10.0.2.0/24", "description": "ACI Bridge Domain: DB_BD:sales",
         "tenant": {"name": "ACI:sales"}, "vrfs": [], "_custom_field_data": {"aci_gateway_ip": "10.0.2.254/24"}},
        {"prefix": "10.0.9.0/24", "description": "ACI Bridge Domain: Backup_BD:sales",
         "tenant": {"name": "ACI:sales"}, "vrfs": [], "_custom_field_data": {"aci_gateway_ip": "10.0.9.254/24"}},
    ]

    bds = build_netascode_yaml(tenants=tenants, prefixes=prefixes)["apic"]["tenants"][0]["bridge_domains"]

    assert sorted(b["name"] for b in bds) == ["Backup_BD", "DB_BD"]


def test_l3_domains_emitted_from_the_location_field():
    locations = [{"name": "ACI-Lab", "_custom_field_data": {"aci_fabric_policies": {
        "l3_domains": [{"name": "ExtL3Dom", "vlan_pool": "ExtL3_Pool"}]}}}]

    result = build_netascode_yaml(tenants=[], prefixes=[], locations=locations)

    assert result["apic"]["access_policies"]["l3_domains"][0]["vlan_pool"] == "ExtL3_Pool"


def test_l3_domains_key_absent_when_unset():
    locations = [{"name": "ACI-Lab", "_custom_field_data": {"aci_fabric_policies": {}}}]

    result = build_netascode_yaml(tenants=[], prefixes=[], locations=locations)

    assert "l3_domains" not in (result["apic"].get("access_policies") or {})
