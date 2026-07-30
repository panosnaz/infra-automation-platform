"""Unit tests for platform/python/generator/evpn_transformer.py.

No live Nautobot required -- builds fixture dicts matching the shape
NautobotEvpnClient.get_tenants()/get_vlans()/get_prefixes()/get_devices()
return, and asserts on build_evpn_fabric_yaml()'s output.

Mirrors tests/unit/test_transformer.py's pattern for the ACI generator.
"""
from __future__ import annotations

from generator.evpn_transformer import build_evpn_fabric_yaml


def _tenant(name: str, description: str = "") -> dict:
    return {"name": name, "description": description, "vrfs": []}


def _vrf(name: str, custom_fields: dict | None = None) -> dict:
    return {"name": name, "description": "", "_custom_field_data": custom_fields or {}}


def _vlan(name: str, vid: int, tenant: str, custom_fields: dict | None = None) -> dict:
    return {
        "id": f"vlan-{name}",
        "name": name,
        "vid": vid,
        "description": "",
        "tenant": {"name": tenant},
        "_custom_field_data": custom_fields or {},
    }


def _prefix(prefix: str, vlan_id: str) -> dict:
    return {"prefix": prefix, "vlan": {"id": vlan_id}}


def _device(name: str, custom_fields: dict | None = None) -> dict:
    return {"name": name, "_custom_field_data": custom_fields or {}}


def test_non_evpn_tenants_are_skipped_entirely():
    """Regression guard for the real bug found during ADR-021 live
    verification: the first generator pass exported every tenant (including
    ACI:-prefixed ones), not just EVPN:-prefixed ones, because the prefix
    strip helper never actually skipped non-matching tenants."""
    tenants = [_tenant("ACI:web-tenant"), _tenant("EVPN:finance")]

    result = build_evpn_fabric_yaml(tenants, vlans=[], prefixes=[], devices=[])

    names = [t["name"] for t in result["fabric"]["tenants"]]
    assert names == ["finance"]


def test_evpn_prefix_is_stripped():
    tenants = [_tenant("EVPN:finance", description="Finance fabric")]

    result = build_evpn_fabric_yaml(tenants, vlans=[], prefixes=[], devices=[])

    tenant = result["fabric"]["tenants"][0]
    assert tenant["name"] == "finance"
    assert tenant["description"] == "Finance fabric"


def test_vrf_l3_vni_emitted_when_custom_field_set():
    tenants = [
        {
            "name": "EVPN:finance",
            "description": "",
            "vrfs": [_vrf("finance-vrf", {"evpn_l3_vni": 10010})],
        }
    ]

    result = build_evpn_fabric_yaml(tenants, vlans=[], prefixes=[], devices=[])

    vrf = result["fabric"]["tenants"][0]["vrfs"][0]
    assert vrf["name"] == "finance-vrf"
    assert vrf["l3_vni"] == 10010


def test_vrf_l3_vni_omitted_when_not_set():
    tenants = [
        {
            "name": "EVPN:finance",
            "description": "",
            "vrfs": [_vrf("finance-vrf")],
        }
    ]

    result = build_evpn_fabric_yaml(tenants, vlans=[], prefixes=[], devices=[])

    vrf = result["fabric"]["tenants"][0]["vrfs"][0]
    assert "l3_vni" not in vrf


def test_bridge_domain_emits_l2_vni_vrf_and_gateway_ip():
    tenants = [_tenant("EVPN:finance")]
    vlans = [
        _vlan(
            "finance-bd",
            100,
            "EVPN:finance",
            {"evpn_l2_vni": 10010, "evpn_vrf": "finance-vrf"},
        )
    ]
    prefixes = [_prefix("10.10.10.0/24", "vlan-finance-bd")]

    result = build_evpn_fabric_yaml(tenants, vlans, prefixes, devices=[])

    bd = result["fabric"]["tenants"][0]["bridge_domains"][0]
    assert bd["name"] == "finance-bd"
    assert bd["vlan_id"] == 100
    assert bd["l2_vni"] == 10010
    assert bd["vrf"] == "finance-vrf"
    assert bd["gateway_ip"] == "10.10.10.1/24"


def test_vlan_under_non_evpn_tenant_is_not_indexed():
    tenants = [_tenant("EVPN:finance")]
    vlans = [_vlan("aci-bd", 200, "ACI:web-tenant")]

    result = build_evpn_fabric_yaml(tenants, vlans, prefixes=[], devices=[])

    assert "bridge_domains" not in result["fabric"]["tenants"][0]


def test_device_emitted_only_when_bgp_asn_or_role_set():
    devices = [
        _device("leaf-a", {"evpn_bgp_asn": 65001, "evpn_role": "leaf"}),
        _device("unrelated-switch"),
    ]

    result = build_evpn_fabric_yaml(tenants=[], vlans=[], prefixes=[], devices=devices)

    device_names = [d["name"] for d in result["fabric"]["devices"]]
    assert device_names == ["leaf-a"]
    assert result["fabric"]["devices"][0]["bgp_asn"] == 65001
    assert result["fabric"]["devices"][0]["role"] == "leaf"


def test_no_devices_key_when_none_onboarded():
    result = build_evpn_fabric_yaml(tenants=[], vlans=[], prefixes=[], devices=[_device("unrelated-switch")])

    assert "devices" not in result["fabric"]
