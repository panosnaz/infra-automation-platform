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
    vlans: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    include_system_tenants: bool = False,
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

        gateway_ip = _to_gateway_ip(network)
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

        entry: dict[str, Any] = {
            "name": bd_name,
            "unicast_routing": True,
            "subnets": [
                {
                    "ip": gateway_ip,
                    "public": False,
                    "private": True,
                    "shared": False,
                }
            ],
        }
        if vrf_name:
            entry["vrf"] = vrf_name

        # ADR-020 Phase A item 1: Bridge Domain attribute depth, sourced from
        # the owning Prefix's custom fields (BD identity is derived
        # per-prefix in this generator, so BD-level attributes live there
        # too -- see the module docstring). Same "only emit if set" rule as
        # VRF attributes above.
        cf = prefix.get("_custom_field_data") or {}
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

        result.append(entry)
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
        epg_domains = cf.get("aci_epg_domains") or {}
        if domains := epg_domains.get("domains"):
            epg["domains"] = list(domains)

        aps[ap_name].append(epg)

    return [
        {"name": ap_name, "endpoint_groups": epgs}
        for ap_name, epgs in aps.items()
    ]


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
    return list(data.get("l3outs") or [])


def _build_fabric_and_access_policies(
    locations: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build apic.fabric_policies and apic.access_policies from each
    Location's ``aci_fabric_policies`` JSON Custom Field (ADR-020 Phase B,
    logical-only scope; Phase C adds POD-wide NTP/DNS/SNMP -- ADR-020 Phase C).

    VLAN Pools/Physical Domains/AEPs/Leaf Interface Policy Groups are
    fabric-wide (not Tenant-scoped) objects with no natural Nautobot home,
    so -- same Custom-Field-JSON approach as Phase A items 3-4 -- they live
    on the Location representing the ACI fabric/site rather than a new
    Nautobot model. Aggregated across all Locations that have the field set
    (multi-site safe, though this lab only has one). Logical-only: no
    physical port/interface binding is modeled -- this simulator has zero
    real leaf/spine interface data available (confirmed via direct APIC API
    query: no l1PhysIf objects exist anywhere, and node-scoped queries fail
    with "node marked unavailable"). Same pass-through convention as
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
    aeps: list[dict[str, Any]] = []
    leaf_interface_policy_groups: list[dict[str, Any]] = []
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

    for location in locations:
        cf = location.get("_custom_field_data") or {}
        data = cf.get("aci_fabric_policies") or {}
        vlan_pools.extend(data.get("vlan_pools") or [])
        physical_domains.extend(data.get("physical_domains") or [])
        aeps.extend(data.get("aeps") or [])
        leaf_interface_policy_groups.extend(data.get("leaf_interface_policy_groups") or [])
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

    access_policies: dict[str, Any] = {}
    if physical_domains:
        access_policies["physical_domains"] = physical_domains
    if aeps:
        access_policies["aeps"] = aeps
    if leaf_interface_policy_groups:
        access_policies["leaf_interface_policy_groups"] = leaf_interface_policy_groups

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
