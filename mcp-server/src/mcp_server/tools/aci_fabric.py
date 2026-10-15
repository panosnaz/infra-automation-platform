"""Cisco ACI fabric-wide policy tools (2026-10-13): NTP, DNS, SNMP, COOP,
ISIS, fault lifecycle, syslog.

These objects are APIC singletons that always exist, so the tools SET them;
list members (NTP / DNS servers, DNS domains, SNMP community references) get
create / update / delete; `reset_fabric_policy` hands a policy back to APIC's
defaults. Read is `get_fabric_intent`. What none of them can set is declared
per tool (not_settable=, see mcp_server/not_settable.py).

Imported by tools/aci.py, so importing the ACI tools registers these too.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.aci_fabric import (
    AssignPodPolicyGroupRequest,
    CreateBgpRouteReflectorNodeRequest,
    CreateDnsDomainRequest,
    CreateDnsServerRequest,
    CreateNtpServerRequest,
    CreateSnmpCommunityRequest,
    DeleteBgpRouteReflectorNodeRequest,
    DeleteDnsDomainRequest,
    DeleteDnsServerRequest,
    DeleteNtpServerRequest,
    DeleteSnmpCommunityRequest,
    ResetFabricPolicyRequest,
    SetBgpRouteReflectorPolicyRequest,
    SetCoopPolicyRequest,
    SetFaultLifecyclePolicyRequest,
    SetIsisPolicyRequest,
    SetNtpPolicyRequest,
    SetSnmpPolicyRequest,
    SetSyslogMessagePolicyRequest,
    SetSyslogRateLimitRequest,
    UpdateDnsDomainRequest,
    UpdateDnsServerRequest,
    UpdateNtpServerRequest,
)
from mcp_server.tools.registry import registry

_LIVE = (
    "2026-10-13. Over the real MCP protocol against live Nautobot: 46/46 checks -- every write read "
    "back via REST, the generator run against live Nautobot (community emitted as reference only), every "
    "policy reset, the Location byte-identical afterwards. Terraform: tests/fixtures/fabric-policies.yaml "
    "applied and destroyed against the lab APIC twice in an isolated state (9 added / 9 destroyed; re-plan "
    "'No changes'), every value read back from APIC, all 8 singletons byte-identical to the pre-apply "
    "snapshot after destroy, no new faults (unscoped 5/5); community string never in output via mask_secrets.py."
)


def _register(name: str, schema, description: str, not_settable: tuple[str, ...] = ()):
    return registry.register(name=name, domain="cisco_aci", description=description, schema=schema,
                             evidence="live-verified", evidence_note=_LIVE, not_settable=not_settable)


# --- NTP --------------------------------------------------------------------------

@_register("set_ntp_policy", SetNtpPolicyRequest,
           "Enable or disable NTP on the fabric (the default date-and-time policy, uni/fabric/time-default).",
           not_settable=("NS-18", "NS-22"))
def set_ntp_policy(request: SetNtpPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_ntp_policy(request.location, request.admin_state)


@_register("create_ntp_server", CreateNtpServerRequest,
           "Add an NTP server (IP or host name) to the fabric's date-and-time policy.", not_settable=("NS-18",))
def create_ntp_server(request: CreateNtpServerRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_ntp_server(request.location, request.address, request.preferred, request.min_poll, request.max_poll)


@_register("update_ntp_server", UpdateNtpServerRequest,
           "Change an NTP server's preference or poll intervals.", not_settable=("NS-18",))
def update_ntp_server(request: UpdateNtpServerRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_ntp_server(request.location, request.address, request.preferred, request.min_poll, request.max_poll)


@_register("delete_ntp_server", DeleteNtpServerRequest, "Remove an NTP server from the fabric.")
def delete_ntp_server(request: DeleteNtpServerRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_ntp_server(request.location, request.address)


# --- DNS --------------------------------------------------------------------------

@_register("create_dns_server", CreateDnsServerRequest,
           "Add a DNS server to the fabric's default DNS profile (uni/fabric/dnsp-default).", not_settable=("NS-18",))
def create_dns_server(request: CreateDnsServerRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_dns_server(request.location, request.address, request.preferred)


@_register("update_dns_server", UpdateDnsServerRequest, "Change whether a DNS server is preferred.")
def update_dns_server(request: UpdateDnsServerRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_dns_server(request.location, request.address, request.preferred)


@_register("delete_dns_server", DeleteDnsServerRequest, "Remove a DNS server from the fabric's DNS profile.")
def delete_dns_server(request: DeleteDnsServerRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_dns_server(request.location, request.address)


@_register("create_dns_domain", CreateDnsDomainRequest,
           "Add a DNS search domain. Making it the default demotes any other default domain -- APIC allows one.")
def create_dns_domain(request: CreateDnsDomainRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_dns_domain(request.location, request.name, request.is_default)


@_register("update_dns_domain", UpdateDnsDomainRequest, "Make a DNS search domain the default, or not.")
def update_dns_domain(request: UpdateDnsDomainRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_dns_domain(request.location, request.name, request.is_default)


@_register("delete_dns_domain", DeleteDnsDomainRequest, "Remove a DNS search domain.")
def delete_dns_domain(request: DeleteDnsDomainRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_dns_domain(request.location, request.name)


# --- SNMP -------------------------------------------------------------------------

@_register("set_snmp_policy", SetSnmpPolicyRequest,
           "Set the fabric SNMP policy: enabled/disabled, sysContact and sysLocation (uni/fabric/snmppol-default).",
           not_settable=("NS-19", "NS-22"))
def set_snmp_policy(request: SetSnmpPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_snmp_policy(request.location, request.admin_state, request.contact, request.system_location)


@_register("create_snmp_community", CreateSnmpCommunityRequest,
           "Add an SNMP community by REFERENCE. Only the reference name is stored; the community string is a "
           "credential, supplied at apply time in the sensitive Terraform variable snmp_community_strings "
           "(e.g. from Vault), keyed by the reference. Never pass the community string itself.",
           not_settable=("NS-19",))
def create_snmp_community(request: CreateSnmpCommunityRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_snmp_community(request.location, request.ref)


@_register("delete_snmp_community", DeleteSnmpCommunityRequest, "Remove an SNMP community by its reference name.")
def delete_snmp_community(request: DeleteSnmpCommunityRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_snmp_community(request.location, request.ref)


# --- COOP / ISIS / fault lifecycle / syslog ---------------------------------------

@_register("set_coop_policy", SetCoopPolicyRequest,
           "Set the COOP group policy type (compatible / strict) -- uni/fabric/pol-default.", not_settable=("NS-21",))
def set_coop_policy(request: SetCoopPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_coop_policy(request.location, request.type)


@_register("set_isis_policy", SetIsisPolicyRequest,
           "Set the fabric ISIS domain policy: MTU and the metric for redistributed routes -- uni/fabric/isisDomP-default.",
           not_settable=("NS-21",))
def set_isis_policy(request: SetIsisPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_isis_policy(request.location, request.mtu, request.redistrib_metric)


@_register("set_fault_lifecycle_policy", SetFaultLifecyclePolicyRequest,
           "Set how long faults soak, stay clearing, and are retained once cleared (uni/fabric/moncommon/flcp-generic).")
def set_fault_lifecycle_policy(request: SetFaultLifecyclePolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_fault_lifecycle_policy(request.location, request.soak, request.retain, request.clear)


@_register("set_syslog_message_policy", SetSyslogMessagePolicyRequest,
           "Set the fabric's syslog system-message handling (uni/fabric/moncommon/sysmsgp).", not_settable=("NS-20",))
def set_syslog_message_policy(request: SetSyslogMessagePolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_syslog_message_policy(request.location, request.admin_state)


@_register("set_syslog_rate_limit", SetSyslogRateLimitRequest,
           "Enable or disable syslog rate limiting and set messages per second (uni/fabric/moncommon/ratelimitp).",
           not_settable=("NS-20",))
def set_syslog_rate_limit(request: SetSyslogRateLimitRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_syslog_rate_limit(request.location, request.enabled, request.limit_per_sec)


@_register("reset_fabric_policy", ResetFabricPolicyRequest,
           "Remove a fabric-wide policy's intent so the APIC goes back to its default. For NTP, DNS, SNMP, fault "
           "lifecycle and syslog Terraform restores the default on the next apply; for COOP and ISIS the APIC "
           "KEEPS the last value, so set the original value first.", not_settable=("NS-21",))
def reset_fabric_policy(request: ResetFabricPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.reset_fabric_policy(request.location, request.policy)


# --- BGP route reflector policy / pod assignment (2026-10-14) ---------------------

_LIVE_RR = (
    "2026-10-14. Over the real MCP protocol against live Nautobot: 30/30 checks -- every write read back via "
    "REST, a leaf / unknown node / missing Pod Policy Group / assigned-group delete each refused, the generator "
    "run against live Nautobot, the Location byte-identical afterwards. Terraform: "
    "tests/fixtures/bgp-route-reflector.yaml applied and destroyed against the lab APIC in an isolated state "
    "(3 + 1 added, 4 destroyed, re-plan 'No changes'), both pod relations 'formed', the three subtrees "
    "byte-identical to the pre-apply snapshot after destroy. AS + assignment: no new faults. The route-reflector "
    "node raises F1893 because this simulator has no registered spine -- check_apic_faults.py caught it."
)


def _register_rr(name: str, schema, description: str, not_settable: tuple[str, ...] = ()):
    return registry.register(name=name, domain="cisco_aci", description=description, schema=schema,
                             evidence="live-verified", evidence_note=_LIVE_RR, not_settable=not_settable)


@_register_rr("set_bgp_route_reflector_policy", SetBgpRouteReflectorPolicyRequest,
              "Set the fabric's BGP autonomous system number (uni/fabric/bgpInstP-default). The fabric's MP-BGP "
              "carries routes learned on L3Outs to every leaf; without an AS and spine route reflectors they "
              "stay on the border leaf. Changing the AS on a running fabric resets every MP-BGP session. Takes "
              "effect once a Pod Policy Group is assigned to the pod (assign_pod_policy_group).",
              not_settable=("NS-23",))
def set_bgp_route_reflector_policy(request: SetBgpRouteReflectorPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_bgp_route_reflector_policy(request.location, request.asn)


@_register_rr("create_bgp_route_reflector_node", CreateBgpRouteReflectorNodeRequest,
              "Make a spine a BGP route reflector for the fabric. Only spines can be route reflectors: a leaf "
              "is refused (APIC would accept it and raise fault F1893). Use two spines for redundancy.",
              not_settable=("NS-23",))
def create_bgp_route_reflector_node(request: CreateBgpRouteReflectorNodeRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_bgp_route_reflector_node(request.location, request.node, request.pod_id)


@_register_rr("delete_bgp_route_reflector_node", DeleteBgpRouteReflectorNodeRequest,
              "Stop a spine acting as a BGP route reflector. Removing the last one stops external routes "
              "being distributed across the fabric.")
def delete_bgp_route_reflector_node(request: DeleteBgpRouteReflectorNodeRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_bgp_route_reflector_node(request.location, request.node_id)


@_register_rr("assign_pod_policy_group", AssignPodPolicyGroupRequest,
              "Assign an existing Pod Policy Group to the default pod selector (all pods) -- this is what makes "
              "the BGP route reflector policy and the group's other pod policies apply. Replaces any group "
              "already assigned. Undo with reset_fabric_policy(policy='pod_profile').",
              not_settable=("NS-22",))
def assign_pod_policy_group(request: AssignPodPolicyGroupRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.assign_pod_policy_group(request.location, request.policy_group)
