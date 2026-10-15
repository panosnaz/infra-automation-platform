"""What the platform cannot set yet -- declared, not just written down.

Evidence levels say how far a tool has been PROVEN. This says what a tool, or
the Terraform behind it, cannot SET at all. A missing setting is invisible
otherwise: the call succeeds, the object deploys, and the attribute the
operator expected silently stays at an APIC default -- or, worse, a setting
that IS stored has no effect because the switch that would enable it is the
missing one (NS-01, closed 2026-10-15: EPG preferred-group membership did
nothing until the VRF's preferred group was enabled, which nothing could set).

One catalogue, one ID per gap. A tool declares the IDs that apply to it
(`registry.register(..., not_settable=("NS-02",))`) and the agent is told
before it calls; Terraform marks the same IDs with `# NOT-SETTABLE[NS-xx]:`
where the provider could do it but this module does not; and
knowledge/architecture/Evidence-Matrix.md lists every ID.
tests/unit/test_not_settable.py fails if the four ever disagree.

Closing a gap: remove its entry here, its `not_settable=` declarations and
`# NOT-SETTABLE` comments, and its Evidence-Matrix row -- the test enforces
all four together.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gap:
    title: str      # what cannot be set
    why: str        # the actual blocker
    meanwhile: str  # what applies instead, today
    next: str       # how it would be closed


NOT_SETTABLE: dict[str, Gap] = {
    "NS-02": Gap(
        "Interface policies on a PC/vPC policy group: CDP, LLDP, link level (speed/auto-negotiation), MCP (miscabling), STP, storm control, port security",
        "The bundle resource is wired only for AEP and LACP; the provider supports the other relations, no tool or Custom Field models them.",
        "APIC's default interface policies apply to every bundle (e.g. CDP off, LLDP on, auto-negotiated link).",
        "Named, shared interface-policy tools and matching fields on create/update_pc_vpc_policy_group.",
    ),
    "NS-03": Gap(
        "Interface policies on an access-port policy group through MCP: CDP, LLDP, link level, STP, port security",
        "Terraform already renders these from the group's `policies` key, but create_leaf_interface_policy_group only accepts a name and an AEP.",
        "Settable only by editing the aci_fabric_policies JSON by hand; otherwise APIC defaults apply.",
        "Expose `policies` on create_leaf_interface_policy_group plus an update tool.",
    ),
    "NS-04": Gap(
        "LACP member policy: per-port priority and fast/normal LACPDU rate",
        "No tool or Terraform resource models aci_lacp_member_policy.",
        "APIC default member policy: priority 32768, normal transmit rate.",
        "create_lacp_member_policy and an override on the PC/vPC group.",
    ),
    "NS-05": Gap(
        "vPC domain policy (peer dead interval)",
        "aci_vpc_explicit_protection_group's vpc_domain_policy is not set, and aci_vpc_domain_policy is not modelled.",
        "Every vPC domain uses APIC's 'default' vPC domain policy.",
        "A vpc_domain_policy field on create/update_vpc_domain backed by aci_vpc_domain_policy.",
    ),
    "NS-06": Gap(
        "Static path deployment immediacy and primary (micro-segmentation) encap",
        "aci_epg_to_static_path's instr_imedcy and primary_encap are not set by main.tf or the tool.",
        "APIC default deployment immediacy (on demand / 'lazy'); no primary encap.",
        "Optional deployment_immediacy and primary_encap on create_static_path_binding.",
    ),
    "NS-07": Gap(
        "IPv6 node management addresses",
        "aci_static_node_mgmt_address's v6_addr / v6_gw are not modelled; the tools accept IPv4 only.",
        "IPv4 management addressing only.",
        "Accept an IPv6 address alongside the IPv4 one (a second Nautobot IP Address on the same interface).",
    ),
    "NS-08": Gap(
        "Management access restriction: out-of-band / in-band management contracts and external management subnets",
        "No tool or Terraform resource models mgmt contracts, external management instance profiles or management zones.",
        "Management access is whatever the APIC's existing mgmt-tenant configuration allows; the platform neither adds nor checks it.",
        "OOB/in-band contract tools and external management subnet intent.",
    ),
    "NS-09": Gap(
        "Changing a bridge domain's subnet or gateway",
        "The subnet IS the Nautobot Prefix; update_bridge_domain changes attributes only, and no tool removes one subnet of a multi-subnet BD.",
        "Add a subnet with create_bridge_domain (same BD name); to change or remove one, delete the whole BD and recreate it.",
        "add/remove_bridge_domain_subnet tools.",
    ),
    "NS-10": Gap(
        "Further VRF / BD / EPG attributes: e.g. BD IP learning and limit-learning-to-subnets, EPG flood-on-encap, intra-EPG isolation, EPG QoS class, VRF BD-enforcement",
        "The provider supports them; no Custom Field or tool field models them.",
        "APIC defaults for each.",
        "Add each as a declared Custom Field (bootstrap first) and an update-tool field, one at a time with a negative test.",
    ),
    "NS-11": Gap(
        "Renaming any object",
        "An ACI object's name is part of its DN, so a rename is a delete and a create -- no update tool offers it.",
        "Delete the object (refused while referenced) and create it under the new name.",
        "Not planned as a single tool; a guided delete-and-recreate may be.",
    ),
    "NS-12": Gap(
        "ARP interface policy on an L3Out logical interface profile",
        "The provider has no resource that can create an arpIfPol (ADR-020, 2026-09-16).",
        "The profile uses uni/tn-common/arpifpol-default.",
        "aci_rest_managed for arpIfPol, with content_on_destroy, if a customer needs it.",
    ),
    "NS-13": Gap(
        "NetFlow monitor on an L3Out logical interface profile",
        "aci_netflow_monitor_policy exists, but aci_logical_interface_profile has no attribute for the l3extRsLIfPToNetflowMonitorPol relation (ADR-020).",
        "No NetFlow on L3Out interfaces.",
        "aci_rest_managed for the relation; NetFlow on bridge domains is possible today through the provider and is a separate roadmap item.",
    ),
    "NS-14": Gap(
        "Health score evaluation policy",
        "No resolvable class in this APIC version (ADR-020 Phase G).",
        "APIC's built-in health scoring.",
        "Re-check on a newer APIC release.",
    ),
    "NS-15": Gap(
        "Removing a fabric switch or interface from the Nautobot inventory",
        "create_fabric_device / create_fabric_interface have no delete counterpart.",
        "Remove the device in the Nautobot UI -- after checking that no vPC domain, static path or management address still names its node ID.",
        "delete_fabric_device with the same refuse-while-referenced check as the other deletes.",
    ),
    "NS-16": Gap(
        "Removing nested items one at a time: filter entries, contract subjects, L3Out node/interface profiles, BGP peers, external EPG subnets, match-rule prefixes, access-port selectors/blocks, leaf selectors/node blocks",
        "delete_tenant_object / delete_fabric_object remove whole top-level objects only.",
        "Delete the parent object and recreate it without the item.",
        "Kind-specific remove_* tools with the same reference checks.",
    ),
    # --- fabric-wide policies (2026-10-13) ------------------------------------
    "NS-18": Gap(
        "NTP authentication keys, the management EPG NTP and DNS are reached through, and DNS IPv4/IPv6 preference",
        "The NTP and DNS resources set servers, poll intervals and domains only.",
        "No NTP authentication; the APIC's existing management-EPG selection and IPv4 DNS preference.",
        "NTP key intent (keys as secrets, like SNMP communities) and an explicit management EPG on set_ntp_policy / DNS.",
    ),
    "NS-19": Gap(
        "SNMP client groups (permitted managers), trap destinations and SNMPv3 users",
        "Only the policy state, contact, location and community references are modelled.",
        "SNMP answers only what the APIC's existing client-group configuration permits; no traps are sent by this platform's intent.",
        "Client-group and trap-destination tools; SNMPv3 users with secrets supplied at apply time.",
    ),
    "NS-20": Gap(
        "Syslog remote destinations (syslog groups and sources) and other monitoring policies",
        "The provider has no typed resource for syslog groups/sources (ADR-020 Phase G); only the message-handling and rate-limit singletons are modelled.",
        "Syslog stays local to the fabric unless configured on the APIC by hand.",
        "aci_rest_managed for syslogGroup / syslogRemoteDest / syslogSrc with their own tools.",
    ),
    "NS-21": Gap(
        "Resetting COOP or ISIS to APIC defaults by clearing the intent",
        "aci_coop_policy / aci_isis_domain_policy cannot delete their singleton; Terraform only forgets it and the APIC keeps the last values (ADR-020 Phase E, confirmed live).",
        "Set the original value explicitly before resetting -- APIC defaults: COOP 'compatible'; ISIS MTU 1492, metric 32.",
        "Manage both through aci_rest_managed with content_on_destroy, like the other singletons.",
    ),
    "NS-22": Gap(
        "Per-pod fabric policies: NTP / DNS / SNMP policies other than the 'default' ones, and pod selectors other than the default all-pods one",
        "Every fabric policy targets the single default object (one-pod scope since ADR-020 Phase C); assign_pod_policy_group assigns to the default pod selector (type ALL) only.",
        "All pods use the default policies and the same Pod Policy Group.",
        "Named policies plus per-pod selector intent, when a multi-pod site needs it.",
    ),
    "NS-23": Gap(
        "BGP beyond in-pod spine route reflectors: external route reflectors (multi-pod / remote leaf), the BGP domain-ID base, and BGP policies other than 'default'",
        "The tools manage the fabric AS and in-pod spine route reflectors on uni/fabric/bgpInstP-default only; this lab has one pod and no inter-pod network to prove the rest against.",
        "No external route reflectors; the APIC's default domain-ID base (0); every Pod Policy Group resolves to the 'default' BGP policy.",
        "External route-reflector node intent and a domain-ID setting on set_bgp_route_reflector_policy, when a multi-pod or remote-leaf site needs it.",
    ),
    "NS-24": Gap(
        "Further ESG / vzAny contract settings: contract masters (inheritance), intra-ESG contracts, consumed contract interfaces (exported contracts), contract labels / match type / priority, and the ESG QoS class",
        "The ESG and vzAny tools bind provided and consumed contracts of the same tenant by name only.",
        "No contract inheritance or intra-ESG contracts; APIC defaults for match type (AtleastOne) and priority (unspecified); contracts from tenant common cannot be bound.",
        "Add each as a field on the ESG / vzAny contract tools when a design needs it, with a negative test.",
    ),
    "NS-25": Gap(
        "The endpoint tags and policy tags that ESG tag selectors match, and selector expressions other than an IP subnet (MAC, VM attributes)",
        "Tag selectors are modelled; the tags themselves (fvEpIpTag / fvEpMacTag under the tenant, or policy tags on EPGs and subnets) are not, and IP subnet selectors only write ip=='x' expressions.",
        "A tag selector matches only endpoints tagged by hand on the APIC (or by an integration); until then it selects nothing.",
        "Endpoint-tag intent (IP / MAC tag per tenant) and a create_endpoint_tag tool.",
    ),
    "NS-26": Gap(
        "Handing a VRF's vzAny back to APIC defaults by removing its intent entirely",
        "vzAny cannot be deleted, and it is managed only for VRFs with vzAny intent. Once the intent is gone (the Custom Field emptied to null by hand), Terraform only forgets vzAny and the APIC keeps the last preferred group and contracts.",
        "Clear through the tools instead: unbind_vzany_contract and update_vrf(preferred_group=false) keep the VRF managed, so the contracts are removed and the preferred group is turned off on the APIC.",
        "A reset that writes the APIC defaults before the intent is dropped, if hand-clearing turns out to happen.",
    ),
    "NS-27": Gap(
        "BFD authentication (key and key ID) on an L3Out interface profile, and multihop BFD",
        "The BFD key is a secret: it would need a sensitive Terraform variable like snmp_community_strings, which does not exist yet. Multihop BFD (bfdMhIfPol / node policies) is not modelled.",
        "BFD runs unauthenticated, single-hop, with the timers of the bound BFD interface policy.",
        "A bfd_keys sensitive variable keyed by reference (the SNMP pattern), and multihop BFD policies when a design needs them.",
    ),
    "NS-28": Gap(
        "Further L3Out routing settings: static-route IP SLA tracking, the shared (virtual) secondary IP of a vPC SVI, OSPF route summarization, and BGP address-family context policies (distances, eBGP/iBGP max-ECMP)",
        "The L3Out depth tools cover static routes, loopbacks, vPC SVIs, BFD, BGP / OSPF timers, BGP best path and summarization, and route tags only.",
        "Static routes stay up whatever their next hop's reachability (BFD aside); a vPC SVI has only its two side addresses; APIC defaults for OSPF summarization and BGP address-family settings.",
        "Add each as a field or tool when a design needs it, live-verified like the rest.",
    ),
}


def describe(ids: tuple[str, ...]) -> str:
    """The remark appended to a tool's description for the calling agent."""
    parts = [f"{i}: {NOT_SETTABLE[i].title} -- meanwhile: {NOT_SETTABLE[i].meanwhile}" for i in ids]
    return " [NOT YET SETTABLE -- " + " | ".join(parts) + "]"
