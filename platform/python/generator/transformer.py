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

import ipaddress
import re
import sys
from copy import deepcopy
from collections import defaultdict
from typing import Any

# ACI built-in system tenants.  By default the generator skips them because
# Terraform should not re-create objects that ACI manages automatically.
_SYSTEM_TENANTS: frozenset[str] = frozenset({"common", "infra", "mgmt"})

# Regex to extract BD name from Nautobot prefix description field.
# Format produced by nautobot-ssot ACI: "ACI Bridge Domain: <bd_name>:<tenant_name>"
_BD_DESCRIPTION_RE = re.compile(r"^ACI Bridge Domain:\s*(?P<bd>[^:]+):(?P<tenant>.+)$")


class PolicyReferenceError(ValueError):
    """Raised when an L3Out Logical Interface Profile references a policy
    that is not declared in the same tenant.

    Fatal for the same reason FabricInventoryError is. The provider resolves
    these relations to a DN and validates them at APPLY time, not plan time
    -- a `terraform plan` renders whatever string it is given and reports
    success, then the apply dies with "Relation target dn <name> not found"
    (measured 2026-09-16, when all seven relations failed at once). Catching
    it here names the tenant and the offending reference instead.
    """


class FabricInventoryError(ValueError):
    """Raised when generated intent references a fabric node that does not
    exist in Nautobot's DCIM inventory.

    This is deliberately fatal rather than a warning. An unknown node ID
    produces a `topology/pod-N/paths-M/...` DN that the APIC accepts and
    then silently leaves at `state: unformed` -- no Terraform error, no
    pipeline failure, no fault that names the intent that caused it. Failing
    at generation time is the only point in the whole chain where the
    mistake is still cheap to diagnose.
    """


def build_netascode_yaml(
    tenants: list[dict[str, Any]],
    prefixes: list[dict[str, Any]],
    vlans: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    devices: list[dict[str, Any]] | None = None,
    include_system_tenants: bool = False,
    validate_node_references: bool = True,
) -> dict[str, Any]:
    """Convert Nautobot ACI data to a NetAsCode-compatible YAML structure.

    Args:
        tenants:   List returned by NautobotClient.get_tenants().
        prefixes:  List returned by NautobotClient.get_prefixes().
        vlans:     List returned by NautobotClient.get_vlans() -- represents
                   EPGs (ADR-020 Phase A item 2). Optional/defaults to none
                   for callers that predate this parameter.
        locations: List returned by NautobotClient.get_locations() -- sources
                   fabric-wide Access/Fabric Policies (ADR-020 Phase B).
                   Optional/defaults to none for callers that predate this
                   parameter.
        devices:   List returned by NautobotClient.get_devices() -- the
                   leaf/spine fabric inventory. Optional/defaults to none
                   for callers that predate this parameter, in which case
                   no inventory is emitted and node validation is skipped
                   (there is nothing to validate against).
        include_system_tenants: When True, include common/infra/mgmt tenants.
        validate_node_references: When True (default) and inventory is
                   supplied, raise FabricInventoryError if any static path
                   or L3Out interface references a node ID that is not in
                   inventory. Set False only to inspect broken intent.

    Returns:
        Dict that can be serialised directly to the NetAsCode YAML schema.

    Raises:
        FabricInventoryError: an intent object references an unknown node.
    """
    # Index prefixes by the *stripped* ACI tenant name
    prefixes_by_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prefix in prefixes:
        tenant_raw = (prefix.get("tenant") or {}).get("name", "")
        aci_tenant = _strip_aci_prefix(tenant_raw)
        if aci_tenant:
            prefixes_by_tenant[aci_tenant].append(prefix)

    # Index VLANs (candidate EPGs) by the *stripped* ACI tenant name
    vlans_by_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for vlan in vlans or []:
        tenant_raw = (vlan.get("tenant") or {}).get("name", "")
        aci_tenant = _strip_aci_prefix(tenant_raw)
        if aci_tenant:
            vlans_by_tenant[aci_tenant].append(vlan)

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

        application_profiles = _build_application_profiles(vlans_by_tenant.get(aci_name, []))
        _add_endpoint_security_groups(application_profiles, tenant.get("_custom_field_data") or {})
        if application_profiles:
            entry["application_profiles"] = application_profiles

        filters, contracts = _build_contracts_and_filters(tenant.get("_custom_field_data") or {})
        if filters:
            entry["filters"] = filters
        if contracts:
            entry["contracts"] = contracts

        l3outs = _build_l3outs(tenant.get("_custom_field_data") or {})
        if l3outs:
            entry["l3outs"] = l3outs

        # `.get(key, {})` only applies the default when the key is ABSENT. A
        # DECLARED-but-unset Nautobot Custom Field comes back as an explicit
        # None, so the default never fires and None.get() raises. Every other
        # field here already uses the `or {}` form; this line did not, and
        # crashed the generator the moment aci_ospf_interface_policies was
        # declared in Nautobot (2026-09-15).
        ospf_cf = (tenant.get("_custom_field_data") or {}).get("aci_ospf_interface_policies") or {}
        ospf_policies = list(ospf_cf.get("policies") or [])
        if ospf_policies:
            entry["ospf_interface_policies"] = ospf_policies

        # L3Out Logical Interface Profile sub-policies (2026-09-16). One
        # Custom Field holds all five lists rather than five fields, because
        # they are always configured together and a single field means one
        # declaration to keep in sync (the undeclared-field failure mode --
        # finding F-01 -- scales with the number of fields).
        entry.update(_build_interface_policies(tenant.get("_custom_field_data") or {}))

        # L3Out depth (2026-10-16): BGP timers / best path / route
        # summarization, OSPF timers and route tag policies -- tenant-scoped,
        # named by VRFs, L3Outs and external EPG subnets.
        protocol_cf = (tenant.get("_custom_field_data") or {}).get("aci_protocol_policies") or {}
        for kind in PROTOCOL_POLICY_KINDS:
            if protocol_cf.get(kind):
                entry[kind] = list(protocol_cf[kind])

        # Route control (2026-09-16). Match rules are tenant-scoped; the route
        # maps themselves live inside each L3Out and therefore arrive through
        # aci_l3outs as pass-through, needing no builder of their own.
        match_rules = _build_match_rules(tenant.get("_custom_field_data") or {})
        if match_rules:
            entry["match_rules"] = match_rules

        vrf_route_leaks = _build_vrf_route_leaks(tenant.get("_custom_field_data") or {})
        if vrf_route_leaks:
            entry["vrf_route_leaks"] = vrf_route_leaks

        services = _build_l4l7_services(tenant.get("_custom_field_data") or {})
        if services:
            entry["services"] = services

        aci_tenants.append(entry)

    result: dict[str, Any] = {"apic": {"tenants": aci_tenants}}

    fabric_policies, access_policies = _build_fabric_and_access_policies(locations or [])
    if fabric_policies:
        result["apic"]["fabric_policies"] = fabric_policies
    if access_policies:
        result["apic"]["access_policies"] = access_policies

    aaa_policies = _build_aaa_policies(locations or [])
    if aaa_policies:
        result["apic"]["aaa_policies"] = aaa_policies

    node_management = _build_node_management(locations or [], devices or [])
    if node_management:
        result["apic"]["node_management"] = node_management

    # Fabric inventory (2026-09-14). Emitted before validation so a failure
    # message can name what inventory actually exists.
    # Policy references are validated unconditionally: unlike node references
    # they need no external inventory to check against, so there is no reason
    # to make it opt-in.
    _validate_interface_policy_references(result)
    _validate_route_control_references(result)
    _validate_access_references(result)
    _validate_fabric_references(result)
    _validate_security_references(result)
    _validate_l3out_depth_references(result)

    inventory = _build_fabric_inventory(devices or [])
    if inventory:
        result["apic"]["fabric_inventory"] = inventory
        if validate_node_references:
            _validate_node_references(result, inventory)

    return result


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

        # ADR-020 Phase A item 1: VRF attribute depth. Custom fields are only
        # emitted when explicitly set in Nautobot -- an unset field means
        # "use the netascode/aci Terraform provider's own ACI default",
        # keeping generated YAML minimal instead of forcing every default
        # value explicitly.
        cf = vrf.get("_custom_field_data") or {}
        if (v := cf.get("aci_ip_data_plane_learning")) is not None:
            entry["ip_data_plane_learning"] = "enabled" if v else "disabled"
        if v := cf.get("aci_policy_control_enforcement_direction"):
            entry["policy_control_enforcement_direction"] = v
        if v := cf.get("aci_policy_control_enforcement_mode"):
            entry["policy_control_enforcement_mode"] = v

        # 2026-10-16 -- L3Out depth: VRF-wide BGP timers, OSPF timers, route tag.
        vrf_policies = cf.get("aci_vrf_protocol_policies") or {}
        for key in VRF_PROTOCOL_POLICY_KEYS:
            if vrf_policies.get(key):
                entry[key] = vrf_policies[key]

        # 2026-10-15 -- vzAny, managed only for VRFs with vzAny intent. Both
        # keys are emitted whenever the field holds a value, even false / {}:
        # once intent was written, clearing it must reach the APIC (preferred
        # group off, relations removed). Absent keys mean "never managed" --
        # Terraform then leaves vzAny alone; it cannot reset it (NS-26).
        if (v := cf.get("aci_vrf_preferred_group")) is not None:
            entry["preferred_group"] = bool(v)
        vzany_cf = cf.get("aci_vzany_contracts")
        if isinstance(vzany_cf, dict):
            entry["vzany"] = {f"{k}_contracts": list(vzany_cf[k]) for k in ("provided", "consumed") if vzany_cf.get(k)}

        result.append(entry)
    return result


def _build_bridge_domains(prefixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for prefix in prefixes:
        network: str = prefix["prefix"]
        description: str = prefix.get("description") or ""

        # Derive bridge-domain name: prefer parsed from description, fall back to
        # a sanitised form of the network address.
        bd_name = _parse_bd_name(description) or _sanitise_prefix_as_bd_name(network)

        # VRF: take the first entry from the vrfs list (one BD has one VRF in ACI)
        vrf_list: list[dict[str, Any]] = prefix.get("vrfs") or []
        vrf_name = vrf_list[0]["name"] if vrf_list else None

        gateway_ip = (prefix.get("_custom_field_data") or {}).get("aci_gateway_ip") or _to_gateway_ip(network)
        if gateway_ip != network:
            # Nautobot has no explicit "this is the gateway" concept for a prefix —
            # it only stores the network address. We assume the first host is the
            # intended ACI BD gateway, which is a common convention but not
            # guaranteed. Surface this clearly rather than guessing silently.
            print(
                f"WARNING: [generator] BD '{bd_name}': prefix {network} has no explicit "
                f"gateway in Nautobot; assuming first host {gateway_ip} as the ACI BD "
                "gateway IP. Verify this matches the intended gateway.",
                file=sys.stderr,
            )

        entry: dict[str, Any] = {"name": bd_name, "unicast_routing": True}
        if " -- no-subnet" not in description:
            # `public` was hardcoded False until 2026-09-16, which meant no BD
            # subnet this platform created could EVER be advertised out of an
            # L3Out -- the transit-routing lab needed exactly that. Driven by
            # the same description convention as the shared scope, and by the
            # aci_bd_subnet_scope Custom Field where one is set.
            scope = (prefix.get("_custom_field_data") or {}).get("aci_bd_subnet_scope") or ""
            is_public = "public" in scope or " -- subnet-scope:public" in description
            is_shared = "shared" in scope or " -- subnet-scope:shared" in description
            entry["subnets"] = [
                {
                    "ip": gateway_ip,
                    "public": is_public,
                    # ACI needs at least one scope flag; private is the default
                    # only when nothing else was asked for.
                    "private": not is_public and not is_shared,
                    "shared": is_shared,
                }
            ]
        if vrf_name:
            entry["vrf"] = vrf_name

        # ADR-020 Phase A item 1: Bridge Domain attribute depth, sourced from
        # the owning Prefix's custom fields (BD identity is derived
        # per-prefix in this generator, so BD-level attributes live there
        # too -- see the module docstring). Same "only emit if set" rule as
        # VRF attributes above.
        cf = prefix.get("_custom_field_data") or {}
        # fvRsBDToOut. A public subnet with no L3Out association is still
        # never advertised, so these two are only useful together.
        if v := cf.get("aci_bd_l3outs"):
            entry["l3outs"] = list(v) if isinstance(v, list) else [v]
        if v := cf.get("aci_bd_mac"):
            entry["mac"] = v
        if (v := cf.get("aci_bd_arp_flooding")) is not None:
            entry["arp_flooding"] = bool(v)
        if (v := cf.get("aci_bd_advertise_host_routes")) is not None:
            entry["advertise_host_routes"] = bool(v)
        if v := cf.get("aci_bd_l2_unknown_unicast"):
            entry["l2_unknown_unicast"] = v
        if v := cf.get("aci_bd_l3_unknown_multicast"):
            entry["l3_unknown_multicast"] = v
        if v := cf.get("aci_bd_multi_destination"):
            entry["multi_destination"] = v
        if v := cf.get("aci_bd_ep_move_detect_mode"):
            entry["ep_move_detect_mode"] = v
        if (v := cf.get("aci_bd_pim")) is not None:
            entry["pim"] = bool(v)

        # A bridge domain may carry SEVERAL subnets. Nautobot models a BD as a
        # Prefix, so two prefixes naming the same BD are two subnets of ONE
        # bridge domain -- not two bridge domains. Appending blindly produced
        # duplicate BD names, which Terraform rejects outright with
        # "Duplicate object key" in local.bridge_domains (the ACI:Sales
        # DB_BD incident, 2026-09-04). Merging here is what makes a
        # multi-subnet BD expressible at all.
        existing = by_name.get(bd_name)
        if existing is None:
            by_name[bd_name] = entry
            result.append(entry)
            continue

        existing.setdefault("subnets", []).extend(entry.get("subnets", []))
        # Union the L3Out associations; a subnet advertised through a
        # different L3Out than its sibling is legitimate.
        if entry.get("l3outs"):
            merged = existing.setdefault("l3outs", [])
            merged.extend(o for o in entry["l3outs"] if o not in merged)
        # Every other BD-level attribute belongs to the bridge domain, not to
        # one of its subnets, so the first prefix that sets one wins and later
        # prefixes only fill gaps. Silently overwriting would make the output
        # depend on Nautobot's row order.
        for key, value in entry.items():
            if key not in ("name", "subnets", "l3outs"):
                existing.setdefault(key, value)
    return result


def _build_application_profiles(vlans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build apic.tenants[].application_profiles[].endpoint_groups[] from a
    tenant's VLANs (ADR-020 Phase A item 2).

    Per that decision, EPGs are represented as Nautobot VLAN objects (no new
    Nautobot plugin/custom model) -- a VLAN is only exported as an EPG when
    both ``aci_application_profile`` and ``aci_epg_bridge_domain`` custom
    fields are explicitly set; VLANs without them are assumed to be
    ordinary IPAM VLANs unrelated to ACI and silently skipped (this keeps
    the feature strictly opt-in, unlike VRF/BD attribute depth which reads
    fields on objects the generator already exports unconditionally).
    """
    aps: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for vlan in vlans:
        cf = vlan.get("_custom_field_data") or {}
        ap_name = cf.get("aci_application_profile")
        bd_name = cf.get("aci_epg_bridge_domain")
        if not ap_name or not bd_name:
            continue

        epg: dict[str, Any] = {"name": vlan["name"], "bridge_domain": bd_name}
        if vlan.get("description"):
            epg["description"] = vlan["description"]
        if cf.get("aci_epg_preferred_group_member"):
            epg["preferred_group_member"] = True

        # ADR-020 Phase A item 3: EPG-level provided/consumed Contract
        # references, stored as a JSON Custom Field on the same VLAN.
        epg_contracts = cf.get("aci_epg_contracts") or {}
        if provided := epg_contracts.get("provided"):
            epg["provided_contracts"] = list(provided)
        if consumed := epg_contracts.get("consumed"):
            epg["consumed_contracts"] = list(consumed)

        # ADR-020 Phase D follow-on: EPG-to-Domain binding (Physical or
        # VMM), stored as a JSON Custom Field on the same VLAN. Each entry
        # must carry an explicit domain_type -- a Physical Domain and a VMM
        # Domain could share the same name, and Terraform needs to resolve
        # against the correct resource map (aci_physical_domain vs.
        # aci_vmm_domain), not guess by name collision. No local validation
        # of resolution_immediacy/deployment_immediacy value strings, same
        # pass-through convention as this function's other fields.
        #
        # Note: copilot/aci-platform-comparison implemented the same
        # concept via separate aci_physical_domains/aci_vmm_domains fields
        # feeding a distinct aci_epg_to_domain Terraform resource. Not
        # ported here deliberately -- running both mechanisms at once would
        # let two different Terraform resources manage the same fvRsDomAtt
        # relation. aci_epg_domains + relation_to_domains (this side) is
        # the one that's live-verified end to end, including over the real
        # MCP protocol; kept as the single canonical path.
        epg_domains = cf.get("aci_epg_domains") or {}
        if domains := epg_domains.get("domains"):
            epg["domains"] = list(domains)

        epg_subnets = cf.get("aci_epg_subnets") or {}
        if subnets := epg_subnets.get("subnets"):
            epg["subnets"] = list(subnets)

        # Ported from copilot/aci-platform-comparison (2026-09-08): EPG
        # static path bindings (port-level, distinct from domain binding
        # above). Feeds main.tf's aci_epg_to_static_path resource, which
        # depends on real per-port `pathep-[...]` DNs this simulator does
        # not have -- see Platform-Status-and-Pending-Items.md.
        if static_paths := cf.get("aci_static_paths"):
            epg["static_paths"] = list(static_paths)

        aps[ap_name].append(epg)

    return [
        {"name": ap_name, "endpoint_groups": epgs}
        for ap_name, epgs in aps.items()
    ]


def _add_endpoint_security_groups(application_profiles: list[dict[str, Any]], tenant_cf: dict[str, Any]) -> None:
    """Place each ESG under its application profile (2026-10-15).

    ESGs are stored on the Tenant (`aci_endpoint_security_groups`), each
    naming its application profile; in the YAML the AP is the parent. An AP
    that holds only ESGs -- no EPG uses it -- is created here, because an ESG
    needs an AP to live in.
    """
    for esg in ((tenant_cf.get("aci_endpoint_security_groups") or {}).get("esgs") or []):
        ap_name = esg.get("application_profile")
        ap = next((a for a in application_profiles if a["name"] == ap_name), None)
        if ap is None:
            ap = {"name": ap_name}
            application_profiles.append(ap)
        ap.setdefault("endpoint_security_groups", []).append(
            {k: v for k, v in esg.items() if k != "application_profile"}
        )


def _build_contracts_and_filters(tenant_cf: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build apic.tenants[].filters[] and apic.tenants[].contracts[] from a
    tenant's ``aci_contracts`` JSON Custom Field (ADR-020 Phase A item 3).

    Contracts/Filters/Subjects have no natural home in Nautobot's existing
    Tenant/VRF/Prefix/VLAN model, so -- per that item's design note -- they
    are read from a single structured JSON field rather than modeled as new
    Nautobot object types. Values are passed through as-is (no local
    validation of e.g. ``scope``/``ether_type`` strings); the netascode/aci
    Terraform provider validates them at plan/apply time, same convention as
    every other attribute this generator emits.
    """
    data = tenant_cf.get("aci_contracts") or {}
    filters = list(data.get("filters") or [])
    contracts = list(data.get("contracts") or [])
    return filters, contracts


def _build_l3outs(tenant_cf: dict[str, Any]) -> list[dict[str, Any]]:
    """Build apic.tenants[].l3outs[] from a tenant's ``aci_l3outs`` JSON
    Custom Field (ADR-020 Phase A item 4, logical-only MVP scope).

    Scope deliberately excludes physical fabric attachment (Logical Node/
    Interface Profiles, routed interfaces, OSPF/BGP protocol config): as of
    this item's implementation, Nautobot's DCIM has zero leaf/spine devices
    synced (only the APIC controller itself), so a real interface path
    (node ID + port) cannot be sourced from actual fabric inventory. This
    emits the L3Out object, its VRF association, External EPGs, and their
    subnets/contract references only -- enough to reserve the L3Out and
    bind Contracts to it, but NOT enough alone to pass external traffic in
    a real APIC without additional manual interface/routing configuration.
    Same pass-through convention as `_build_contracts_and_filters()`: no
    local validation of e.g. ``scope``/``aggregate`` strings.
    """
    data = tenant_cf.get("aci_l3outs") or {}
    l3outs = deepcopy(list(data.get("l3outs") or []))
    for l3out in l3outs:
        for node_profile in l3out.get("node_profiles", []):
            for interface_profile in node_profile.get("interface_profiles", []):
                for interface in interface_profile.get("interfaces", []):
                    # APIC/XML uses "trunk" for an SVI path; the installed
                    # CiscoDevNet/aci provider represents the same path as
                    # mode="regular".
                    if interface.get("mode") == "trunk":
                        interface["mode"] = "regular"
        for epg in l3out.get("external_epgs", []):
            for subnet in epg.get("subnets", []):
                scope = subnet.get("scope", [])
                if "shared-security" in scope and "import-security" not in scope:
                    scope.append("import-security")
    return l3outs


# The five policy kinds an l3extLIfP can reference, and the interface-profile
# key that points at each. Ordered as APIC's own GUI lists them.
INTERFACE_POLICY_KINDS: dict[str, tuple[str, ...]] = {
    "nd_interface_policies": ("nd_interface_policy",),
    "dpp_policies": ("ingress_dpp_policy", "egress_dpp_policy"),
    "pim_interface_policies": ("pim_interface_policy", "pim_v6_interface_policy"),
    "igmp_interface_policies": ("igmp_interface_policy",),
    "custom_qos_policies": ("custom_qos_policy",),
    # 2026-10-16 -- L3Out depth.
    "bfd_interface_policies": ("bfd_interface_policy",),
}

# L3Out depth (2026-10-16): tenant-scoped protocol policies, stored together
# in the `aci_protocol_policies` Custom Field, and the objects that name each.
PROTOCOL_POLICY_KINDS: dict[str, str] = {
    "bgp_timers_policies": "bgp_timers_policy",
    "bgp_best_path_policies": "bgp_best_path_policy",
    "bgp_route_summarization_policies": "bgp_route_summarization_policy",
    "ospf_timers_policies": "ospf_timers_policy",
    "route_tag_policies": "route_tag_policy",
}
VRF_PROTOCOL_POLICY_KEYS = ("bgp_timers_policy", "ospf_timers_policy", "route_tag_policy")


def _build_interface_policies(tenant_cf: dict[str, Any]) -> dict[str, Any]:
    """Build the tenant-scoped L3Out interface policy lists from the
    ``aci_interface_policies`` JSON Custom Field.

    Pass-through, same convention as `_build_contracts_and_filters()`: no
    local validation of attribute value strings, which belong to the
    provider's own enums. Only the list shape is normalised, and a key is
    emitted only when it has entries -- an empty key would make Terraform
    iterate an empty map instead of skipping.
    """
    data = tenant_cf.get("aci_interface_policies") or {}
    out: dict[str, Any] = {}
    for kind in INTERFACE_POLICY_KINDS:
        values = list(data.get(kind) or [])
        if values:
            out[kind] = values
    return out


def _validate_interface_policy_references(data: dict[str, Any]) -> None:
    """Every policy an interface profile names must be declared in the same
    tenant -- or be a literal DN, which is the documented escape hatch for
    pointing at a policy this platform does not manage.

    The reference is by name and the provider turns it into a DN, so a typo
    is invisible until apply time. See PolicyReferenceError.
    """
    problems: list[str] = []

    for tenant in data.get("apic", {}).get("tenants", []):
        tenant_name = tenant.get("name", "?")
        declared = {
            kind: {p.get("name") for p in tenant.get(kind, []) if p.get("name")}
            for kind in INTERFACE_POLICY_KINDS
        }

        for l3out in tenant.get("l3outs", []):
            for node_profile in l3out.get("node_profiles", []):
                for profile in node_profile.get("interface_profiles", []):
                    for kind, ref_keys in INTERFACE_POLICY_KINDS.items():
                        for ref_key in ref_keys:
                            ref = profile.get(ref_key)
                            # A literal DN is passed straight to APIC by
                            # main.tf and cannot be checked against anything
                            # this generator knows about.
                            if not ref or str(ref).startswith("uni/"):
                                continue
                            if ref not in declared[kind]:
                                known = ", ".join(sorted(declared[kind])) or "none"
                                problems.append(
                                    f"tenant '{tenant_name}' L3Out '{l3out.get('name')}' "
                                    f"interface profile '{profile.get('name')}': "
                                    f"{ref_key}='{ref}' is not declared in this tenant's "
                                    f"{kind} (declared: {known})"
                                )

    if problems:
        raise PolicyReferenceError(
            "L3Out interface profile references a policy that does not exist:\n  - "
            + "\n  - ".join(problems)
            + "\n\nDeclare the policy in the same tenant, or use a full 'uni/...' DN "
            "to point at one this platform does not manage. To inherit APIC's "
            "built-in default, omit the field entirely -- the literal string "
            "'default' is NOT valid and fails at apply time."
        )


def _build_match_rules(tenant_cf: dict[str, Any]) -> list[dict[str, Any]]:
    """Build tenant-scoped route-map match rules from the
    ``aci_route_control`` JSON Custom Field.

    Only the match RULES are tenant-scoped. A route map (``rtctrlProfile``)
    hangs off an L3Out, so it travels inside ``aci_l3outs`` and needs no
    builder here -- `_build_l3outs()` already passes unknown keys through.
    """
    data = tenant_cf.get("aci_route_control") or {}
    return list(data.get("match_rules") or [])


def _validate_route_control_references(data: dict[str, Any]) -> None:
    """Every match rule a route-map context names must exist in the same
    tenant, and every route map an external EPG binds must exist in the same
    L3Out.

    Both are name references that APIC resolves late. A context pointing at a
    match rule that does not exist produces a route map entry matching
    nothing, which in a map whose last word is an implicit deny means
    *silently dropping every route* -- no error, no fault, just no
    advertisement. That is worth failing the pipeline over.
    """
    problems: list[str] = []

    for tenant in data.get("apic", {}).get("tenants", []):
        tenant_name = tenant.get("name", "?")
        declared_rules = {r.get("name") for r in tenant.get("match_rules", []) if r.get("name")}

        for l3out in tenant.get("l3outs", []):
            l3out_name = l3out.get("name", "?")
            profiles = l3out.get("route_control_profiles", []) or []
            declared_profiles = {p.get("name") for p in profiles if p.get("name")}

            for profile in profiles:
                for ctx in profile.get("contexts", []) or []:
                    rule = ctx.get("match_rule")
                    if not rule:
                        continue
                    if rule not in declared_rules:
                        known = ", ".join(sorted(declared_rules)) or "none"
                        problems.append(
                            f"tenant '{tenant_name}' L3Out '{l3out_name}' route map "
                            f"'{profile.get('name')}' context '{ctx.get('name')}': "
                            f"match_rule='{rule}' is not declared in this tenant's "
                            f"match_rules (declared: {known})"
                        )

            for epg in l3out.get("external_epgs", []):
                for binding in epg.get("route_control_profiles", []) or []:
                    name = binding.get("name")
                    if name and name not in declared_profiles:
                        known = ", ".join(sorted(declared_profiles)) or "none"
                        problems.append(
                            f"tenant '{tenant_name}' L3Out '{l3out_name}' external EPG "
                            f"'{epg.get('name')}' binds route map '{name}', which is not "
                            f"declared in this L3Out (declared: {known})"
                        )

    for tenant in data.get("apic", {}).get("tenants", []):
        tenant_name = tenant.get("name", "?")
        declared_l3outs = {o.get("name") for o in tenant.get("l3outs", []) if o.get("name")}
        for bd in tenant.get("bridge_domains", []):
            for ref in bd.get("l3outs", []) or []:
                if ref not in declared_l3outs:
                    known = ", ".join(sorted(declared_l3outs)) or "none"
                    problems.append(
                        f"tenant '{tenant_name}' bridge domain '{bd.get('name')}' is "
                        f"associated with L3Out '{ref}', which is not declared in this "
                        f"tenant (declared: {known})"
                    )

    if problems:
        raise PolicyReferenceError(
            "route control references something that does not exist:\n  - "
            + "\n  - ".join(problems)
            + "\n\nA context whose match rule is missing matches nothing, and an "
            "ACI route map ends in an implicit deny -- so the result is silently "
            "advertising no routes at all, with no error and no fault."
        )


def _build_vrf_route_leaks(tenant_cf: dict[str, Any]) -> list[dict[str, Any]]:
    """Build tenant ``vrf_route_leaks`` from the ``aci_vrf_route_leaks``
    JSON Custom Field.

    ``source_vrf`` is retained in the generated intent for auditability and
    validation, while the installed CiscoDevNet/aci provider resource accepts
    the destination VRF and leaked subnet only.
    """
    data = tenant_cf.get("aci_vrf_route_leaks") or {}
    return list(data.get("route_leaks") or [])


def _build_l4l7_services(tenant_cf: dict[str, Any]) -> dict[str, Any]:
    """Build tenant ``services`` from the ``aci_l4l7_services`` JSON
    Custom Field.

    L4-L7 devices, service graphs, and PBR redirect policies are tenant
    scoped ACI objects without a natural first-class Nautobot equivalent,
    so they follow the existing Contract/L3Out Custom-Field-JSON pattern.

    `health_groups` and `ip_sla_policies` (2026-09-15) back the PBR
    resilience objects: a redirect policy with no health tracking fails
    closed the moment its destination dies, silently black-holing the
    redirected traffic.

    Concrete device discovery remains out of scope -- but note that the
    earlier claim here, that the installed provider has no concrete device
    resources, was wrong: `aci_concrete_device` and `aci_concrete_interface`
    both exist in CiscoDevNet/aci v2.20.0. Excluding them is a scope choice
    (they need real vCenter VM identities), not a provider limitation.
    """
    data = tenant_cf.get("aci_l4l7_services") or {}
    services: dict[str, Any] = {}
    for key in ("devices", "service_graphs", "redirect_policies", "health_groups", "ip_sla_policies"):
        values = list(data.get(key) or [])
        if values:
            services[key] = values
    return services


def _build_fabric_and_access_policies(
    locations: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build apic.fabric_policies and apic.access_policies from each
    Location's ``aci_fabric_policies`` JSON Custom Field (ADR-020 Phase B,
    logical-only scope; Phase C adds POD-wide NTP/DNS/SNMP; Phase D adds
    VMware VMM Domains).

    VLAN Pools/Physical Domains/AEPs/Leaf Interface Policy Groups are
    fabric-wide (not Tenant-scoped) objects with no natural Nautobot home,
    so -- same Custom-Field-JSON approach as Phase A items 3-4 -- they live
    on the Location representing the ACI fabric/site rather than a new
    Nautobot model. Aggregated across all Locations that have the field set
    (multi-site safe, though this lab only has one). This function's own
    scope is logical-only: it does not model physical port/interface
    binding. That was an MVP scope choice -- the physical hierarchy
    (access-port profiles/selectors/blocks, leaf profiles/selectors/node
    blocks) is emitted further down via the `leaf_interface_profiles`/
    `interface_selectors`/`access_port_profiles`/`leaf_profiles` keys.

    CORRECTED 2026-09-14: this docstring previously justified the exclusion
    by stating physical binding is impossible because "this simulator has
    zero real leaf/spine interface data available". The premise is true but
    the conclusion is not -- ACI relations are late-binding, and the APIC
    accepts a port hierarchy naming a leaf that does not exist, storing it
    with the relation unresolved. Configuration works; deployment and
    operational verification do not. See ADR-020's 2026-09-14 correction.

    Same pass-through convention as
    `_build_contracts_and_filters()`/`_build_l3outs()`: no local validation
    of value strings.

    Phase C's `ntp`/`dns`/`snmp` keys target ACI's real singleton default
    POD policies (`uni/fabric/time-default`, `uni/fabric/dnsp-default`,
    `uni/fabric/snmppol-default`) -- confirmed via direct APIC queries
    against the real simulator (not guessed), including live-creating and
    deleting a real `datetimeNtpProv`/`dnsProv`/`dnsDomain` to confirm their
    exact attribute names. Scoped to the single default POD Policy Group
    only (this lab has one POD) -- custom-named alternate policies with
    explicit POD Policy Group assignment are out of scope.

    Phase D's `vmm_domains` key models VMM Domain integration (VMware only
    for this MVP): the VMM Domain object, its Controller (vCenter host/
    datacenter association), and an optional VLAN Pool binding. The
    Controller's actual vCenter username/password are deliberately NOT part
    of this Custom Field or the generated YAML -- same as the APIC's own
    `aci_username`/`aci_password`, they are supplied at `terraform apply`
    time via sensitive Terraform variables (`vmm_vcenter_username`/
    `vmm_vcenter_password`), never persisted in Nautobot or committed YAML.

    Phase E's `coop`/`isis` keys are singletons, same semantics as `ntp`/
    `dns`/`snmp` -- they target ACI's real mandatory default fabric-wide
    policies (`uni/fabric/pol-default` for COOP Group Policy, `uni/fabric/
    isisDomP-default` for ISIS Domain Policy), confirmed via direct APIC
    queries. `pod_policy_groups` is list-shaped (like `vlan_pools`/
    `aeps`/etc.): named Pod Policy Groups are purely additive objects with
    no default instance, so no destroy-safety concern applies to them the
    way it does to the singleton keys.

    Phase G's `fault_lifecycle`/`syslog_system_msg`/`syslog_rate_limit`
    keys are singletons too, targeting real mandatory default objects
    confirmed via direct APIC queries under `uni/fabric/moncommon` (the
    fabric's Common Monitoring Policy, distinct from Phase C/E's
    `monfab-default`): Fault Lifecycle Policy at `moncommon/flcp-generic`,
    Syslog System Message Policy at `moncommon/sysmsgp`, Syslog Rate Limit
    Policy at `moncommon/ratelimitp`.
    """
    vlan_pools: list[dict[str, Any]] = []
    physical_domains: list[dict[str, Any]] = []
    l3_domains: list[dict[str, Any]] = []
    aeps: list[dict[str, Any]] = []
    leaf_interface_policy_groups: list[dict[str, Any]] = []
    # Port-channel / vPC (2026-10-12).
    lacp_policies: list[dict[str, Any]] = []
    vpc_domains: list[dict[str, Any]] = []
    pc_vpc_policy_groups: list[dict[str, Any]] = []
    vmm_domains: list[dict[str, Any]] = []
    pod_policy_groups: list[dict[str, Any]] = []
    ntp: dict[str, Any] = {}
    dns: dict[str, Any] = {}
    snmp: dict[str, Any] = {}
    coop: dict[str, Any] = {}
    isis: dict[str, Any] = {}
    fault_lifecycle: dict[str, Any] = {}
    syslog_system_msg: dict[str, Any] = {}
    syslog_rate_limit: dict[str, Any] = {}
    bgp_route_reflector: dict[str, Any] = {}
    pod_profile: dict[str, Any] = {}

    for location in locations:
        cf = location.get("_custom_field_data") or {}
        data = cf.get("aci_fabric_policies") or {}
        vlan_pools.extend(data.get("vlan_pools") or [])
        physical_domains.extend(data.get("physical_domains") or [])
        # L3 (external routed) domains. Distinct from physical domains: an
        # L3Out's interface attaches through one of these, and its VLAN pool
        # is what makes the L3Out's encap VLAN legal.
        l3_domains.extend(data.get("l3_domains") or [])
        aeps.extend(data.get("aeps") or [])
        leaf_interface_policy_groups.extend(data.get("leaf_interface_policy_groups") or [])
        lacp_policies.extend(data.get("lacp_policies") or [])
        vpc_domains.extend(data.get("vpc_domains") or [])
        pc_vpc_policy_groups.extend(data.get("pc_vpc_policy_groups") or [])
        vmm_domains.extend(data.get("vmm_domains") or [])
        pod_policy_groups.extend(data.get("pod_policy_groups") or [])
        # POD-wide policies are singletons -- last Location with the field
        # set wins, rather than merged/appended like the list-shaped keys
        # above (multiple Locations setting conflicting NTP/DNS/SNMP config
        # would be a real modeling conflict, not a valid multi-site case).
        if data.get("ntp"):
            ntp = data["ntp"]
        if data.get("dns"):
            dns = data["dns"]
        if data.get("snmp"):
            snmp = data["snmp"]
        if data.get("coop"):
            coop = data["coop"]
        if data.get("isis"):
            isis = data["isis"]
        if data.get("fault_lifecycle"):
            fault_lifecycle = data["fault_lifecycle"]
        if data.get("syslog_system_msg"):
            syslog_system_msg = data["syslog_system_msg"]
        if data.get("syslog_rate_limit"):
            syslog_rate_limit = data["syslog_rate_limit"]
        # 2026-10-14: the fabric AS + spine route reflectors
        # (uni/fabric/bgpInstP-default) and the Pod Policy Group assigned to
        # the default pod selector -- singletons, same rule.
        if data.get("bgp_route_reflector"):
            bgp_route_reflector = data["bgp_route_reflector"]
        if data.get("pod_profile"):
            pod_profile = data["pod_profile"]

    fabric_policies: dict[str, Any] = {}
    if vlan_pools:
        fabric_policies["vlan_pools"] = vlan_pools
    if vmm_domains:
        fabric_policies["vmm_domains"] = vmm_domains
    if ntp:
        fabric_policies["ntp"] = ntp
    if dns:
        fabric_policies["dns"] = dns
    if snmp:
        fabric_policies["snmp"] = snmp
    if coop:
        fabric_policies["coop"] = coop
    if isis:
        fabric_policies["isis"] = isis
    if pod_policy_groups:
        fabric_policies["pod_policy_groups"] = pod_policy_groups
    if fault_lifecycle:
        fabric_policies["fault_lifecycle"] = fault_lifecycle
    if syslog_system_msg:
        fabric_policies["syslog_system_msg"] = syslog_system_msg
    if syslog_rate_limit:
        fabric_policies["syslog_rate_limit"] = syslog_rate_limit
    if bgp_route_reflector:
        fabric_policies["bgp_route_reflector"] = bgp_route_reflector
    if pod_profile:
        fabric_policies["pod_profile"] = pod_profile

    access_policies: dict[str, Any] = {}
    if physical_domains:
        access_policies["physical_domains"] = physical_domains
    if l3_domains:
        access_policies["l3_domains"] = l3_domains
    if aeps:
        access_policies["aeps"] = aeps
    if leaf_interface_policy_groups:
        access_policies["leaf_interface_policy_groups"] = leaf_interface_policy_groups
    if lacp_policies:
        access_policies["lacp_policies"] = lacp_policies
    if vpc_domains:
        access_policies["vpc_domains"] = vpc_domains
    if pc_vpc_policy_groups:
        access_policies["pc_vpc_policy_groups"] = pc_vpc_policy_groups
    for key in ("leaf_interface_profiles", "interface_selectors", "access_port_profiles", "leaf_profiles"):
        values = []
        for location in locations:
            data = (location.get("_custom_field_data") or {}).get("aci_fabric_policies") or {}
            values.extend(data.get(key) or [])
        if values:
            access_policies[key] = values

    return fabric_policies, access_policies


def _build_aaa_policies(locations: list[dict[str, Any]]) -> dict[str, Any]:
    """Build apic.aaa_policies from each Location's ``aci_aaa_policies`` JSON
    Custom Field (ADR-020 Phase F -- RBAC/Security Domains/Local Users).

    Deliberately a separate Custom Field from `aci_fabric_policies`, not a
    new key within it: Security Domains/Local Users live under the APIC's
    `uni/userext` subtree (platform administration/AAA), a genuinely
    different part of the ACI MIT from `uni/fabric` (network/tenant
    policy) -- keeping them in a separate field avoids conflating two
    unrelated concerns in one ever-growing JSON blob.

    Both `security_domains` and `local_users` are purely additive named
    objects with no default/mandatory instance in a fresh fabric (unlike
    Phase C/E's fabric-wide singletons), so -- same convention as
    `vlan_pools`/`aeps`/Phase E's `pod_policy_groups` -- they are list-
    shaped and aggregated across all Locations that have the field set.
    Local User passwords are deliberately NOT part of this Custom Field or
    the generated YAML -- same convention as Phase D's VMM Controller
    credentials -- supplied at `terraform apply` time via a sensitive
    `local_user_passwords` map variable, keyed by username, never
    persisted in Nautobot or committed YAML.
    """
    security_domains: list[dict[str, Any]] = []
    local_users: list[dict[str, Any]] = []

    for location in locations:
        cf = location.get("_custom_field_data") or {}
        data = cf.get("aci_aaa_policies") or {}
        security_domains.extend(data.get("security_domains") or [])
        local_users.extend(data.get("local_users") or [])

    aaa_policies: dict[str, Any] = {}
    if security_domains:
        aaa_policies["security_domains"] = security_domains
    if local_users:
        aaa_policies["local_users"] = local_users

    return aaa_policies


def _build_fabric_inventory(devices: list[dict[str, Any]]) -> dict[str, Any]:
    """Build apic.fabric_inventory from Nautobot DCIM Devices.

    A Device is only treated as a fabric switch when its role is `leaf` or
    `spine` AND it carries an `aci_node_id` -- strictly opt-in, same rule
    as EPG-from-VLAN. An APIC controller, a jump host, or any other Device
    in the same Nautobot instance is therefore ignored rather than
    misinterpreted as a switch.

    `pod_id` defaults to 1 when unset. That default is safe for a
    single-pod fabric and is exactly what the generator assumed implicitly
    before inventory existed; a multi-pod fabric must set it explicitly,
    which `create_fabric_device` can now do.

    Interfaces are carried through so a future increment can validate
    port references (`eth1/4`) as well as node references. Nothing
    validates ports yet -- a Device with no modeled Interfaces is normal
    and is not an error.
    """
    nodes: list[dict[str, Any]] = []

    for device in devices:
        role = ((device.get("role") or {}).get("name") or "").lower()
        if role not in ("leaf", "spine"):
            continue

        cf = device.get("_custom_field_data") or {}
        node_id = cf.get("aci_node_id")
        if node_id is None:
            print(
                f"WARNING: [generator] device '{device.get('name')}' has role "
                f"'{role}' but no aci_node_id Custom Field set -- excluded from "
                "fabric inventory. Any path DN referencing it will fail validation.",
                file=sys.stderr,
            )
            continue

        entry: dict[str, Any] = {
            "name": device.get("name"),
            "node_id": int(node_id),
            "pod_id": int(cf.get("aci_pod_id") or 1),
            "role": role,
        }
        if device.get("serial"):
            entry["serial"] = device["serial"]
        if model := (device.get("device_type") or {}).get("model"):
            entry["model"] = model

        interfaces = [
            {"name": i["name"], "enabled": i.get("enabled", True)}
            for i in (device.get("interfaces") or [])
            if i.get("name")
        ]
        if interfaces:
            entry["interfaces"] = interfaces

        nodes.append(entry)

    if not nodes:
        return {}

    # Sorted by node_id so output is deterministic regardless of the order
    # Nautobot returns Devices in -- the pipeline's generate_nac job runs the
    # generator twice and diffs the results, so any unstable ordering here
    # would fail that gate.
    nodes.sort(key=lambda n: n["node_id"])
    return {"nodes": nodes}


def _collect_node_references(data: dict[str, Any]) -> list[tuple[int, str]]:
    """Walk generated intent and return every (node_id, where) reference.

    Covers the three places a node ID can legitimately appear: EPG static
    path bindings, L3Out logical nodes, and L3Out interfaces.
    """
    references: list[tuple[int, str]] = []

    for tenant in data.get("apic", {}).get("tenants", []):
        tenant_name = tenant.get("name", "?")

        for ap in tenant.get("application_profiles", []):
            for epg in ap.get("endpoint_groups", []):
                for path in epg.get("static_paths", []):
                    for key in ("node_id", "node_id2"):
                        if (node_id := path.get(key)) is not None:
                            references.append(
                                (int(node_id), f"tenant '{tenant_name}' EPG '{epg.get('name')}' static path")
                            )

        # L4-L7 concrete interfaces resolve to the same
        # topology/pod-N/paths-M/... DN as a static path, so they get the
        # same inventory validation -- a typo here is just as silent.
        for device in (tenant.get("services") or {}).get("devices", []):
            for cdev in device.get("concrete_devices", []):
                for interface in cdev.get("interfaces", []):
                    if (node_id := interface.get("node_id")) is not None:
                        references.append(
                            (int(node_id), f"tenant '{tenant_name}' L4-L7 device '{device.get('name')}' concrete interface '{interface.get('name')}'")
                        )

        for l3out in tenant.get("l3outs", []):
            l3out_name = l3out.get("name", "?")
            for node_profile in l3out.get("node_profiles", []):
                for node in node_profile.get("nodes", []):
                    if (node_id := node.get("node_id")) is not None:
                        references.append(
                            (int(node_id), f"tenant '{tenant_name}' L3Out '{l3out_name}' node profile '{node_profile.get('name')}'")
                        )
                for interface_profile in node_profile.get("interface_profiles", []):
                    for interface in interface_profile.get("interfaces", []):
                        # node_id2: the second leaf of a vPC SVI (2026-10-16).
                        for key in ("node_id", "node_id2"):
                            if (node_id := interface.get(key)) is not None:
                                references.append(
                                    (int(node_id), f"tenant '{tenant_name}' L3Out '{l3out_name}' interface profile '{interface_profile.get('name')}'")
                                )

    # A vPC domain names both its leaves; a typo pairs a real leaf with one
    # that does not exist, and APIC accepts the protection group regardless.
    for domain in (data.get("apic", {}).get("access_policies") or {}).get("vpc_domains", []):
        for key in ("node1", "node2"):
            if (node_id := domain.get(key)) is not None:
                references.append((int(node_id), f"vPC domain '{domain.get('name')}'"))

    for node in _route_reflector_nodes(data):
        references.append((int(node["node_id"]), "BGP route reflector policy"))

    return references


def _route_reflector_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    fabric = data.get("apic", {}).get("fabric_policies") or {}
    return [n for n in (fabric.get("bgp_route_reflector") or {}).get("nodes", []) if n.get("node_id") is not None]


def _validate_node_references(data: dict[str, Any], inventory: dict[str, Any]) -> None:
    """Fail generation if intent references a node absent from inventory.

    This is the whole point of modeling fabric inventory in Nautobot. The
    APIC accepts a path DN naming a switch that does not exist and leaves
    the relation `unformed` -- no error is raised anywhere downstream, so
    without this check a typo'd node ID is invisible until someone
    manually inspects relation state on the APIC.
    """
    known = {node["node_id"]: node for node in inventory.get("nodes", [])}
    unknown = [(node_id, where) for node_id, where in _collect_node_references(data) if node_id not in known]
    if not unknown:
        # Only spines can reflect routes. APIC accepts a leaf (or anything
        # else) with HTTP 200 and then raises F1893 under
        # bgpInstP-default/rr/node-N -- verified live 2026-10-14.
        not_spines = [
            f"node {n['node_id']} ({known[int(n['node_id'])]['name']}) is a {known[int(n['node_id'])]['role']}"
            for n in _route_reflector_nodes(data)
            if known[int(n["node_id"])].get("role") != "spine"
        ]
        if not_spines:
            raise FabricInventoryError(
                "BGP route reflector policy names switches that are not spines: " + "; ".join(not_spines) +
                ". Only spines can be BGP route reflectors -- APIC would accept this and raise fault F1893."
            )
        return

    roster = ", ".join(
        f"{n['node_id']} ({n['name']}, {n['role']})" for n in inventory.get("nodes", [])
    ) or "(inventory is empty)"
    details = "\n".join(f"  - node {node_id} referenced by {where}" for node_id, where in sorted(set(unknown)))
    raise FabricInventoryError(
        f"Intent references {len(set(unknown))} fabric node(s) not present in Nautobot DCIM inventory:\n"
        f"{details}\n"
        f"Known fabric nodes: {roster}.\n"
        "Add the missing switch to Nautobot (MCP tool `create_fabric_device`, or Nautobot DCIM directly, "
        "setting the aci_node_id/aci_pod_id Custom Fields) or correct the node ID in the referencing intent. "
        "The APIC would accept this DN and silently leave the relation unformed, so this is caught here on purpose."
    )


def _build_node_management(
    locations: list[dict[str, Any]], devices: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build apic.node_management: in-band management EPGs (Location JSON)
    and static node management addresses (2026-10-12).

    An address is a native Nautobot IP Address on a fabric switch's
    interface, and only counts when it carries `aci_mgmt_type` -- any other
    IP on the switch is ordinary IPAM and is ignored, the same opt-in rule as
    EPG-from-VLAN. The node and pod come from the switch itself, so the
    address can never name a node that is not in inventory.

    Out-of-band addresses always attach to APIC's built-in OOB EPG
    `uni/tn-mgmt/mgmtp-default/oob-default`, which this platform never
    manages; in-band addresses name an EPG declared in `inband_mgmt_epgs`.
    """
    inband_epgs: list[dict[str, Any]] = []
    for location in locations:
        data = (location.get("_custom_field_data") or {}).get("aci_fabric_policies") or {}
        inband_epgs.extend(data.get("inband_mgmt_epgs") or [])

    addresses: list[dict[str, Any]] = []
    for device in devices:
        cf = device.get("_custom_field_data") or {}
        if cf.get("aci_node_id") is None:
            continue
        for interface in device.get("interfaces") or []:
            for ip in interface.get("ip_addresses") or []:
                ip_cf = ip.get("_custom_field_data") or {}
                mgmt_type = ip_cf.get("aci_mgmt_type")
                if not mgmt_type:
                    continue
                entry: dict[str, Any] = {
                    "node_id": int(cf["aci_node_id"]),
                    "pod_id": int(cf.get("aci_pod_id") or 1),
                    "type": mgmt_type,
                    "address": ip["address"],
                }
                if ip_cf.get("aci_mgmt_gateway"):
                    entry["gateway"] = ip_cf["aci_mgmt_gateway"]
                if mgmt_type == "in_band":
                    entry["epg"] = ip_cf.get("aci_mgmt_epg")
                addresses.append(entry)

    result: dict[str, Any] = {}
    if inband_epgs:
        result["inband_epgs"] = inband_epgs
    if addresses:
        result["static_addresses"] = sorted(addresses, key=lambda a: (a["node_id"], a["type"]))
    return result


def _validate_l3out_depth_references(data: dict[str, Any]) -> None:
    """L3Out depth references (2026-10-16).

    Every protocol policy a VRF, L3Out or external EPG subnet names must be
    declared in the same tenant (Terraform resolves them by key: an unknown
    name is a plan error that names nothing useful). BGP timers / best path on
    a non-BGP L3Out would be silently ignored -- there is no BGP protocol
    profile to carry them. A vPC SVI needs both side addresses, a VLAN, a
    vPC policy group and a vPC domain pairing its two leaves; and duplicate
    static routes or loopbacks on one node collide as Terraform keys.
    """
    apic = data.get("apic", {})
    access = apic.get("access_policies") or {}
    bundles = {g.get("name"): g for g in access.get("pc_vpc_policy_groups", [])}
    pairs = {frozenset((int(d.get("node1", 0)), int(d.get("node2", 0)))) for d in access.get("vpc_domains", [])}
    problems: list[str] = []

    for tenant in apic.get("tenants", []):
        declared = {ref: {p.get("name") for p in tenant.get(kind, [])} for kind, ref in PROTOCOL_POLICY_KINDS.items()}

        for vrf in tenant.get("vrfs", []):
            for key in VRF_PROTOCOL_POLICY_KEYS:
                if vrf.get(key) and vrf[key] not in declared[key]:
                    problems.append(f"VRF '{vrf['name']}' names undeclared {key} '{vrf[key]}'")

        for l3out in tenant.get("l3outs", []):
            name = l3out.get("name")
            bgp_refs = [k for k in ("bgp_timers_policy", "bgp_best_path_policy") if l3out.get(k)]
            for key in bgp_refs:
                if l3out[key] not in declared[key]:
                    problems.append(f"L3Out '{name}' names undeclared {key} '{l3out[key]}'")
            if bgp_refs and l3out.get("protocol") != "bgp":
                problems.append(
                    f"L3Out '{name}' sets bgp_timers_policy / bgp_best_path_policy but is not a BGP L3Out "
                    f"(protocol '{l3out.get('protocol')}') -- nothing would carry them"
                )
            for epg in l3out.get("external_epgs", []):
                for subnet in epg.get("subnets", []):
                    ref = subnet.get("bgp_route_summarization_policy")
                    if ref and ref not in declared["bgp_route_summarization_policy"]:
                        problems.append(
                            f"subnet {subnet.get('ip')} of external EPG '{epg.get('name')}' (L3Out '{name}') names "
                            f"undeclared bgp_route_summarization_policy '{ref}'"
                        )
            for node_profile in l3out.get("node_profiles", []):
                for node in node_profile.get("nodes", []):
                    nid = node.get("node_id")
                    for label, items, key in (("static route", node.get("static_routes", []), "prefix"),
                                              ("loopback", node.get("loopbacks", []), "ip")):
                        values = [i.get(key) for i in items]
                        for dup in sorted({v for v in values if values.count(v) > 1}):
                            problems.append(f"L3Out '{name}': {label} {dup} is declared twice on node {nid}")
                    for route in node.get("static_routes", []):
                        hops = [h.get("ip") for h in route.get("next_hops", [])]
                        for dup in sorted({h for h in hops if hops.count(h) > 1}):
                            problems.append(f"L3Out '{name}': next hop {dup} is declared twice on static route {route.get('prefix')}")
                for profile in node_profile.get("interface_profiles", []):
                    for iface in profile.get("interfaces", []):
                        if iface.get("path_type", "port") != "vpc":
                            continue
                        pair = [int(iface.get("node_id", 0)), int(iface.get("node_id2", 0))]
                        where = f"L3Out '{name}' vPC interface on nodes {sorted(pair)}"
                        if not iface.get("svi"):
                            problems.append(f"{where}: a vPC L3Out interface must be an SVI (svi: true)")
                        if not iface.get("vlan"):
                            problems.append(f"{where}: an SVI needs a vlan")
                        if not (iface.get("side_a_ip") and iface.get("side_b_ip")):
                            problems.append(f"{where}: needs side_a_ip and side_b_ip -- one address per leaf")
                        group = bundles.get(iface.get("policy_group"))
                        if group is None:
                            problems.append(f"{where}: undeclared PC/vPC policy group '{iface.get('policy_group')}'")
                        elif group.get("bundle_type") != "vpc":
                            problems.append(f"{where}: policy group '{iface.get('policy_group')}' is not a vPC policy group")
                        if frozenset(pair) not in pairs:
                            problems.append(f"{where}: no vPC domain pairs them")

    if problems:
        raise PolicyReferenceError(
            "L3Out depth references do not resolve:\n" + "\n".join(f"  - {p}" for p in problems)
        )


def _validate_security_references(data: dict[str, Any]) -> None:
    """ESG and vzAny references (2026-10-15).

    Each is fatal here, naming the offender. APIC 6.2 rejects an EPG selected
    from another VRF or by two ESGs, and one IP subnet or tag selector in two
    ESGs of a VRF, with HTTP 400 at apply time -- failing the pipeline part-
    way through (probed 2026-10-15). An ESG in a VRF Terraform does not manage
    fails the plan; a missing contract likewise.

    Preferred-group members in a VRF whose preferred group is off only WARN:
    that is NS-01's old trap (membership with no effect), and a legitimate
    intermediate state while a design is being built.
    """
    problems: list[str] = []
    for tenant in data.get("apic", {}).get("tenants", []):
        vrfs = {v["name"]: v for v in tenant.get("vrfs", [])}
        contracts = {c.get("name") for c in tenant.get("contracts", [])}
        scopes = {c.get("name"): c.get("scope") or "context" for c in tenant.get("contracts", [])}
        bd_vrf = {bd["name"]: bd.get("vrf") for bd in tenant.get("bridge_domains", [])}
        epg_vrf: dict[str, str | None] = {}
        preferred: list[tuple[str, str | None]] = []
        for ap in tenant.get("application_profiles", []):
            for epg in ap.get("endpoint_groups", []):
                epg_vrf[f"{ap['name']}/{epg['name']}"] = bd_vrf.get(epg.get("bridge_domain"))
                if epg.get("preferred_group_member"):
                    preferred.append((f"EPG '{ap['name']}/{epg['name']}'", bd_vrf.get(epg.get("bridge_domain"))))

        for vrf in vrfs.values():
            for key, verb in (("provided_contracts", "provides"), ("consumed_contracts", "consumes")):
                for c in (vrf.get("vzany") or {}).get(key, []):
                    if c not in contracts:
                        problems.append(f"vzAny of VRF '{vrf['name']}' {verb} undeclared contract '{c}'")
                    elif key == "provided_contracts" and scopes[c] != "context":
                        # APIC 6.2: HTTP 400 at apply (probed 2026-10-15).
                        problems.append(
                            f"vzAny of VRF '{vrf['name']}' provides contract '{c}' with scope '{scopes[c]}' -- "
                            "vzAny can only provide 'context' (VRF) scoped contracts"
                        )

        selected_epgs: dict[str, list[str]] = defaultdict(list)
        selected_subnets: dict[tuple, list[str]] = defaultdict(list)
        selected_tags: dict[tuple, list[str]] = defaultdict(list)
        for ap in tenant.get("application_profiles", []):
            seen: set[str] = set()
            for esg in ap.get("endpoint_security_groups", []):
                name, vrf = esg.get("name"), esg.get("vrf")
                if name in seen:
                    problems.append(f"ESG '{name}' is declared twice in application profile '{ap['name']}'")
                seen.add(name)
                if vrf not in vrfs:
                    problems.append(f"ESG '{name}' is in undeclared VRF '{vrf}'")
                if esg.get("preferred_group_member"):
                    preferred.append((f"ESG '{name}'", vrf))
                for key, verb in (("provided_contracts", "provides"), ("consumed_contracts", "consumes")):
                    for c in esg.get(key, []):
                        if c not in contracts:
                            problems.append(f"ESG '{name}' {verb} undeclared contract '{c}'")
                for sel in esg.get("epg_selectors", []):
                    ref = f"{sel.get('application_profile')}/{sel.get('endpoint_group')}"
                    selected_epgs[ref].append(name)
                    if ref not in epg_vrf:
                        problems.append(f"ESG '{name}' selects undeclared EPG '{ref}'")
                    elif epg_vrf[ref] is not None and epg_vrf[ref] != vrf:
                        problems.append(
                            f"ESG '{name}' (VRF '{vrf}') selects EPG '{ref}', whose bridge domain is in VRF "
                            f"'{epg_vrf[ref]}' -- an ESG can only select endpoints in its own VRF"
                        )
                for sel in esg.get("ip_subnet_selectors", []):
                    selected_subnets[(vrf, sel.get("value"))].append(name)
                for sel in esg.get("tag_selectors", []):
                    selected_tags[(vrf, f"{sel.get('key')}={sel.get('value')}")].append(name)

        for ref, names in selected_epgs.items():
            if len(names) > 1:
                problems.append(f"EPG '{ref}' is selected by more than one ESG: {', '.join(names)}")
        for (vrf, subnet), names in selected_subnets.items():
            if len(names) > 1:
                problems.append(f"IP subnet {subnet} is selected by more than one ESG in VRF '{vrf}': {', '.join(names)}")
        for (vrf, tag), names in selected_tags.items():
            if len(names) > 1:
                problems.append(f"tag selector {tag} is in more than one ESG in VRF '{vrf}': {', '.join(names)}")

        for what, vrf in preferred:
            if vrf in vrfs and not vrfs[vrf].get("preferred_group"):
                print(
                    f"WARNING: [generator] tenant '{tenant.get('name')}': {what} is a preferred-group member, but "
                    f"VRF '{vrf}' does not enable its preferred group -- the membership has no effect until it does "
                    "(update_vrf preferred_group=true).",
                    file=sys.stderr,
                )

    if problems:
        raise PolicyReferenceError(
            "ESG / vzAny references do not resolve:\n" + "\n".join(f"  - {p}" for p in problems)
        )


def _validate_fabric_references(data: dict[str, Any]) -> None:
    """BGP route reflector policy and pod profile references (2026-10-14).

    Both are accepted by APIC and do nothing: route-reflector nodes with no
    fabric AS run no MP-BGP, and a pod selector naming a Pod Policy Group
    that does not exist leaves the relation unresolved.
    """
    fabric = data.get("apic", {}).get("fabric_policies") or {}
    problems: list[str] = []
    rr = fabric.get("bgp_route_reflector") or {}
    if rr.get("nodes") and not rr.get("asn"):
        problems.append("the BGP route reflector policy has route reflector nodes but no fabric AS")
    group = (fabric.get("pod_profile") or {}).get("policy_group")
    if group and group not in {g.get("name") for g in fabric.get("pod_policy_groups", [])}:
        problems.append(f"the default pod selector is assigned undeclared Pod Policy Group '{group}'")
    if problems:
        raise PolicyReferenceError("Fabric policy references do not resolve:\n" + "\n".join(f"  - {p}" for p in problems))


def _validate_access_references(data: dict[str, Any]) -> None:
    """Port-channel / vPC / management references must resolve (2026-10-12).

    Every one of these is a name or a node pair that APIC accepts and leaves
    unresolved: a vPC binding on a pair no protection group covers, a
    selector naming a group that does not exist, an in-band address pointing
    at an EPG nobody declared. None fails at plan time; most do not fail at
    apply time either. So they are fatal here, naming the offender.
    """
    apic = data.get("apic", {})
    access = apic.get("access_policies") or {}
    problems: list[str] = []

    aeps = {a.get("name") for a in access.get("aeps", [])}
    lacps = {p.get("name") for p in access.get("lacp_policies", [])}
    access_groups = {g.get("name") for g in access.get("leaf_interface_policy_groups", [])}
    bundles = {g.get("name"): g for g in access.get("pc_vpc_policy_groups", [])}

    for name in sorted(access_groups & set(bundles)):
        problems.append(f"'{name}' is both an access-port and a PC/vPC policy group -- selectors resolve groups by name")
    for name, group in bundles.items():
        if group.get("aep") and group["aep"] not in aeps:
            problems.append(f"PC/vPC policy group '{name}' uses undeclared AEP '{group['aep']}'")
        if group.get("lacp_policy") and group["lacp_policy"] not in lacps:
            problems.append(f"PC/vPC policy group '{name}' uses undeclared LACP policy '{group['lacp_policy']}'")

    selectors = [(s.get("name"), s.get("policy_group")) for s in access.get("interface_selectors", [])]
    for profile in access.get("access_port_profiles", []):
        selectors += [(s.get("name"), s.get("policy_group")) for s in profile.get("selectors", [])]
    for sel_name, group in selectors:
        if group and group not in access_groups and group not in bundles:
            problems.append(f"interface selector '{sel_name}' applies undeclared policy group '{group}'")

    pairs: dict[frozenset, str] = {}
    seen_nodes: dict[int, str] = {}
    seen_ids: dict[int, str] = {}
    for domain in access.get("vpc_domains", []):
        name = domain.get("name")
        pair = frozenset((int(domain.get("node1", 0)), int(domain.get("node2", 0))))
        pairs[pair] = name
        for node in pair:
            if node in seen_nodes:
                problems.append(f"leaf {node} is in two vPC domains ('{seen_nodes[node]}' and '{name}')")
            seen_nodes[node] = name
        did = int(domain.get("domain_id", 0))
        if did in seen_ids:
            problems.append(f"vPC domain ID {did} is used by both '{seen_ids[did]}' and '{name}'")
        seen_ids[did] = name

    for tenant in apic.get("tenants", []):
        for ap in tenant.get("application_profiles", []):
            for epg in ap.get("endpoint_groups", []):
                for path in epg.get("static_paths", []):
                    kind = path.get("path_type", "port")
                    if kind == "port":
                        continue
                    where = f"tenant '{tenant.get('name')}' EPG '{epg.get('name')}'"
                    group = bundles.get(path.get("policy_group"))
                    if group is None:
                        problems.append(f"{where} binds undeclared PC/vPC policy group '{path.get('policy_group')}'")
                    elif group.get("bundle_type") != kind:
                        problems.append(
                            f"{where} binds '{path.get('policy_group')}' as {kind}, but it is a {group.get('bundle_type')} group"
                        )
                    if kind == "vpc":
                        pair = frozenset((int(path.get("node_id", 0)), int(path.get("node_id2", 0))))
                        if pair not in pairs:
                            problems.append(f"{where} binds a vPC on nodes {sorted(pair)}, which no vPC domain pairs")

    mgmt = apic.get("node_management") or {}
    inband = {e.get("name") for e in mgmt.get("inband_epgs", [])}
    for addr in mgmt.get("static_addresses", []):
        if addr.get("type") == "in_band" and addr.get("epg") not in inband:
            problems.append(
                f"node {addr.get('node_id')} in-band address {addr.get('address')} names undeclared "
                f"in-band EPG '{addr.get('epg')}'"
            )

    if problems:
        raise PolicyReferenceError(
            "Access / management references do not resolve:\n" + "\n".join(f"  - {p}" for p in problems)
        )


def _parse_bd_name(description: str) -> str | None:
    """Extract BD name from 'ACI Bridge Domain: <bd>:<tenant>' description."""
    if not description:
        return None
    match = _BD_DESCRIPTION_RE.match(description.strip())
    return match.group("bd").strip() if match else None


def _sanitise_prefix_as_bd_name(prefix: str) -> str:
    """Convert a CIDR string to a safe ACI BD name, e.g. '10.0.0.0/27' → 'BD_10-0-0-0_27'."""
    return "BD_" + prefix.replace(".", "-").replace("/", "_")


def _to_gateway_ip(prefix: str) -> str:
    """Return the first-host address of a prefix as the ACI BD gateway IP.

    ACI Bridge Domain subnets require a host address (gateway IP), not a
    network address.  Nautobot always normalises prefixes to network addresses,
    so this function converts e.g. '10.10.10.0/24' → '10.10.10.1/24'.
    If the prefix is already a host address it is returned unchanged.
    """
    try:
        net = ipaddress.ip_network(prefix, strict=False)
        hosts = list(net.hosts())
        if not hosts:
            return prefix  # e.g. /31 or /32 edge cases — pass through
        host = hosts[0]
        return f"{host}/{net.prefixlen}"
    except ValueError:
        return prefix  # unparseable — pass through unchanged
