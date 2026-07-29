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
