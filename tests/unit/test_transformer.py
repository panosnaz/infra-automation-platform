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

from generator.transformer import build_netascode_yaml


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
