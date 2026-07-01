"""Transform Nautobot ACI objects into a NetAsCode YAML data structure.

Nautobot ACI SSoT conventions observed in this lab:
  - Tenant names carry an "ACI:" namespace prefix (e.g. "ACI:infra") — stripped here.
  - VRFs are returned directly via the tenants.vrfs GraphQL relationship.
  - Prefixes carry a description "ACI Bridge Domain: <bd_name>:<tenant_name>" that
    encodes both the ACI bridge-domain name and the owning tenant.
  - Each prefix has a `vrfs` list; the first entry is the ACI VRF for that BD.

Output schema (netascode/aci Terraform provider):
  apic:
    tenants:
      - name: <tenant>
        vrfs:
          - name: <vrf>
        bridge_domains:
          - name: <bd>
            vrf: <vrf>
            subnets:
              - ip: <prefix>
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

# ACI built-in system tenants.  By default the generator skips them because
# Terraform should not re-create objects that ACI manages automatically.
_SYSTEM_TENANTS: frozenset[str] = frozenset({"common", "infra", "mgmt"})

# Regex to extract BD name from Nautobot prefix description field.
# Format produced by nautobot-ssot ACI: "ACI Bridge Domain: <bd_name>:<tenant_name>"
_BD_DESCRIPTION_RE = re.compile(r"^ACI Bridge Domain:\s*(?P<bd>[^:]+):(?P<tenant>.+)$")


def build_netascode_yaml(
    tenants: list[dict[str, Any]],
    prefixes: list[dict[str, Any]],
    include_system_tenants: bool = False,
) -> dict[str, Any]:
    """Convert Nautobot ACI data to a NetAsCode-compatible YAML structure.

    Args:
        tenants:  List returned by NautobotClient.get_tenants().
        prefixes: List returned by NautobotClient.get_prefixes().
        include_system_tenants: When True, include common/infra/mgmt tenants.

    Returns:
        Dict that can be serialised directly to the NetAsCode YAML schema.
    """
    # Index prefixes by the *stripped* ACI tenant name
    prefixes_by_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prefix in prefixes:
        tenant_raw = (prefix.get("tenant") or {}).get("name", "")
        aci_tenant = _strip_aci_prefix(tenant_raw)
        if aci_tenant:
            prefixes_by_tenant[aci_tenant].append(prefix)

    aci_tenants: list[dict[str, Any]] = []

    for tenant in tenants:
        aci_name = _strip_aci_prefix(tenant["name"])

        if not include_system_tenants and aci_name.lower() in _SYSTEM_TENANTS:
            continue

        entry: dict[str, Any] = {"name": aci_name}
        if tenant.get("description"):
            entry["description"] = tenant["description"]

        vrfs = _build_vrfs(tenant.get("vrfs", []))
        if vrfs:
            entry["vrfs"] = vrfs

        bridge_domains = _build_bridge_domains(prefixes_by_tenant.get(aci_name, []))
        if bridge_domains:
            entry["bridge_domains"] = bridge_domains

        aci_tenants.append(entry)

    return {"apic": {"tenants": aci_tenants}}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strip_aci_prefix(name: str) -> str:
    """Strip the 'ACI:' namespace prefix added by nautobot-ssot."""
    if name.startswith("ACI:"):
        return name[4:]
    return name


def _build_vrfs(vrfs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for vrf in vrfs:
        entry: dict[str, Any] = {"name": vrf["name"]}
        if vrf.get("description"):
            entry["description"] = vrf["description"]
        result.append(entry)
    return result


def _build_bridge_domains(prefixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for prefix in prefixes:
        network: str = prefix["prefix"]
        description: str = prefix.get("description") or ""

        # Derive bridge-domain name: prefer parsed from description, fall back to
        # a sanitised form of the network address.
        bd_name = _parse_bd_name(description) or _sanitise_prefix_as_bd_name(network)

        # VRF: take the first entry from the vrfs list (one BD has one VRF in ACI)
        vrf_list: list[dict[str, Any]] = prefix.get("vrfs") or []
        vrf_name = vrf_list[0]["name"] if vrf_list else None

        entry: dict[str, Any] = {
            "name": bd_name,
            "unicast_routing": True,
            "subnets": [
                {
                    "ip": network,
                    "public": False,
                    "private": True,
                    "shared": False,
                }
            ],
        }
        if vrf_name:
            entry["vrf"] = vrf_name

        result.append(entry)
    return result


def _parse_bd_name(description: str) -> str | None:
    """Extract BD name from 'ACI Bridge Domain: <bd>:<tenant>' description."""
    if not description:
        return None
    match = _BD_DESCRIPTION_RE.match(description.strip())
    return match.group("bd").strip() if match else None


def _sanitise_prefix_as_bd_name(prefix: str) -> str:
    """Convert a CIDR string to a safe ACI BD name, e.g. '10.0.0.0/27' → 'BD_10-0-0-0_27'."""
    return "BD_" + prefix.replace(".", "-").replace("/", "_")
