"""Where every kind of ACI intent lives, and what refers to it.

Pure functions only -- no Nautobot calls -- so the rules that decide whether a
delete is safe can be tested exhaustively offline.

Why this exists: a delete that leaves a reference behind does not fail when it
is made. Nautobot accepts it, the tool reports success, and the next pipeline's
generator then stops on a PolicyReferenceError (or, for references the
generator does not check, Terraform plans a broken object). Refusing the delete
up front, and naming what still points at the object, turns that into an
immediate, actionable answer.

The reference rules below mirror what the generator and main.tf actually
resolve. When a create_* tool starts writing a new cross-reference, add the
rule here too -- otherwise deleting the target is allowed and breaks the next
pipeline.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Bridge-domain naming -- must match platform/python/generator/transformer.py
# exactly (_BD_DESCRIPTION_RE / _parse_bd_name / _sanitise_prefix_as_bd_name),
# because the generator, not this module, decides what a BD is called. A
# parity test in tests/unit/test_bd_name_parity.py fails if they diverge.
# ---------------------------------------------------------------------------
_BD_DESCRIPTION_RE = re.compile(r"^ACI Bridge Domain:\s*(?P<bd>[^:]+):(?P<tenant>.+)$")


def bd_name_for_prefix(prefix: str, description: str | None) -> str:
    """The bridge-domain name the generator will give this Prefix."""
    match = _BD_DESCRIPTION_RE.match((description or "").strip())
    if match:
        return match.group("bd").strip()
    return "BD_" + prefix.replace(".", "-").replace("/", "_")


def parse_bd_description(description: str | None) -> tuple[bool, str | None, str]:
    """Split a BD Prefix description into (no_subnet, scope marker, free text).

    create_bridge_domain writes 'ACI Bridge Domain: <bd>:<tenant>' followed by
    optional ' -- no-subnet' or ' -- subnet-scope:<scope>' and then
    ' -- <user text>'. The generator reads the markers, so an update has to
    keep them apart from the user's text rather than overwrite the lot.
    A description in any other format is all free text.
    """
    desc = (description or "").strip()
    match = _BD_DESCRIPTION_RE.match(desc)
    if not match:
        return False, None, desc
    no_subnet, marker, text = False, None, []
    for part in match.group("tenant").split(" -- ")[1:]:
        if part == "no-subnet":
            no_subnet = True
        elif part.startswith("subnet-scope:"):
            marker = part[len("subnet-scope:"):]
        else:
            text.append(part)
    return no_subnet, marker, " -- ".join(text)


def compose_bd_description(
    bd: str, tenant: str, *, no_subnet: bool = False, scope_marker: str | None = None, text: str = ""
) -> str:
    """Inverse of parse_bd_description, in create_bridge_domain's format.

    The generator honours BOTH the scope marker and the aci_bd_subnet_scope
    Custom Field ("public" in either wins), so an update that changes the
    scope passes scope_marker=None and lets the Custom Field decide alone.
    """
    result = f"ACI Bridge Domain: {bd}:{tenant}"
    if no_subnet:
        result += " -- no-subnet"
    elif scope_marker:
        result += f" -- subnet-scope:{scope_marker}"
    if text:
        result += f" -- {text}"
    return result


SYSTEM_TENANTS = frozenset({"common", "infra", "mgmt"})


def bare_tenant_name(name: str) -> str:
    return name[4:] if name.startswith("ACI:") else name


# ---------------------------------------------------------------------------
# Where JSON-held kinds are stored: kind -> (Custom Field, list key).
# ---------------------------------------------------------------------------
TENANT_JSON_KINDS: dict[str, tuple[str, str]] = {
    "contract": ("aci_contracts", "contracts"),
    "filter": ("aci_contracts", "filters"),
    "l3out": ("aci_l3outs", "l3outs"),
    "match_rule": ("aci_route_control", "match_rules"),
    "vrf_route_leak": ("aci_vrf_route_leaks", "route_leaks"),
    "ospf_interface_policy": ("aci_ospf_interface_policies", "policies"),
    "nd_interface_policy": ("aci_interface_policies", "nd_interface_policies"),
    "dpp_policy": ("aci_interface_policies", "dpp_policies"),
    "pim_interface_policy": ("aci_interface_policies", "pim_interface_policies"),
    "igmp_interface_policy": ("aci_interface_policies", "igmp_interface_policies"),
    "custom_qos_policy": ("aci_interface_policies", "custom_qos_policies"),
    "l4l7_device": ("aci_l4l7_services", "devices"),
    "service_graph": ("aci_l4l7_services", "service_graphs"),
    "pbr_policy": ("aci_l4l7_services", "redirect_policies"),
    "pbr_health_group": ("aci_l4l7_services", "health_groups"),
    "ip_sla_policy": ("aci_l4l7_services", "ip_sla_policies"),
    # 2026-10-15. Nothing refers to an ESG by name.
    "esg": ("aci_endpoint_security_groups", "esgs"),
    # 2026-10-16 -- L3Out depth.
    "bfd_interface_policy": ("aci_interface_policies", "bfd_interface_policies"),
    "bgp_timers_policy": ("aci_protocol_policies", "bgp_timers_policies"),
    "bgp_best_path_policy": ("aci_protocol_policies", "bgp_best_path_policies"),
    "bgp_route_summarization_policy": ("aci_protocol_policies", "bgp_route_summarization_policies"),
    "ospf_timers_policy": ("aci_protocol_policies", "ospf_timers_policies"),
    "route_tag_policy": ("aci_protocol_policies", "route_tag_policies"),
}

# Kinds backed by first-class Nautobot objects rather than JSON.
TENANT_OBJECT_KINDS = ("vrf", "bridge_domain", "epg")

# Nested inside one L3Out, so it needs the L3Out named.
TENANT_NESTED_KINDS = ("route_control_profile",)

TENANT_KINDS = TENANT_OBJECT_KINDS + tuple(TENANT_JSON_KINDS) + TENANT_NESTED_KINDS

FABRIC_KINDS: dict[str, tuple[str, str]] = {
    "vlan_pool": ("aci_fabric_policies", "vlan_pools"),
    "physical_domain": ("aci_fabric_policies", "physical_domains"),
    "l3_domain": ("aci_fabric_policies", "l3_domains"),
    "vmm_domain": ("aci_fabric_policies", "vmm_domains"),
    "aep": ("aci_fabric_policies", "aeps"),
    "leaf_interface_policy_group": ("aci_fabric_policies", "leaf_interface_policy_groups"),
    "pod_policy_group": ("aci_fabric_policies", "pod_policy_groups"),
    "leaf_interface_profile": ("aci_fabric_policies", "leaf_interface_profiles"),
    "interface_selector": ("aci_fabric_policies", "interface_selectors"),
    "access_port_profile": ("aci_fabric_policies", "access_port_profiles"),
    "leaf_profile": ("aci_fabric_policies", "leaf_profiles"),
    "security_domain": ("aci_aaa_policies", "security_domains"),
    "local_user": ("aci_aaa_policies", "local_users"),
    # Port-channel / vPC and in-band management (2026-10-12).
    "lacp_policy": ("aci_fabric_policies", "lacp_policies"),
    "vpc_domain": ("aci_fabric_policies", "vpc_domains"),
    "pc_vpc_policy_group": ("aci_fabric_policies", "pc_vpc_policy_groups"),
    "inband_mgmt_epg": ("aci_fabric_policies", "inband_mgmt_epgs"),
}

# Fabric kinds whose references live in tenants (EPG static paths, domains),
# so a delete must load every tenant before checking.
FABRIC_KINDS_NEEDING_TENANTS = frozenset(
    {"physical_domain", "l3_domain", "vmm_domain", "pc_vpc_policy_group", "vpc_domain"}
)


def static_path_identity(path: dict) -> tuple:
    """What makes two static path bindings the SAME binding.

    A port is a node + slot + port; a port-channel is a node + its policy
    group; a vPC is a node PAIR (either order) + its policy group. Used to
    dedupe on create and to find the binding to remove.
    """
    kind = path.get("path_type", "port")
    pod = int(path.get("pod_id", 1))
    if kind == "vpc":
        pair = tuple(sorted((int(path["node_id"]), int(path["node_id2"]))))
        return ("vpc", pod, pair, path.get("policy_group"))
    if kind == "port_channel":
        return ("port_channel", pod, int(path["node_id"]), path.get("policy_group"))
    return ("port", pod, int(path["node_id"]), int(path.get("module", 1)), int(path["port"]))


def describe_static_path(path: dict) -> str:
    kind = path.get("path_type", "port")
    if kind == "vpc":
        return f"vPC {path.get('policy_group')} on nodes {path.get('node_id')}-{path.get('node_id2')}"
    if kind == "port_channel":
        return f"port-channel {path.get('policy_group')} on node {path.get('node_id')}"
    return f"port eth{path.get('module', 1)}/{path.get('port')} on node {path.get('node_id')}"


def _list(container: Any, key: str) -> list:
    if not isinstance(container, dict):
        return []
    value = container.get(key)
    return list(value) if isinstance(value, list) else []


def _cf(fields: dict, key: str) -> dict:
    value = (fields or {}).get(key)
    return value if isinstance(value, dict) else {}


def _interface_profiles(tenant_cf: dict) -> Iterable[tuple[str, str, dict]]:
    """Yield (l3out, interface profile name, profile dict) for every Logical
    Interface Profile in the tenant."""
    for out in _list(_cf(tenant_cf, "aci_l3outs"), "l3outs"):
        for np_ in _list(out, "node_profiles"):
            for ip in _list(np_, "interface_profiles"):
                yield out.get("name", "?"), ip.get("name", "?"), ip


# Which interface-profile binding keys point at which policy kind.
_INTERFACE_POLICY_BINDINGS: dict[str, tuple[str, ...]] = {
    "nd_interface_policy": ("nd_interface_policy",),
    "dpp_policy": ("ingress_dpp_policy", "egress_dpp_policy"),
    "pim_interface_policy": ("pim_interface_policy", "pim_v6_interface_policy"),
    "igmp_interface_policy": ("igmp_interface_policy",),
    "custom_qos_policy": ("custom_qos_policy",),
    "bfd_interface_policy": ("bfd_interface_policy",),
}

# L3Out depth (2026-10-16): which object keys name each protocol policy.
_VRF_POLICY_KINDS = ("bgp_timers_policy", "ospf_timers_policy", "route_tag_policy")
_L3OUT_POLICY_KINDS = ("bgp_timers_policy", "bgp_best_path_policy")


def tenant_references(
    kind: str,
    name: str,
    tenant_cf: dict,
    bridge_domains: list[dict] | None = None,
    epgs: list[dict] | None = None,
    l3out: str | None = None,
    vrfs: list[dict] | None = None,
    application_profile: str | None = None,
) -> list[str]:
    """Everything inside one tenant that still refers to `name`.

    `bridge_domains`: [{"name", "vrfs": [...], "cf": {...}}] -- one per Prefix.
    `epgs`: [{"name", "cf": {...}}] -- one per VLAN in the tenant.
    `vrfs`: [{"name", "cf": {...}}] -- vzAny contracts live on the VRF.
    `application_profile`: for kind 'epg', whose names are unique only per AP.
    """
    bridge_domains = bridge_domains or []
    epgs = epgs or []
    refs: list[str] = []
    esgs = _list(_cf(tenant_cf, "aci_endpoint_security_groups"), "esgs")
    l3outs = _list(_cf(tenant_cf, "aci_l3outs"), "l3outs")
    contracts = _list(_cf(tenant_cf, "aci_contracts"), "contracts")
    services = _cf(tenant_cf, "aci_l4l7_services")

    if kind == "vrf":
        for bd in bridge_domains:
            if name in (bd.get("vrfs") or []):
                refs.append(f"bridge domain '{bd['name']}' is in this VRF")
        for out in l3outs:
            if out.get("vrf") == name:
                refs.append(f"L3Out '{out.get('name')}' is in this VRF")
        for leak in _list(_cf(tenant_cf, "aci_vrf_route_leaks"), "route_leaks"):
            if name in (leak.get("source_vrf"), leak.get("destination_vrf")):
                refs.append(f"VRF route leak '{leak.get('name')}' uses this VRF")
        for epg in epgs:
            if (epg.get("cf") or {}).get("evpn_vrf") == name:
                refs.append(f"EVPN bridge domain '{epg['name']}' is in this VRF")
        for esg in esgs:
            if esg.get("vrf") == name:
                refs.append(f"ESG '{esg.get('name')}' is in this VRF")

    elif kind == "epg":
        for esg in esgs:
            for sel in _list(esg, "epg_selectors"):
                if sel.get("endpoint_group") == name and sel.get("application_profile") == application_profile:
                    refs.append(f"ESG '{esg.get('name')}' selects this EPG")

    elif kind == "bridge_domain":
        for epg in epgs:
            cf = epg.get("cf") or {}
            if cf.get("aci_epg_bridge_domain") == name:
                refs.append(
                    f"EPG '{epg['name']}' (application profile "
                    f"'{cf.get('aci_application_profile')}') uses this bridge domain"
                )

    elif kind == "contract":
        for epg in epgs:
            bound = _cf(epg.get("cf") or {}, "aci_epg_contracts")
            for direction in ("provided", "consumed"):
                if name in (bound.get(direction) or []):
                    refs.append(f"EPG '{epg['name']}' {direction[:-1]}s this contract")
        for out in l3outs:
            for ext in _list(out, "external_epgs"):
                for key, verb in (("provided_contracts", "provides"), ("consumed_contracts", "consumes")):
                    if name in (ext.get(key) or []):
                        refs.append(
                            f"external EPG '{ext.get('name')}' of L3Out '{out.get('name')}' {verb} this contract"
                        )
        for graph in _list(services, "service_graphs"):
            if graph.get("contract") == name:
                refs.append(f"service graph '{graph.get('name')}' is attached to this contract")
        for esg in esgs:
            for key, verb in (("provided_contracts", "provides"), ("consumed_contracts", "consumes")):
                if name in (esg.get(key) or []):
                    refs.append(f"ESG '{esg.get('name')}' {verb} this contract")
        for vrf in vrfs or []:
            bound = _cf(vrf.get("cf") or {}, "aci_vzany_contracts")
            for direction, verb in (("provided", "provides"), ("consumed", "consumes")):
                if name in (bound.get(direction) or []):
                    refs.append(f"vzAny of VRF '{vrf.get('name')}' {verb} this contract")

    elif kind == "filter":
        for contract in contracts:
            for subject in _list(contract, "subjects"):
                if name in (subject.get("filters") or []):
                    refs.append(
                        f"subject '{subject.get('name')}' of contract '{contract.get('name')}' uses this filter"
                    )

    elif kind == "l3out":
        for bd in bridge_domains:
            if name in ((bd.get("cf") or {}).get("aci_bd_l3outs") or []):
                refs.append(f"bridge domain '{bd['name']}' advertises through this L3Out")

    elif kind == "route_control_profile":
        for out in l3outs:
            if l3out is not None and out.get("name") != l3out:
                continue
            for ext in _list(out, "external_epgs"):
                for binding in _list(ext, "route_control_profiles"):
                    if binding.get("name") == name:
                        refs.append(
                            f"external EPG '{ext.get('name')}' of L3Out '{out.get('name')}' "
                            f"binds this route map ({binding.get('direction', 'export')})"
                        )

    elif kind == "match_rule":
        for out in l3outs:
            for rmap in _list(out, "route_control_profiles"):
                for ctx in _list(rmap, "contexts"):
                    if ctx.get("match_rule") == name:
                        refs.append(
                            f"context '{ctx.get('name')}' of route map '{rmap.get('name')}' "
                            f"(L3Out '{out.get('name')}') matches on this rule"
                        )

    elif kind == "ospf_interface_policy":
        for out in l3outs:
            for ospf in _list(out, "ospf_interfaces"):
                if ospf.get("policy") == name:
                    refs.append(
                        f"OSPF interface '{ospf.get('interface_key')}' of L3Out '{out.get('name')}' uses this policy"
                    )

    elif kind in _VRF_POLICY_KINDS + _L3OUT_POLICY_KINDS + ("bgp_route_summarization_policy",):
        for vrf in vrfs or []:
            if kind in _VRF_POLICY_KINDS and _cf(vrf.get("cf") or {}, "aci_vrf_protocol_policies").get(kind) == name:
                refs.append(f"VRF '{vrf.get('name')}' uses this as its {kind}")
        for out in l3outs:
            if kind in _L3OUT_POLICY_KINDS and out.get(kind) == name:
                refs.append(f"L3Out '{out.get('name')}' uses this as its {kind}")
            for ext in _list(out, "external_epgs"):
                for subnet in _list(ext, "subnets"):
                    if kind == "bgp_route_summarization_policy" and subnet.get(kind) == name:
                        refs.append(
                            f"subnet {subnet.get('ip')} of external EPG '{ext.get('name')}' (L3Out "
                            f"'{out.get('name')}') summarizes with this policy"
                        )

    elif kind in _INTERFACE_POLICY_BINDINGS:
        for out_name, ip_name, ip in _interface_profiles(tenant_cf):
            for key in _INTERFACE_POLICY_BINDINGS[kind]:
                if ip.get(key) == name:
                    refs.append(
                        f"interface profile '{ip_name}' of L3Out '{out_name}' binds this policy as {key}"
                    )

    elif kind == "l4l7_device":
        for graph in _list(services, "service_graphs"):
            if graph.get("device") == name:
                refs.append(f"service graph '{graph.get('name')}' uses this device")

    elif kind == "service_graph":
        for contract in contracts:
            for subject in _list(contract, "subjects"):
                if subject.get("service_graph") == name:
                    refs.append(
                        f"subject '{subject.get('name')}' of contract '{contract.get('name')}' redirects through this graph"
                    )

    elif kind == "pbr_policy":
        for graph in _list(services, "service_graphs"):
            for side in ("consumer", "provider"):
                if (graph.get(side) or {}).get("redirect_policy") == name:
                    refs.append(f"service graph '{graph.get('name')}' uses this policy on its {side} side")

    elif kind == "pbr_health_group":
        for policy in _list(services, "redirect_policies"):
            for dest in _list(policy, "destinations"):
                if dest.get("health_group") == name:
                    refs.append(
                        f"destination {dest.get('ip')} of redirect policy '{policy.get('name')}' is tracked by this group"
                    )

    elif kind == "ip_sla_policy":
        for policy in _list(services, "redirect_policies"):
            if policy.get("ip_sla_policy") == name:
                refs.append(f"redirect policy '{policy.get('name')}' probes with this IP SLA policy")

    # epg, vrf_route_leak: nothing else refers to them by name.
    # Once each: a multi-subnet BD is several Prefixes carrying the same fact.
    return list(dict.fromkeys(refs))


def _domain_names(domains: list) -> list[tuple[str, str]]:
    """AEP domain entries are either a bare name (physical) or {name, type}."""
    result = []
    for d in domains:
        if isinstance(d, dict):
            result.append((d.get("name"), d.get("type", "physical")))
        else:
            result.append((d, "physical"))
    return result


def fabric_references(
    kind: str,
    name: str,
    location_cf: dict,
    tenants: list[dict] | None = None,
    mgmt_addresses: list[dict] | None = None,
) -> list[str]:
    """Everything that still refers to a fabric-wide object.

    `tenants`: [{"name", "cf": tenant custom fields, "epgs": [{"name", "cf"}]}]
    for EVERY tenant -- domains are referenced across tenants, so a check
    scoped to one tenant would pass while another tenant's EPG still binds it.
    """
    tenants = tenants or []
    fabric = _cf(location_cf, "aci_fabric_policies")
    aaa = _cf(location_cf, "aci_aaa_policies")
    refs: list[str] = []

    if kind == "vlan_pool":
        for key, label in (("physical_domains", "physical domain"), ("l3_domains", "L3 domain"),
                           ("vmm_domains", "VMM domain")):
            for dom in _list(fabric, key):
                if dom.get("vlan_pool") == name:
                    refs.append(f"{label} '{dom.get('name')}' draws VLANs from this pool")

    elif kind in ("physical_domain", "l3_domain", "vmm_domain"):
        aep_type = {"physical_domain": "physical", "l3_domain": "l3", "vmm_domain": "vmm"}[kind]
        epg_type = {"physical_domain": "physical", "vmm_domain": "vmm"}.get(kind)
        for aep in _list(fabric, "aeps"):
            if (name, aep_type) in _domain_names(_list(aep, "domains")):
                refs.append(f"AEP '{aep.get('name')}' includes this domain")
        for tenant in tenants:
            tname = tenant.get("name")
            if epg_type:
                for epg in tenant.get("epgs") or []:
                    for dom in _list(_cf(epg.get("cf") or {}, "aci_epg_domains"), "domains"):
                        if dom.get("name") == name and dom.get("domain_type") == epg_type:
                            refs.append(f"EPG '{epg.get('name')}' in tenant '{tname}' is bound to this domain")
            for device in _list(_cf(tenant.get("cf") or {}, "aci_l4l7_services"), "devices"):
                if kind == "physical_domain" and device.get("physical_domain") == name:
                    refs.append(f"L4-L7 device '{device.get('name')}' in tenant '{tname}' uses this domain")
                if kind == "vmm_domain" and device.get("vmm_domain") == name:
                    refs.append(f"L4-L7 device '{device.get('name')}' in tenant '{tname}' uses this domain")
            if kind == "l3_domain":
                for out in _list(_cf(tenant.get("cf") or {}, "aci_l3outs"), "l3outs"):
                    if out.get("domain") == name:
                        refs.append(f"L3Out '{out.get('name')}' in tenant '{tname}' uses this domain")

    elif kind == "aep":
        for group in _list(fabric, "leaf_interface_policy_groups"):
            if group.get("aep") == name:
                refs.append(f"leaf interface policy group '{group.get('name')}' uses this AEP")
        for group in _list(fabric, "pc_vpc_policy_groups"):
            if group.get("aep") == name:
                refs.append(f"PC/vPC policy group '{group.get('name')}' uses this AEP")

    elif kind == "lacp_policy":
        for group in _list(fabric, "pc_vpc_policy_groups"):
            if group.get("lacp_policy") == name:
                refs.append(f"PC/vPC policy group '{group.get('name')}' uses this LACP policy")

    elif kind == "vpc_domain":
        domain = next((d for d in _list(fabric, "vpc_domains") if d.get("name") == name), None)
        if domain is not None:
            pair = {int(domain.get("node1", -1)), int(domain.get("node2", -1))}
            for tenant in tenants:
                for epg in tenant.get("epgs") or []:
                    for path in (epg.get("cf") or {}).get("aci_static_paths") or []:
                        if path.get("path_type") == "vpc" and {int(path.get("node_id", -1)), int(path.get("node_id2", -1))} == pair:
                            refs.append(
                                f"EPG '{epg.get('name')}' in tenant '{tenant.get('name')}' is bound to "
                                f"{describe_static_path(path)}, which needs this vPC pair"
                            )

    elif kind == "pod_policy_group":
        if (fabric.get("pod_profile") or {}).get("policy_group") == name:
            refs.append("the default pod selector (all pods) is assigned this policy group")

    elif kind == "inband_mgmt_epg":
        for addr in mgmt_addresses or []:
            if addr.get("type") == "in_band" and addr.get("epg") == name:
                refs.append(f"in-band management address {addr.get('address')} of node {addr.get('node')} uses this EPG")

    elif kind == "pc_vpc_policy_group":
        for sel in _list(fabric, "interface_selectors"):
            if sel.get("policy_group") == name:
                refs.append(f"interface selector '{sel.get('name')}' applies this policy group")
        for profile in _list(fabric, "access_port_profiles"):
            for sel in _list(profile, "selectors"):
                if sel.get("policy_group") == name:
                    refs.append(
                        f"selector '{sel.get('name')}' of access port profile '{profile.get('name')}' "
                        "applies this policy group"
                    )
        for tenant in tenants:
            for epg in tenant.get("epgs") or []:
                for path in (epg.get("cf") or {}).get("aci_static_paths") or []:
                    if path.get("policy_group") == name:
                        refs.append(
                            f"EPG '{epg.get('name')}' in tenant '{tenant.get('name')}' is bound to {describe_static_path(path)}"
                        )

    elif kind == "leaf_interface_policy_group":
        for sel in _list(fabric, "interface_selectors"):
            if sel.get("policy_group") == name:
                refs.append(f"interface selector '{sel.get('name')}' applies this policy group")
        for profile in _list(fabric, "access_port_profiles"):
            for sel in _list(profile, "selectors"):
                if sel.get("policy_group") == name:
                    refs.append(
                        f"selector '{sel.get('name')}' of access port profile '{profile.get('name')}' "
                        "applies this policy group"
                    )

    elif kind == "leaf_interface_profile":
        for sel in _list(fabric, "interface_selectors"):
            if sel.get("leaf_interface_profile") == name:
                refs.append(f"interface selector '{sel.get('name')}' belongs to this profile")

    elif kind == "access_port_profile":
        for profile in _list(fabric, "leaf_profiles"):
            if name in (profile.get("access_port_profiles") or []):
                refs.append(f"leaf profile '{profile.get('name')}' includes this access port profile")

    elif kind == "security_domain":
        for user in _list(aaa, "local_users"):
            for dom in _list(user, "security_domains"):
                if dom.get("name") == name:
                    refs.append(f"local user '{user.get('name')}' is assigned to this security domain")

    # interface_selector, leaf_profile, local_user: nothing else refers to
    # them by name.
    return list(dict.fromkeys(refs))


def remove_named(entries: list, name: str) -> tuple[list, int]:
    """Drop every entry called `name`. Returns (kept, how many were removed).

    Every one, not the first: several create_* tools used to append rather
    than dedupe, so some environments still carry duplicates, and removing
    only the first would leave the object in place while reporting success.
    """
    kept = [e for e in entries if not (isinstance(e, dict) and e.get("name") == name)]
    return kept, len(entries) - len(kept)
