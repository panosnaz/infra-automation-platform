"""Transform Nautobot VXLAN EVPN objects into a NetAsCode-equivalent YAML structure.

Nautobot EVPN conventions established by ADR-021:
  - Tenant names carry an "EVPN:" namespace prefix (mirrors ACI's "ACI:" prefix,
    stripped here the same way) -- keeps ACI and EVPN Tenants disjoint in the
    same Nautobot instance.
  - VRFs are returned directly via the tenants.vrfs GraphQL relationship
    (same shape as the ACI generator).
  - VLANs ARE Bridge Domains directly -- no Prefix-description parsing is
    needed here (unlike ACI), since NX-OS's own data model treats a bridge
    domain as a VLAN.
  - Each VLAN's L2 VNI and each VRF's L3 VNI come from Custom Fields
    (`evpn_l2_vni` / `evpn_l3_vni`) -- plain integers, not JSON, since a VNI
    is a single scalar (contrast with ACI's Contract/L3Out Custom Fields,
    which are JSON because those are nested structures).
  - Devices carry `evpn_bgp_asn` / `evpn_role` Custom Fields -- genuinely
    per-device attributes (leaf/spine/border-leaf each may have distinct
    values), unlike ACI Phase B's fabric-wide Location-scoped policies.

Output schema (feeds the nxos Terraform provider, ADR-021 §1):
  fabric:
    devices:
      - name: <device>
        bgp_asn: <int>
        role: <leaf|spine|border-leaf>
    tenants:
      - name: <tenant>
        vrfs:
          - name: <vrf>
            l3_vni: <int>
        bridge_domains:
          - name: <vlan-name>
            vlan_id: <int>
            l2_vni: <int>
            vrf: <vrf-name-or-null>
            gateway_ip: <ip/prefix-or-null>
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

# Mirrors platform/python/generator/transformer.py's _SYSTEM_TENANTS pattern --
# no NX-OS system tenants exist the way ACI's common/infra/mgmt do, but the
# constant is kept for structural symmetry and as an extension point.
_SYSTEM_TENANTS: frozenset[str] = frozenset()


def build_evpn_fabric_yaml(
    tenants: list[dict[str, Any]],
    vlans: list[dict[str, Any]],
    prefixes: list[dict[str, Any]],
    devices: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert Nautobot EVPN data to a NetAsCode-equivalent YAML structure.

    Args:
        tenants:  List returned by NautobotEvpnClient.get_tenants().
        vlans:    List returned by NautobotEvpnClient.get_vlans() -- Bridge Domains.
        prefixes: List returned by NautobotEvpnClient.get_prefixes() -- SVI gateways.
        devices:  List returned by NautobotEvpnClient.get_devices() -- fabric switches.

    Returns:
        Dict that can be serialised directly to the EVPN NetAsCode-equivalent
        YAML schema (ADR-021 §3).
    """
    # Index prefixes by VLAN id, to derive each Bridge Domain's gateway IP.
    prefix_by_vlan: dict[str, dict[str, Any]] = {}
    for prefix in prefixes:
        vlan = prefix.get("vlan")
        if vlan and vlan.get("id"):
            prefix_by_vlan[vlan["id"]] = prefix

    # Index VLANs by the *stripped* EVPN tenant name -- only VLANs under an
    # "EVPN:"-prefixed tenant are indexed, for the same reason the tenant
    # loop below only processes "EVPN:"-prefixed tenants.
    vlans_by_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for vlan in vlans:
        tenant_raw = (vlan.get("tenant") or {}).get("name", "")
        if not tenant_raw.startswith("EVPN:"):
            continue
        evpn_tenant = _strip_evpn_prefix(tenant_raw)
        if evpn_tenant:
            vlans_by_tenant[evpn_tenant].append(vlan)

    fabric_tenants: list[dict[str, Any]] = []
    for tenant in tenants:
        # Only tenants explicitly onboarded into the EVPN domain (the
        # "EVPN:" prefix) are exported -- this Nautobot instance holds ACI
        # and EVPN data side by side (ADR-021 §Consequences), so unlike the
        # ACI generator (which manages every tenant by default), this one
        # must explicitly skip anything without the prefix, not just strip it.
        if not tenant["name"].startswith("EVPN:"):
            continue

        evpn_name = _strip_evpn_prefix(tenant["name"])
        if not evpn_name or evpn_name.lower() in _SYSTEM_TENANTS:
            continue

        entry: dict[str, Any] = {"name": evpn_name}
        if tenant.get("description"):
            entry["description"] = tenant["description"]

        vrfs = _build_vrfs(tenant.get("vrfs", []))
        if vrfs:
            entry["vrfs"] = vrfs

        bridge_domains = _build_bridge_domains(vlans_by_tenant.get(evpn_name, []), prefix_by_vlan)
        if bridge_domains:
            entry["bridge_domains"] = bridge_domains

        fabric_tenants.append(entry)

    result: dict[str, Any] = {"fabric": {"tenants": fabric_tenants}}

    fabric_devices = _build_devices(devices)
    if fabric_devices:
        result["fabric"]["devices"] = fabric_devices

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strip_evpn_prefix(name: str) -> str:
    """Strip the 'EVPN:' namespace prefix (mirrors ACI's '_strip_aci_prefix')."""
    if name.startswith("EVPN:"):
        return name[5:]
    return name


def _build_vrfs(vrfs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for vrf in vrfs:
        entry: dict[str, Any] = {"name": vrf["name"]}
        if vrf.get("description"):
            entry["description"] = vrf["description"]

        cf = vrf.get("_custom_field_data") or {}
        # Custom fields are only emitted when explicitly set in Nautobot --
        # an unset field means "not yet allocated", not "use a default",
        # since a VNI collision is a hard failure, never silently defaulted.
        if (l3_vni := cf.get("evpn_l3_vni")) is not None:
            entry["l3_vni"] = int(l3_vni)

        result.append(entry)
    return result


def _build_bridge_domains(
    vlans: list[dict[str, Any]], prefix_by_vlan: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for vlan in vlans:
        entry: dict[str, Any] = {
            "name": vlan["name"],
            "vlan_id": vlan["vid"],
        }
        if vlan.get("description"):
            entry["description"] = vlan["description"]

        cf = vlan.get("_custom_field_data") or {}
        if (l2_vni := cf.get("evpn_l2_vni")) is not None:
            entry["l2_vni"] = int(l2_vni)
        if vrf_name := cf.get("evpn_vrf"):
            entry["vrf"] = vrf_name

        prefix = prefix_by_vlan.get(vlan["id"])
        if prefix:
            entry["gateway_ip"] = _to_gateway_ip(prefix["prefix"])

        result.append(entry)
    return result


def _build_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for device in devices:
        cf = device.get("_custom_field_data") or {}
        bgp_asn = cf.get("evpn_bgp_asn")
        role = cf.get("evpn_role")
        # Only emit devices explicitly onboarded into the EVPN fabric --
        # a device with neither field set is not yet part of this domain.
        if bgp_asn is None and not role:
            continue

        entry: dict[str, Any] = {"name": device["name"]}
        if bgp_asn is not None:
            entry["bgp_asn"] = int(bgp_asn)
        if role:
            entry["role"] = role

        result.append(entry)
    return result


def _to_gateway_ip(network: str) -> str:
    """First host address in the network, expressed with the same prefix length.

    Mirrors the ACI generator's identical convention (`transformer.py`'s
    `_to_gateway_ip`) -- reused as a pattern, not shared code, per ADR-018.
    """
    import ipaddress

    net = ipaddress.ip_network(network, strict=False)
    try:
        first_host = next(net.hosts())
    except StopIteration:
        return network
    return f"{first_host}/{net.prefixlen}"
