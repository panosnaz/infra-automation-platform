"""Cisco ACI domain tools. Per Platform-v2-Reference-Architecture.md §7.8,
covers create_tenant, create_vrf, create_bridge_domain, create_epg,
create_contract, and create_l3out -- one tool per ADR-020 Phase A item, added
the same way once each item's generator/Terraform support landed. Also
covers create_vlan_pool, create_physical_domain, create_aep, and
create_leaf_interface_policy_group -- ADR-020 Phase B's fabric-wide Access/
Fabric Policy objects, following the same pattern. Also covers
create_vmm_domain -- ADR-020 Phase D's VMM Domain integration -- and
bind_epg_domain -- ADR-020 Phase D's follow-on EPG-to-Domain binding. Also
covers create_security_domain and create_local_user -- ADR-020 Phase F's
RBAC/Security Domains/Local Users coverage. Also covers, ported from
copilot/aci-platform-comparison (2026-09-08): create_vrf_route_leak,
create_leaf_interface_profile/create_interface_selector/
create_static_path_binding, physical/protocol L3Out node/interface/BGP/OSPF
tools, and L4-L7/PBR/Service Graph tools -- see Platform-Status-and-Pending-
Items.md for their plan-validated-only status on this simulator.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.aci import (
    BindEpgContractRequest,
    BindEpgDomainRequest,
    CreateAepRequest,
    CreateBgpPeerRequest,
    CreateBridgeDomainRequest,
    CreateContractRequest,
    CreateContractSubjectRequest,
    CreateEpgRequest,
    CreateFilterRequest,
    CreateFilterEntryRequest,
    CreateInterfaceSelectorRequest,
    CreateAccessPortProfileRequest,
    CreateAccessPortSelectorRequest,
    CreateAccessPortBlockRequest,
    CreateLeafProfileRequest,
    CreateLeafSelectorRequest,
    CreateLeafNodeBlockRequest,
    CreateStaticPathBindingRequest,
    CreateProtocolL3OutRequest,
    CreateL3OutNodeProfileRequest,
    CreateL3OutInterfaceProfileRequest,
    CreateL3OutInterfaceRequest,
    CreateL3OutNodeProfileRequest,
    CreateL3OutRequest,
    BindExternalEpgRouteControlProfileRequest,
    BindL3OutInterfaceProfilePoliciesRequest,
    AddExternalEpgSubnetRequest,
    AddMatchRulePrefixRequest,
    BindExternalEpgContractRequest,
    CreateL3DomainRequest,
    CreateMatchRuleRequest,
    SetExternalEpgSubnetScopeRequest,
    CreateRouteControlProfileRequest,
    CreateConcreteDeviceRequest,
    CreateCustomQosPolicyRequest,
    CreateDppPolicyRequest,
    CreateIgmpInterfacePolicyRequest,
    CreateNdInterfacePolicyRequest,
    CreatePimInterfacePolicyRequest,
    CreateL4L7DeviceRequest,
    CreateLeafInterfacePolicyGroupRequest,
    CreateLeafInterfaceProfileRequest,
    CreatePodPolicyGroupRequest,
    CreateFabricDeviceRequest,
    CreateFabricInterfaceRequest,
    CreateLocalUserRequest,
    CreateOneArmServiceGraphRequest,
    CreateOspfInterfacePolicyRequest,
    CreateOspfInterfaceRequest,
    CreateIpSlaPolicyRequest,
    CreatePbrContractRequest,
    CreatePbrHealthGroupRequest,
    CreatePbrPolicyRequest,
    CreatePhysicalDomainRequest,
    CreateProtocolL3OutRequest,
    CreateSecurityDomainRequest,
    CreateServiceGraphRequest,
    CreateStaticPathBindingRequest,
    CreateTenantRequest,
    CreateVlanPoolRequest,
    CreateVmmDomainRequest,
    CreateVrfRequest,
    CreateVrfRouteLeakRequest,
)
from mcp_server.tools.registry import registry


def _resolved_location(result: dict, request) -> str:
    """The Location a write actually landed in.

    `request.location` is None whenever the caller let it auto-resolve, so
    echoing it back reported "Location 'None'" while the data was written
    correctly (2026-09-17). The client returns the resolved name; fall back to
    the request only if a client has not been updated to do so.
    """
    inner = result if isinstance(result, dict) else {}
    for key in ("location",):
        if inner.get(key):
            return str(inner[key])
    return str(getattr(request, "location", None) or "auto-resolved")


# Every one of these was proven the same way, so the note is shared rather
# than re-typed six times.
EVIDENCE_LEVEL = "live-verified"
_APPLIED = (
    "Terraform applied + destroyed against the lab APIC 2026-09-16 via "
    "tests/fixtures/l3out-interface-policies.yaml, with the resulting MOs read "
    "back from APIC. These objects need no leaf port, switch or vCenter, so "
    "nothing on this simulator blocks them."
)
ND_NOTE = _APPLIED + " ndIfPol ND_Strict created; hopLimit=64, mtu=1500, retransTimer=1000 confirmed on the MO; l3extRsNdIfPol state=formed."
DPP_NOTE = _APPLIED + " qosDppPol Ingress_100M created; rate=100 mega, burst=200 mega, conform=transmit, exceed=drop confirmed; both l3extRsIngressQosDppPol and l3extRsEgressQosDppPol state=formed."
PIM_NOTE = _APPLIED + " pimIfPol PIM_Edge and PIM6_Edge created; pimRsIfPol and pimRsV6IfPol both state=formed. Note the relation is nested under pimifp/pimipv6ifp containers, not a direct l3extRs child."
IGMP_NOTE = _APPLIED + " igmpIfPol IGMP_v3 created; ver=v3, queryIntvl=125, grpTimeout=260 confirmed; igmpRsIfPol state=formed."
CQOS_NOTE = _APPLIED + " qosCustomPol CQos_Edge created; l3extRsLIfPCustQosPol state=formed."
BIND_NOTE = _APPLIED + " All seven relations bound at once on one profile and all reached state=formed, while a control profile with no bindings correctly fell back to uni/tn-common/*-default."

_RC_APPLIED = (
    "Transit-routing lab 2026-09-16: written over the real MCP protocol, "
    "generated, and applied against the lab APIC, with the resulting MOs read "
    "back. Route control objects are pure tenant/L3Out config and need no "
    "leaf port, switch or vCenter."
)
MATCH_RULE_NOTE = _RC_APPLIED + " rtctrlSubjP + rtctrlMatchRtDest confirmed for match-permit-prefix-out (172.16.200.200/32) and deny-prefix-out (10.0.3.0/24)."
ROUTE_MAP_NOTE = _RC_APPLIED + " rtctrlProfile Uni-Route-Profile-OUT (type=global, Match Routing Policy Only) with rtctrlCtxP order 0 permit-explicit/permit and order 1 explicit-deny-out/deny, each resolving its match rule."
BIND_RM_NOTE = _RC_APPLIED + " l3extRsInstPToProfile confirmed on the external EPG for direction=export."
CORRECTION_NOTE = (
    "Transit-routing lab corrections 2026-09-16: written over the real MCP "
    "protocol, generated, applied against the lab APIC and the MO read back."
)
SCOPE_NOTE = _RC_APPLIED + " Cat_ExtNet 172.16.200.200/32 moved off export-rtctrl so the route map is the only export mechanism; the resulting l3extSubnet scope was read back from APIC."





@registry.register(
    name="create_tenant",
    evidence="live-verified",
    evidence_note="MCP protocol + Nautobot, Milestone 6 end-to-end",
    domain="cisco_aci",
    description=(
        "Create a new Cisco ACI Tenant by writing a Tenant object directly "
        "to Nautobot (the Source of Truth). This triggers Nautobot's "
        "tenancy.tenant webhook, which starts the existing GitLab CI "
        "pipeline (generate -> policy -> plan -> approval -> apply -> "
        "ansible -> validate -> write-results -> knowledge-capture) "
        "unmodified. Use show_status afterward to check on the deployment."
    ),
    schema=CreateTenantRequest,
)
def create_tenant(request: CreateTenantRequest, *, nautobot: NautobotClient) -> dict:
    tenant = nautobot.create_tenant(name=request.name, description=request.description)
    return {
        "tenant": tenant,
        "note": (
            "Tenant written to Nautobot. If a webhook is configured on "
            "tenancy.tenant creation, a GitLab pipeline has been triggered "
            "-- call show_status(name=...) to check on it."
        ),
    }


@registry.register(
    name="create_vrf",
    evidence="live-verified",
    evidence_note="MCP protocol + Nautobot, Milestone 6 end-to-end",
    domain="cisco_aci",
    description=(
        "Create a VRF inside an existing Cisco ACI Tenant by writing an "
        "ipam.vrf object directly to Nautobot. The next scheduled/triggered "
        "pipeline run will pick it up via the generator (ADR-020 Phase A "
        "item 1) -- use show_status(name=<tenant>) afterward."
    ),
    schema=CreateVrfRequest,
)
def create_vrf(request: CreateVrfRequest, *, nautobot: NautobotClient) -> dict:
    vrf = nautobot.create_vrf(tenant=request.tenant, name=request.name, description=request.description)
    return {
        "vrf": vrf,
        "note": f"VRF written to Nautobot under tenant '{request.tenant}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
    }


@registry.register(
    name="create_bridge_domain",
    evidence="live-verified",
    evidence_note="MCP protocol + Nautobot, Milestone 6 end-to-end",
    domain="cisco_aci",
    description=(
        "Create a Bridge Domain inside an existing Cisco ACI Tenant/VRF by "
        "writing a Prefix to Nautobot (BD identity is derived from the "
        "Prefix's description -- Nautobot has no separate BD object, see "
        "ADR-020 Phase A item 1) plus its VRF assignment. Use "
        "show_status(name=<tenant>) afterward."
    ),
    schema=CreateBridgeDomainRequest,
)
def create_bridge_domain(request: CreateBridgeDomainRequest, *, nautobot: NautobotClient) -> dict:
    prefix = nautobot.create_bridge_domain(
        tenant=request.tenant,
        vrf=request.vrf,
        name=request.name,
        gateway_ip=request.gateway_ip,
        subnet_scope=request.subnet_scope,
        description=request.description,
        l3outs=request.l3outs,
    )
    return {
        "prefix": prefix,
        "note": f"Bridge Domain '{request.name}' written to Nautobot under tenant '{request.tenant}'/VRF '{request.vrf}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
    }


@registry.register(
    name="create_epg",
    evidence="live-verified",
    evidence_note="MCP protocol + Nautobot (ADR-020 Phase A)",
    domain="cisco_aci",
    description=(
        "Create an EPG inside an existing Cisco ACI Tenant by writing a "
        "VLAN to Nautobot with the aci_application_profile/"
        "aci_epg_bridge_domain Custom Fields set (EPGs are modeled as "
        "VLANs -- ADR-020 Phase A item 2). Use show_status(name=<tenant>) "
        "afterward."
    ),
    schema=CreateEpgRequest,
)
def create_epg(request: CreateEpgRequest, *, nautobot: NautobotClient) -> dict:
    vlan = nautobot.create_epg(
        tenant=request.tenant,
        application_profile=request.application_profile,
        bridge_domain=request.bridge_domain,
        name=request.name,
        vid=request.vid,
        subnet=request.subnet,
        subnet_scope=request.subnet_scope,
        provided_contracts=request.provided_contracts,
        consumed_contracts=request.consumed_contracts,
        description=request.description,
    )
    return {
        "epg": vlan,
        "note": f"EPG '{request.name}' (Application Profile '{request.application_profile}') written to Nautobot under tenant '{request.tenant}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
    }


@registry.register(
    name="bind_epg_domain",
    evidence="live-verified",
    evidence_note="MCP protocol session 2026-09-04, verified in Nautobot then cleaned up",
    domain="cisco_aci",
    description=(
        "Bind an existing EPG to a Physical or VMM Domain (ADR-020 Phase D "
        "follow-on) by writing to the aci_epg_domains Custom Field on the "
        "EPG's own VLAN object. Re-binding the same domain updates its "
        "resolution/deployment immediacy in place rather than duplicating "
        "the entry. Use show_status(name=<tenant>) afterward."
    ),
    schema=BindEpgDomainRequest,
)
def bind_epg_domain(request: BindEpgDomainRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.bind_epg_domain(
        tenant=request.tenant,
        application_profile=request.application_profile,
        epg=request.epg,
        domain=request.domain,
        domain_type=request.domain_type,
        resolution_immediacy=request.resolution_immediacy,
        deployment_immediacy=request.deployment_immediacy,
    )
    return {
        "binding": result,
        "note": f"EPG '{request.epg}' bound to {request.domain_type} domain '{request.domain}' under tenant '{request.tenant}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
    }


@registry.register(
    name="create_contract",
    evidence="live-verified",
    evidence_note="MCP protocol + Nautobot (ADR-020 Phase A)",
    domain="cisco_aci",
    description=(
        "Create a Contract (with a single Subject binding one Filter) "
        "inside an existing Cisco ACI Tenant by writing to the Tenant's "
        "aci_contracts JSON Custom Field (Contracts/Filters have no "
        "first-class Nautobot object -- ADR-020 Phase A item 3). This tool "
        "only creates the Contract/Filter objects; bind them to an EPG's "
        "provided/consumed contracts separately by editing that EPG's "
        "aci_epg_contracts Custom Field. Use show_status(name=<tenant>) "
        "afterward."
    ),
    schema=CreateContractRequest,
)
def create_contract(request: CreateContractRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_contract(
        tenant=request.tenant,
        name=request.name,
        filter_name=request.filter_name,
        scope=request.scope,
        ether_type=request.ether_type,
        ip_protocol=request.ip_protocol,
        description=request.description,
    )
    return {
        "contract": result,
        "note": f"Contract '{request.name}' written to Nautobot under tenant '{request.tenant}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
    }


@registry.register(
    name="create_pod_policy_group",
    domain="cisco_aci",
    description=(
        "Create a fabric Pod Policy Group (Fabric > Fabric Policies > Pods > "
        "Policy Groups) and resolve its BGP Route Reflector Policy. ACI ships "
        "exactly one BGP Route Reflector Policy, named 'default', which is "
        "what this resolves to unless told otherwise. Re-running with the same "
        "name updates the group in place."
    ),
    schema=CreatePodPolicyGroupRequest,
)
def create_pod_policy_group(request: CreatePodPolicyGroupRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_pod_policy_group(
        location=request.location,
        name=request.name,
        bgp_route_reflector_policy=request.bgp_route_reflector_policy,
    )
    return {
        "pod_policy_group": result,
        "note": f"Pod Policy Group '{request.name}' written to Nautobot under Location '{_resolved_location(result, request)}'.",
    }


@registry.register(
    name="create_filter",
    domain="cisco_aci",
    description=(
        "Create a standalone Filter with one or more entries (vzEntry) in an "
        "existing Cisco ACI Tenant, with full attribute depth: source/"
        "destination port ranges, TCP flags, stateful, ARP opcode, ICMP type, "
        "DSCP match. Use this instead of create_contract when you need "
        "anything beyond a single permit-all entry. Re-creating an existing "
        "Filter name replaces its entry list."
    ),
    schema=CreateFilterRequest,
    evidence="live-verified",
    evidence_note=(
        "PBR lab 2026-09-15: Web_Fltr (tcp/80 + tcp/443) written over MCP, "
        "generated, applied; vzEntry http/https confirmed in APIC with zero faults."
    ),
)
def create_filter(request: CreateFilterRequest, *, nautobot: NautobotClient) -> dict:
    entries = [e.model_dump(exclude_none=True, exclude_defaults=False) for e in request.entries]
    result = nautobot.create_filter(
        tenant=request.tenant,
        name=request.name,
        entries=entries,
        description=request.description,
    )
    return {
        "filter": result,
        "note": f"Filter '{request.name}' written to Nautobot under tenant '{request.tenant}'. Bind it to a contract subject with create_contract_subject.",
    }


@registry.register(
    name="create_filter_entry",
    domain="cisco_aci",
    description=(
        "Append a single entry (vzEntry) to a Filter that already exists in "
        "the Tenant. Re-adding the same entry name replaces it in place."
    ),
    schema=CreateFilterEntryRequest,
)
def create_filter_entry(request: CreateFilterEntryRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_filter_entry(
        tenant=request.tenant,
        filter_name=request.filter_name,
        entry=request.entry.model_dump(exclude_none=True, exclude_defaults=False),
    )
    return {
        "filter": result,
        "note": f"Entry '{request.entry.name}' added to filter '{request.filter_name}' in tenant '{request.tenant}'.",
    }


@registry.register(
    name="create_contract_subject",
    domain="cisco_aci",
    description=(
        "Append a Subject (vzSubj) to an existing Contract, binding one or "
        "more existing Filters, with bidirectional/reverse-port/priority/DSCP "
        "control. Use this when a contract needs more than the single "
        "single-filter subject create_contract emits."
    ),
    schema=CreateContractSubjectRequest,
)
def create_contract_subject(request: CreateContractSubjectRequest, *, nautobot: NautobotClient) -> dict:
    subject: dict = {
        "name": request.name,
        "filters": request.filters,
        "apply_both_directions": request.apply_both_directions,
        "reverse_filter_ports": request.reverse_filter_ports,
    }
    if request.priority:
        subject["priority"] = request.priority
    if request.target_dscp:
        subject["target_dscp"] = request.target_dscp
    if request.description:
        subject["description"] = request.description

    result = nautobot.create_contract_subject(
        tenant=request.tenant, contract=request.contract, subject=subject
    )
    return {
        "contract": result,
        "note": f"Subject '{request.name}' added to contract '{request.contract}' in tenant '{request.tenant}'.",
    }


@registry.register(
    name="bind_epg_contract",
    domain="cisco_aci",
    description=(
        "Bind an existing Contract to an existing EPG as provider or "
        "consumer. create_contract only creates the Contract/Filter objects; "
        "this is the tool that actually puts the contract into the data path."
    ),
    schema=BindEpgContractRequest,
)
def bind_epg_contract(request: BindEpgContractRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.bind_epg_contract(
        tenant=request.tenant,
        application_profile=request.application_profile,
        epg=request.epg,
        contract=request.contract,
        relation=request.relation,
    )
    return {
        "epg_contracts": result,
        "note": f"EPG '{request.epg}' now {request.relation} contract '{request.contract}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
    }


@registry.register(
    name="create_l3out",
    evidence="live-verified",
    evidence_note="MCP protocol + Nautobot (ADR-020 Phase A, logical scope)",
    domain="cisco_aci",
    description=(
        "Create an L3Out (with a single External EPG + subnet) inside an "
        "existing Cisco ACI Tenant/VRF by writing to the Tenant's "
        "aci_l3outs JSON Custom Field (L3Outs have no first-class Nautobot "
        "object -- ADR-020 Phase A item 4). Logical-only scope: no "
        "physical interface/OSPF/BGP attachment is created -- this "
        "requires additional manual APIC configuration to pass real "
        "external traffic. Use show_status(name=<tenant>) afterward."
    ),
    schema=CreateL3OutRequest,
)
def create_l3out(request: CreateL3OutRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_l3out(
        tenant=request.tenant,
        vrf=request.vrf,
        name=request.name,
        external_epg_name=request.external_epg_name,
        subnet=request.subnet,
        description=request.description,
    )
    return {
        "l3out": result,
        "note": f"L3Out '{request.name}' written to Nautobot under tenant '{request.tenant}'/VRF '{request.vrf}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
    }


@registry.register(
    name="create_vlan_pool",
    evidence="live-verified",
    evidence_note="MCP protocol session 2026-09-04",
    domain="cisco_aci",
    description=(
        "Create or extend a fabric-wide VLAN Pool by writing to the "
        "aci_fabric_policies JSON Custom Field on the ACI Location object "
        "(ADR-020 Phase B -- fabric-wide objects have no Tenant home). "
        "Appends one encap range; creates the pool first if it doesn't "
        "already exist. Logical-only, no physical port binding. Use "
        "show_status(name=<any tenant>) afterward to check the next "
        "pipeline run."
    ),
    schema=CreateVlanPoolRequest,
)
def create_vlan_pool(request: CreateVlanPoolRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_vlan_pool(
        location=request.location,
        name=request.name,
        alloc_mode=request.alloc_mode,
        range_from=request.range_from,
        range_to=request.range_to,
        range_alloc_mode=request.range_alloc_mode,
        role=request.role,
        description=request.description,
    )
    return {
        "vlan_pool": result,
        "note": f"VLAN Pool '{request.name}' (range {request.range_from}-{request.range_to}) written to Location '{_resolved_location(result, request)}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_physical_domain",
    evidence="live-verified",
    evidence_note="MCP protocol session 2026-09-04",
    domain="cisco_aci",
    description=(
        "Create a Physical Domain, optionally bound to an existing VLAN "
        "Pool, by writing to the aci_fabric_policies JSON Custom Field on "
        "the ACI Location object (ADR-020 Phase B). Logical-only, no "
        "physical port binding -- this lab's ACI simulator has zero real "
        "leaf/spine interface data. Use show_status(name=<any tenant>) "
        "afterward."
    ),
    schema=CreatePhysicalDomainRequest,
)
def create_physical_domain(request: CreatePhysicalDomainRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_physical_domain(
        location=request.location,
        name=request.name,
        vlan_pool=request.vlan_pool,
    )
    return {
        "physical_domain": result,
        "note": f"Physical Domain '{request.name}' written to Location '{_resolved_location(result, request)}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_aep",
    evidence="live-verified",
    evidence_note="MCP protocol session 2026-09-04",
    domain="cisco_aci",
    description=(
        "Create or extend an Attachable Access Entity Profile (AEP), bound "
        "to zero or more existing Physical Domains, by writing to the "
        "aci_fabric_policies JSON Custom Field on the ACI Location object "
        "(ADR-020 Phase B). Domains are merged with any already bound on "
        "repeated calls. Use show_status(name=<any tenant>) afterward."
    ),
    schema=CreateAepRequest,
)
def create_aep(request: CreateAepRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_aep(
        location=request.location,
        name=request.name,
        # Flatten any AepDomainSpec models -- these go straight into a JSON
        # Custom Field, and a Pydantic model is not JSON-serialisable. Same
        # trap as create_concrete_device's nested interface specs.
        domains=[d if isinstance(d, str) else d.model_dump() for d in request.domains],
    )
    return {
        "aep": result,
        "note": f"AEP '{request.name}' written to Location '{_resolved_location(result, request)}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_leaf_interface_policy_group",
    evidence="live-verified",
    evidence_note="MCP protocol session 2026-09-04",
    domain="cisco_aci",
    description=(
        "Create a Leaf Interface Policy Group, optionally bound to an "
        "existing AEP, by writing to the aci_fabric_policies JSON Custom "
        "Field on the ACI Location object (ADR-020 Phase B). Logical-only, "
        "no physical leaf/port selector binding -- this lab's ACI "
        "simulator has zero real leaf/spine interface data. Use "
        "show_status(name=<any tenant>) afterward."
    ),
    schema=CreateLeafInterfacePolicyGroupRequest,
)
def create_leaf_interface_policy_group(
    request: CreateLeafInterfacePolicyGroupRequest, *, nautobot: NautobotClient
) -> dict:
    result = nautobot.create_leaf_interface_policy_group(
        location=request.location,
        name=request.name,
        aep=request.aep,
    )
    return {
        "leaf_interface_policy_group": result,
        "note": f"Leaf Interface Policy Group '{request.name}' written to Location '{_resolved_location(result, request)}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


# Ported from copilot/aci-platform-comparison (2026-09-08). Not ported:
# their duplicate create_vlan_pool/create_physical_domain/
# create_leaf_interface_policy_group (this side's own versions above are
# already live-verified, including over the real MCP protocol, and remain
# canonical), create_aaep (superseded by this side's create_aep),
# bind_epg_to_physical_domain/bind_epg_to_vmm_domain (superseded by
# bind_epg_domain below -- see schemas/aci.py's own comment on why). See
# Platform-Status-and-Pending-Items.md: the physical/protocol L3Out tools
# below are plan-validated only on this simulator (no real `pathep-[...]`
# interface data); VRF route-leak/L4-L7/PBR tools are not simulator-blocked
# but have not yet had a real apply+destroy cycle run in this repo either.
@registry.register(
    name="create_vrf_route_leak",
    domain="cisco_aci",
    description="Create shared-services or L3Out-associated VRF route-leak intent between two existing VRFs in the same Tenant. Writes to Nautobot only; Terraform applies the destination-VRF leak resource later.",
    schema=CreateVrfRouteLeakRequest,
)
def create_vrf_route_leak(request: CreateVrfRouteLeakRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_vrf_route_leak(**request.model_dump())
    return {
        "vrf_route_leak": result,
        "note": f"VRF route leak '{request.name}' written to tenant '{request.tenant}'. Review the next Terraform plan before approval.",
    }


def _fabric_tool(name: str, schema, method: str, description: str):
    def decorator(function):
        return registry.register(name=name, domain="cisco_aci", description=description, schema=schema)(function)
    return decorator


@_fabric_tool("create_leaf_interface_profile", CreateLeafInterfaceProfileRequest, "create_leaf_interface_profile", "Create a leaf interface profile intent.")
def create_leaf_interface_profile(request: CreateLeafInterfaceProfileRequest, *, nautobot: NautobotClient) -> dict:
    return {"leaf_interface_profile": nautobot.create_leaf_interface_profile(**request.model_dump())}


@registry.register(name="create_fabric_device", domain="cisco_aci", description="Create or update an ACI fabric device in Nautobot DCIM.", schema=CreateFabricDeviceRequest)
def create_fabric_device(request: CreateFabricDeviceRequest, *, nautobot: NautobotClient) -> dict:
    return {"device": nautobot.create_fabric_device(**request.model_dump())}


@registry.register(name="create_fabric_interface", domain="cisco_aci", description="Create or update a physical fabric interface in Nautobot DCIM.", schema=CreateFabricInterfaceRequest)
def create_fabric_interface(request: CreateFabricInterfaceRequest, *, nautobot: NautobotClient) -> dict:
    return {"interface": nautobot.create_fabric_interface(**request.model_dump())}


@_fabric_tool("create_interface_selector", CreateInterfaceSelectorRequest, "create_interface_selector", "Create a leaf interface selector bound to an IPG.")
def create_interface_selector(request: CreateInterfaceSelectorRequest, *, nautobot: NautobotClient) -> dict:
    return {"interface_selector": nautobot.create_interface_selector(**request.model_dump())}


@_fabric_tool("create_static_path_binding", CreateStaticPathBindingRequest, "create_static_path_binding", "Bind an EPG to a static leaf path.")
def create_static_path_binding(request: CreateStaticPathBindingRequest, *, nautobot: NautobotClient) -> dict:
    return {"static_path": nautobot.create_static_path_binding(**request.model_dump())}


@registry.register(name="create_access_port_profile", domain="cisco_aci", description="Create an APIC-equivalent access-port profile (infraAccPortP) intent.", schema=CreateAccessPortProfileRequest)
def create_access_port_profile(request: CreateAccessPortProfileRequest, *, nautobot: NautobotClient) -> dict:
    return {"access_port_profile": nautobot.create_access_port_profile(**request.model_dump())}


@registry.register(name="create_access_port_selector", domain="cisco_aci", description="Create an APIC-equivalent access-port selector (infraHPortS) intent.", schema=CreateAccessPortSelectorRequest)
def create_access_port_selector(request: CreateAccessPortSelectorRequest, *, nautobot: NautobotClient) -> dict:
    return {"access_port_selector": nautobot.create_access_port_selector(**request.model_dump())}


@registry.register(name="create_access_port_block", domain="cisco_aci", description="Create an APIC-equivalent port block (infraPortBlk) intent.", schema=CreateAccessPortBlockRequest)
def create_access_port_block(request: CreateAccessPortBlockRequest, *, nautobot: NautobotClient) -> dict:
    return {"access_port_block": nautobot.create_access_port_block(**request.model_dump())}


@registry.register(name="create_leaf_profile", domain="cisco_aci", description="Create an APIC-equivalent leaf/node profile (infraNodeP) intent.", schema=CreateLeafProfileRequest)
def create_leaf_profile(request: CreateLeafProfileRequest, *, nautobot: NautobotClient) -> dict:
    return {"leaf_profile": nautobot.create_leaf_profile(**request.model_dump())}


@registry.register(name="create_leaf_selector", domain="cisco_aci", description="Create an APIC-equivalent leaf selector (infraLeafS) intent.", schema=CreateLeafSelectorRequest)
def create_leaf_selector(request: CreateLeafSelectorRequest, *, nautobot: NautobotClient) -> dict:
    return {"leaf_selector": nautobot.create_leaf_selector(**request.model_dump())}


@registry.register(name="create_leaf_node_block", domain="cisco_aci", description="Create an APIC-equivalent node block (infraNodeBlk) intent.", schema=CreateLeafNodeBlockRequest)
def create_leaf_node_block(request: CreateLeafNodeBlockRequest, *, nautobot: NautobotClient) -> dict:
    return {"leaf_node_block": nautobot.create_leaf_node_block(**request.model_dump())}


@registry.register(name="create_bgp_l3out", domain="cisco_aci", description="Create a BGP-enabled L3Out intent in Nautobot.", schema=CreateProtocolL3OutRequest)
def create_bgp_l3out(request: CreateProtocolL3OutRequest, *, nautobot: NautobotClient) -> dict:
    return {"l3out": nautobot.create_protocol_l3out(protocol="bgp", **request.model_dump())}


@registry.register(name="create_ospf_l3out", domain="cisco_aci", description="Create an OSPF-enabled L3Out intent in Nautobot.", schema=CreateProtocolL3OutRequest)
def create_ospf_l3out(request: CreateProtocolL3OutRequest, *, nautobot: NautobotClient) -> dict:
    return {"l3out": nautobot.create_protocol_l3out(protocol="ospf", **request.model_dump())}


@registry.register(name="create_l3out_node_profile", domain="cisco_aci", description="Add a logical node profile to an L3Out.", schema=CreateL3OutNodeProfileRequest)
def create_l3out_node_profile(request: CreateL3OutNodeProfileRequest, *, nautobot: NautobotClient) -> dict:
    return {"node_profile": nautobot.create_l3out_node_profile(**request.model_dump())}


@registry.register(name="create_l3out_interface_profile", domain="cisco_aci", description="Add an interface profile to an L3Out node profile.", schema=CreateL3OutInterfaceProfileRequest)
def create_l3out_interface_profile(request: CreateL3OutInterfaceProfileRequest, *, nautobot: NautobotClient) -> dict:
    return {"interface_profile": nautobot.create_l3out_interface_profile(**request.model_dump())}


@registry.register(name="create_l3out_interface", domain="cisco_aci", description="Add an SVI or routed interface to an L3Out interface profile.", schema=CreateL3OutInterfaceRequest)
def create_l3out_interface(request: CreateL3OutInterfaceRequest, *, nautobot: NautobotClient) -> dict:
    return {"interface": nautobot.create_l3out_interface(**request.model_dump())}


@registry.register(name="create_bgp_peer", domain="cisco_aci", description="Add a BGP peer to an L3Out interface.", schema=CreateBgpPeerRequest)
def create_bgp_peer(request: CreateBgpPeerRequest, *, nautobot: NautobotClient) -> dict:
    return {"bgp_peer": nautobot.create_bgp_peer(**request.model_dump())}


@registry.register(name="create_ospf_interface", domain="cisco_aci", description="Add OSPF intent to an L3Out interface.", schema=CreateOspfInterfaceRequest)
def create_ospf_interface(request: CreateOspfInterfaceRequest, *, nautobot: NautobotClient) -> dict:
    return {"ospf_interface": nautobot.create_ospf_interface(**request.model_dump())}


@registry.register(name="create_ospf_interface_policy", domain="cisco_aci", description="Create an OSPF interface policy with network type, timers, passive control, and authentication intent.", schema=CreateOspfInterfacePolicyRequest)
def create_ospf_interface_policy(request: CreateOspfInterfacePolicyRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_ospf_interface_policy(**request.model_dump())
    return {"ospf_interface_policy": result, "note": f"OSPF interface policy '{request.name}' written to tenant '{request.tenant}'."}


@registry.register(
    name="create_vmm_domain",
    evidence="live-verified",
    evidence_note="MCP protocol session 2026-09-04, against this lab's real vCenter",
    domain="cisco_aci",
    description=(
        "Create a VMM Domain and its Controller (vCenter host/datacenter "
        "association), optionally bound to an existing VLAN Pool, by "
        "writing to the aci_fabric_policies JSON Custom Field on the ACI "
        "Location object (ADR-020 Phase D). The Controller's actual "
        "vCenter username/password are NOT part of this tool's request -- "
        "they are supplied at terraform apply time via sensitive Terraform "
        "variables, never persisted in Nautobot. Use "
        "show_status(name=<any tenant>) afterward."
    ),
    schema=CreateVmmDomainRequest,
)
def create_vmm_domain(request: CreateVmmDomainRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_vmm_domain(
        location=request.location,
        name=request.name,
        controller_name=request.controller_name,
        host_or_ip=request.host_or_ip,
        root_cont_name=request.root_cont_name,
        vendor=request.vendor,
        vlan_pool=request.vlan_pool,
        credential_name=request.credential_name,
        dvs_version=request.dvs_version,
    )
    return {
        "vmm_domain": result,
        "note": f"VMM Domain '{request.name}' written to Location '{_resolved_location(result, request)}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_security_domain",
    evidence="live-verified",
    evidence_note="MCP protocol session 2026-09-04 (ADR-020 Phase F)",
    domain="cisco_aci",
    description=(
        "Create a Security Domain (RBAC) by writing to the aci_aaa_policies "
        "JSON Custom Field on the ACI Location object (ADR-020 Phase F). "
        "Use show_status(name=<any tenant>) afterward."
    ),
    schema=CreateSecurityDomainRequest,
)
def create_security_domain(request: CreateSecurityDomainRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_security_domain(location=request.location, name=request.name, description=request.description)
    return {
        "security_domain": result,
        "note": f"Security Domain '{request.name}' written to Location '{_resolved_location(result, request)}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_local_user",
    evidence="live-verified",
    evidence_note="MCP protocol session 2026-09-04 (ADR-020 Phase F)",
    domain="cisco_aci",
    description=(
        "Create a Local User, optionally bound to one Security Domain + "
        "Role, by writing to the aci_aaa_policies JSON Custom Field on the "
        "ACI Location object (ADR-020 Phase F). The user's password is NOT "
        "part of this tool's request -- it is supplied at terraform apply "
        "time via the sensitive local_user_passwords Terraform variable, "
        "never persisted in Nautobot or seen by this tool. Use "
        "show_status(name=<any tenant>) afterward."
    ),
    schema=CreateLocalUserRequest,
)
def create_local_user(request: CreateLocalUserRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_local_user(
        location=request.location,
        name=request.name,
        email=request.email,
        first_name=request.first_name,
        last_name=request.last_name,
        phone=request.phone,
        account_status=request.account_status,
        security_domain=request.security_domain,
        role=request.role,
        priv_type=request.priv_type,
    )
    return {
        "local_user": result,
        "note": f"Local User '{request.name}' written to Location '{_resolved_location(result, request)}'. Set TF_VAR_local_user_passwords[\"{request.name}\"] before the next terraform apply. Use show_status(name=<any tenant>) to check the pipeline run.",
    }


# Ported from copilot/aci-platform-comparison (2026-09-08) -- L4-L7/PBR/
# Service Graph tools, genuinely new and non-overlapping.
@registry.register(
    name="create_l4l7_device",
    domain="cisco_aci",
    description="Create a logical Cisco ACI L4-L7 device with consumer/provider logical interfaces by writing non-secret intent to the Tenant's aci_l4l7_services Nautobot Custom Field.",
    schema=CreateL4L7DeviceRequest,
    evidence_note=(
        "Applied live 2026-09-15: vnsLDevVip is created and vnsRsALDevToDomP "
        "reaches state=formed, but APIC flags the device INVALID (8 faults, "
        "root cause vnsConfIssue-missing-cdev) because no concrete device "
        "exists. Measured A/B on a throwaway tenant: adding a vnsCDev does "
        "NOT reduce the count -- it trades those faults for vCenter-vNIC "
        "faults (F1778/F0765). 10 faults is the floor for a VIRTUAL device "
        "without a vCenter. NOT live-verified: the object exists, the "
        "deployment does not."
    ),
)
def create_l4l7_device(request: CreateL4L7DeviceRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_l4l7_device(**request.model_dump())
    return {"l4l7_device": result, "note": f"L4-L7 device '{request.name}' written to tenant '{request.tenant}'."}


@registry.register(
    name="create_concrete_device",
    domain="cisco_aci",
    description=(
        "Create a concrete device (vnsCDev) behind an existing logical L4-L7 "
        "device and bind its interfaces to that device's logical interfaces. "
        "This is what makes an L4-L7 device deployable at all: without one, "
        "APIC accepts the logical device and then flags it invalid with "
        "vnsConfIssue-missing-cdev. A VIRTUAL concrete device requires a VMM "
        "domain WITH a controller -- its ports are identified by "
        "vCenter-discovered vNIC names. A PHYSICAL one is identified by leaf "
        "port paths instead."
    ),
    schema=CreateConcreteDeviceRequest,
    evidence_note=(
        "Written 2026-09-15 to close the gap found when the PBR lab applied: "
        "main.tf already accepted vnic_name but nothing upstream could produce "
        "it, so a virtual concrete device was unexpressible. NOT live-verified "
        "-- the VIRTUAL path needs a real vCenter with the appliance VM "
        "present, and the PHYSICAL path needs leaf switches this fabric does "
        "not have. Both are blocked on lab hardware, not on this code."
    ),
)
def create_concrete_device(request: CreateConcreteDeviceRequest, *, nautobot: NautobotClient) -> dict:
    payload = request.model_dump()
    payload["interfaces"] = [i.model_dump() for i in request.interfaces]
    result = nautobot.create_concrete_device(**payload)

    bindings = ", ".join(f"{i.name}->{i.logical_interface}" for i in request.interfaces)
    note = (
        f"Concrete device '{request.name}' attached to L4-L7 device "
        f"'{request.device}' in tenant '{request.tenant}' ({bindings})."
    )
    if request.device_type.upper() == "VIRTUAL":
        note += (
            f" APIC will resolve VM '{request.vm_name}' and its vNICs through "
            f"controller '{request.vmm_controller}'. If that VM is not present in "
            "the controller's inventory the device stays invalid -- the vNIC names "
            "must match what vCenter reports."
        )
    else:
        note += (
            " The leaf path relations stay state=unformed until the named switches "
            "actually exist in the fabric."
        )
    return {"concrete_device": result, "note": note}


@registry.register(
    name="create_service_graph",
    domain="cisco_aci",
    description="Create a Cisco ACI Service Graph intent that binds an existing Contract to a logical L4-L7 device. It does not create or store service-device credentials.",
    schema=CreateServiceGraphRequest,
    evidence_note=(
        "Applied live 2026-09-15: vnsAbsGraph + vnsAbsNode created and the "
        "contract subject's vzRsSubjGraphAtt reaches state=formed, but APIC "
        "flags the graph INVALID (F0757/F1690) -- inherited from the L4-L7 "
        "device's missing concrete device, not a defect in this tool. See "
        "create_l4l7_device's note."
    ),
)
def create_service_graph(request: CreateServiceGraphRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_service_graph(**request.model_dump())
    return {"service_graph": result, "note": f"Service Graph '{request.name}' written to tenant '{request.tenant}'."}


@registry.register(
    name="create_one_arm_service_graph",
    domain="cisco_aci",
    description="Create a one-arm ADC/load-balancer Service Graph with one logical interface and one PBR redirect-policy binding. The tool writes non-secret intent to Nautobot only.",
    schema=CreateOneArmServiceGraphRequest,
)
def create_one_arm_service_graph(request: CreateOneArmServiceGraphRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_one_arm_service_graph(**request.model_dump())
    return {"service_graph": result, "note": f"One-arm Service Graph '{request.name}' written to tenant '{request.tenant}'."}


@registry.register(
    name="create_pbr_policy",
    domain="cisco_aci",
    description="Create a Cisco ACI policy-based redirect policy with one or more destinations, optional health-group tracking, IP SLA monitoring and threshold behaviour, by writing non-secret intent to the Tenant's aci_l4l7_services Nautobot Custom Field.",
    schema=CreatePbrPolicyRequest,
    evidence="live-verified",
    evidence_note=(
        "PBR lab 2026-09-15: DB_PBR (10.0.2.253) and Backup_PBR (10.0.9.253) "
        "written over MCP and applied; vnsSvcRedirectPol + vnsRedirectDest "
        "confirmed in APIC, raising zero faults of their own."
    ),
)
def create_pbr_policy(request: CreatePbrPolicyRequest, *, nautobot: NautobotClient) -> dict:
    # The schema's validator has already normalised the single-destination
    # shorthand into `destinations`, so the shorthand fields are dropped here
    # rather than reaching the client -- one destination shape, not two.
    payload = request.model_dump(exclude={"destination_ip", "destination_mac"})
    payload["destinations"] = [dest for dest in payload["destinations"]]
    result = nautobot.create_pbr_policy(**payload)
    tracked = [d for d in request.destinations if d.health_group]
    note = f"PBR policy '{request.name}' written to tenant '{request.tenant}' with {len(request.destinations)} destination(s)."
    if not tracked:
        note += (
            " WARNING: no destination is bound to a health group, so none are health-checked -- "
            "traffic keeps being redirected to a destination after it dies. Create a health group "
            "(create_pbr_health_group) and an IP SLA policy (create_ip_sla_policy), then reference them."
        )
    return {"pbr_policy": result, "note": note}


@registry.register(
    name="create_pbr_health_group",
    domain="cisco_aci",
    description="Create a Cisco ACI redirect health group (vnsRedirectHealthGroup). PBR destinations bound to a health group are health-tracked; unbound destinations keep receiving redirected traffic after they fail.",
    schema=CreatePbrHealthGroupRequest,
)
def create_pbr_health_group(request: CreatePbrHealthGroupRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_pbr_health_group(**request.model_dump())
    return {"health_group": result, "note": f"Redirect health group '{request.name}' written to tenant '{request.tenant}'. Reference it from a destination's health_group field."}


@registry.register(
    name="create_ip_sla_policy",
    domain="cisco_aci",
    description="Create a Cisco ACI IP SLA monitoring policy (fvIPSLAMonitoringPol) -- the probe that determines whether a health-tracked PBR destination is alive. Attach it to a redirect policy via its ip_sla_policy field.",
    schema=CreateIpSlaPolicyRequest,
)
def create_ip_sla_policy(request: CreateIpSlaPolicyRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_ip_sla_policy(**request.model_dump())
    return {"ip_sla_policy": result, "note": f"IP SLA monitoring policy '{request.name}' ({request.sla_type}) written to tenant '{request.tenant}'."}


@registry.register(
    name="create_pbr_contract",
    domain="cisco_aci",
    description="Create a Contract attached to a Service Graph and bind it to existing consumer and provider VLAN-backed EPGs. The tool writes intent to Nautobot only.",
    schema=CreatePbrContractRequest,
    evidence="live-verified",
    evidence_note=(
        "PBR lab 2026-09-15: FW_Ct applied; vzBrCP, its subject, the "
        "vzRsSubjGraphAtt to FW_SGT and the vnsLDevCtx device-selection "
        "policy with both vnsRsLIfCtxToSvcRedirectPol relations all reach "
        "state=formed in APIC with zero faults."
    ),
)
def create_pbr_contract(request: CreatePbrContractRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_pbr_contract(**request.model_dump())
    return {"pbr_contract": result, "note": f"PBR Contract '{request.name}' bound to EPGs in tenant '{request.tenant}'."}


# ---------------------------------------------------------------------------
# L3Out Logical Interface Profile sub-policies (2026-09-16).
#
# Before these, an l3extLIfP this platform created carried ONLY a name and a
# description. APIC auto-creates every policy relation on a new profile
# pointing at uni/tn-common/<kind>-default, so profiles were never
# unconfigured -- they silently ran on fabric defaults with no way to change
# them. Measured on the live lab before the work started.
# ---------------------------------------------------------------------------

@registry.register(
    name="create_nd_interface_policy",
    domain="cisco_aci",
    description=(
        "Create an IPv6 Neighbour Discovery interface policy (ndIfPol) in a "
        "Cisco ACI Tenant, ready to bind to an L3Out Logical Interface "
        "Profile with bind_l3out_interface_profile_policies. Omitted "
        "attributes are left for APIC to default."
    ),
    schema=CreateNdInterfacePolicyRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=ND_NOTE,
)
def create_nd_interface_policy(request: CreateNdInterfacePolicyRequest, *, nautobot: NautobotClient) -> dict:
    payload = request.model_dump()
    tenant, name = payload.pop("tenant"), payload.pop("name")
    result = nautobot.create_nd_interface_policy(tenant=tenant, name=name, **payload)
    return {"nd_interface_policy": result, "note": f"ND interface policy '{name}' written to tenant '{tenant}'."}


@registry.register(
    name="create_dpp_policy",
    domain="cisco_aci",
    description=(
        "Create a Data Plane Policing policy (qosDppPol) in a Cisco ACI "
        "Tenant. One policy serves both directions -- direction is decided "
        "by which relation binds it (ingress_dpp_policy vs "
        "egress_dpp_policy), so the same policy can be used for both. Rate "
        "and burst units are separate fields, not value suffixes."
    ),
    schema=CreateDppPolicyRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=DPP_NOTE,
)
def create_dpp_policy(request: CreateDppPolicyRequest, *, nautobot: NautobotClient) -> dict:
    payload = request.model_dump()
    tenant, name = payload.pop("tenant"), payload.pop("name")
    result = nautobot.create_dpp_policy(tenant=tenant, name=name, **payload)
    return {"dpp_policy": result, "note": f"Data plane policing policy '{name}' written to tenant '{tenant}'."}


@registry.register(
    name="create_pim_interface_policy",
    domain="cisco_aci",
    description=(
        "Create a PIM interface policy (pimIfPol) in a Cisco ACI Tenant. The "
        "same policy serves IPv4 and IPv6 -- which one it configures depends "
        "on the relation that binds it. The authentication key is "
        "deliberately not accepted here; it is supplied as a sensitive "
        "Terraform variable, never stored in Nautobot."
    ),
    schema=CreatePimInterfacePolicyRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=PIM_NOTE,
)
def create_pim_interface_policy(request: CreatePimInterfacePolicyRequest, *, nautobot: NautobotClient) -> dict:
    payload = request.model_dump()
    tenant, name = payload.pop("tenant"), payload.pop("name")
    result = nautobot.create_pim_interface_policy(tenant=tenant, name=name, **payload)
    return {"pim_interface_policy": result, "note": f"PIM interface policy '{name}' written to tenant '{tenant}'."}


@registry.register(
    name="create_igmp_interface_policy",
    domain="cisco_aci",
    description=(
        "Create an IGMP interface policy (igmpIfPol) in a Cisco ACI Tenant, "
        "ready to bind to an L3Out Logical Interface Profile."
    ),
    schema=CreateIgmpInterfacePolicyRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=IGMP_NOTE,
)
def create_igmp_interface_policy(request: CreateIgmpInterfacePolicyRequest, *, nautobot: NautobotClient) -> dict:
    payload = request.model_dump()
    tenant, name = payload.pop("tenant"), payload.pop("name")
    result = nautobot.create_igmp_interface_policy(tenant=tenant, name=name, **payload)
    return {"igmp_interface_policy": result, "note": f"IGMP interface policy '{name}' written to tenant '{tenant}'."}


@registry.register(
    name="create_custom_qos_policy",
    domain="cisco_aci",
    description=(
        "Create a Custom QoS policy (qosCustomPol) in a Cisco ACI Tenant, "
        "mapping incoming DSCP and/or dot1p values to ACI QoS levels."
    ),
    schema=CreateCustomQosPolicyRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=CQOS_NOTE,
)
def create_custom_qos_policy(request: CreateCustomQosPolicyRequest, *, nautobot: NautobotClient) -> dict:
    payload = request.model_dump()
    tenant, name = payload.pop("tenant"), payload.pop("name")
    result = nautobot.create_custom_qos_policy(tenant=tenant, name=name, **payload)
    return {"custom_qos_policy": result, "note": f"Custom QoS policy '{name}' written to tenant '{tenant}'."}


@registry.register(
    name="bind_l3out_interface_profile_policies",
    domain="cisco_aci",
    description=(
        "Bind ND / Data Plane Policing / PIM / PIMv6 / IGMP / Custom QoS "
        "policies to an existing L3Out Logical Interface Profile, and/or set "
        "its QoS priority. Each policy must already exist in the same tenant "
        "(or be a full uni/... DN). Omitting a field leaves it unchanged; "
        "there is no way to clear a binding back to the APIC default through "
        "this tool, and the literal string 'default' is rejected because APIC "
        "fails the apply on it."
    ),
    schema=BindL3OutInterfaceProfilePoliciesRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=BIND_NOTE,
)
def bind_l3out_interface_profile_policies(
    request: BindL3OutInterfaceProfilePoliciesRequest, *, nautobot: NautobotClient
) -> dict:
    payload = request.model_dump()
    tenant = payload.pop("tenant")
    l3out = payload.pop("l3out")
    node_profile = payload.pop("node_profile")
    interface_profile = payload.pop("interface_profile")
    result = nautobot.bind_l3out_interface_profile_policies(
        tenant=tenant, l3out=l3out, node_profile=node_profile,
        interface_profile=interface_profile, **payload,
    )
    bound = ", ".join(f"{k}={v}" for k, v in sorted(result["bound"].items()))
    return {
        "interface_profile_policies": result,
        "note": (
            f"Bound {bound} to interface profile '{interface_profile}' in tenant "
            f"'{tenant}'. Each referenced policy must exist in this tenant -- the "
            "generator fails the pipeline on a dangling reference, because the "
            "Terraform provider only catches it at apply time."
        ),
    }


# ---------------------------------------------------------------------------
# Route control / route maps (2026-09-16).
#
# Built for the transit-routing lab. The requirement there was to stop using
# per-subnet "Export Route Control Subnet" flags and drive export from a route
# map: permit one prefix, deny a bridge-domain subnet, and let ACI's implicit
# deny drop the rest without naming it.
#
# A route map in ACI is four objects, and they are created by three tools:
#   create_match_rule              rtctrlSubjP + rtctrlMatchRtDest
#   create_route_control_profile   rtctrlProfile + rtctrlCtxP
#   bind_..._route_control_profile l3extRsInstPToProfile
# ---------------------------------------------------------------------------

@registry.register(
    name="create_match_rule",
    domain="cisco_aci",
    description=(
        "Create a route-map match rule (rtctrlSubjP) with one or more prefixes "
        "in a Cisco ACI Tenant. Tenant-scoped, so one rule can be referenced by "
        "several route maps. Each prefix supports the Aggregate flag and "
        "greater-than/less-than mask bounds, matching APIC's own match-prefix "
        "fields. Reference it from a route map context by name."
    ),
    schema=CreateMatchRuleRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=MATCH_RULE_NOTE,
)
def create_match_rule(request: CreateMatchRuleRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_match_rule(
        tenant=request.tenant,
        name=request.name,
        prefixes=[p.model_dump() for p in request.prefixes],
        description=request.description,
    )
    prefixes = ", ".join(p.ip for p in request.prefixes)
    return {
        "match_rule": result,
        "note": f"Match rule '{request.name}' ({prefixes}) written to tenant '{request.tenant}'.",
    }


@registry.register(
    name="create_route_control_profile",
    domain="cisco_aci",
    description=(
        "Create a route map (rtctrlProfile) under an existing L3Out, with its "
        "ordered permit/deny contexts (rtctrlCtxP). An ACI route map ends in an "
        "IMPLICIT DENY, so anything no context permits is dropped -- which is "
        "what lets a route map replace per-subnet Export Route Control Subnet "
        "flags entirely. Note that a custom-named route map is INERT until "
        "something references it: only the reserved names default-export and "
        "default-import apply to an L3Out on their own. Use "
        "bind_external_epg_route_control_profile for any other name."
    ),
    schema=CreateRouteControlProfileRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=ROUTE_MAP_NOTE,
)
def create_route_control_profile(
    request: CreateRouteControlProfileRequest, *, nautobot: NautobotClient
) -> dict:
    result = nautobot.create_route_control_profile(
        tenant=request.tenant,
        l3out=request.l3out,
        name=request.name,
        contexts=[c.model_dump() for c in request.contexts],
        type=request.type,
        description=request.description,
    )
    order = " -> ".join(
        f"{c.order}:{c.name}({c.action})" for c in sorted(request.contexts, key=lambda c: c.order)
    )
    note = (
        f"Route map '{request.name}' written to L3Out '{request.l3out}' in tenant "
        f"'{request.tenant}'. Evaluation order: {order}. Anything no context permits "
        "is dropped by ACI's implicit deny."
    )
    if request.name not in ("default-export", "default-import"):
        note += (
            f" WARNING: '{request.name}' is a custom name, so this map does nothing "
            "until it is referenced -- bind it with "
            "bind_external_epg_route_control_profile, or rename it to default-export."
        )
    return {"route_control_profile": result, "note": note}


@registry.register(
    name="bind_external_epg_route_control_profile",
    domain="cisco_aci",
    description=(
        "Bind an existing route map to an external EPG for one direction "
        "(l3extRsInstPToProfile). This is what makes a custom-named route map "
        "take effect; default-export and default-import need no binding."
    ),
    schema=BindExternalEpgRouteControlProfileRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=BIND_RM_NOTE,
)
def bind_external_epg_route_control_profile(
    request: BindExternalEpgRouteControlProfileRequest, *, nautobot: NautobotClient
) -> dict:
    result = nautobot.bind_external_epg_route_control_profile(**request.model_dump())
    return {
        "route_control_binding": result,
        "note": (
            f"Route map '{request.route_control_profile}' bound to external EPG "
            f"'{request.external_epg}' for direction '{request.direction}'."
        ),
    }


@registry.register(
    name="set_external_epg_subnet_scope",
    domain="cisco_aci",
    description=(
        "Replace the scope flags on an existing external EPG subnet. This is "
        "how you switch an L3Out between per-subnet Export Route Control "
        "Subnet flags and a route map: strip export-rtctrl from the subnet and "
        "let the route map decide instead. The scope list REPLACES the current "
        "one rather than merging, and cannot be empty."
    ),
    schema=SetExternalEpgSubnetScopeRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=SCOPE_NOTE,
)
def set_external_epg_subnet_scope(
    request: SetExternalEpgSubnetScopeRequest, *, nautobot: NautobotClient
) -> dict:
    result = nautobot.set_external_epg_subnet_scope(**request.model_dump())
    return {
        "subnet_scope": result,
        "note": (
            f"Subnet '{request.ip}' on external EPG '{request.external_epg}' changed "
            f"from {result['previous_scope']} to {result['scope']}."
        ),
    }


@registry.register(
    name="bind_external_epg_contract",
    domain="cisco_aci",
    description=(
        "Provide and/or consume Contracts on an L3Out's external EPG "
        "(l3extInstP). Separate from bind_epg_contract, which works on "
        "application EPGs. Transit routing needs this: one L3Out's external "
        "EPG consumes the contract and the other provides it, or traffic "
        "between them is dropped however correct the routing is."
    ),
    schema=BindExternalEpgContractRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=CORRECTION_NOTE + " FileServices_Ct consumed by Cat_ExtNet and provided by Nexus_ExtNet; fvRsCons/fvRsProv confirmed in APIC.",
)
def bind_external_epg_contract(request: BindExternalEpgContractRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.bind_external_epg_contract(**request.model_dump())
    parts = []
    if request.provided_contracts:
        parts.append("provides " + ", ".join(request.provided_contracts))
    if request.consumed_contracts:
        parts.append("consumes " + ", ".join(request.consumed_contracts))
    return {"external_epg_contracts": result,
            "note": f"External EPG '{request.external_epg}' now {' and '.join(parts)}."}


@registry.register(
    name="add_external_epg_subnet",
    domain="cisco_aci",
    description=(
        "Add a subnet to an existing L3Out external EPG. Default scope is "
        "import-security (External Subnets for the External EPG), the "
        "classification contracts match on. Use "
        "set_external_epg_subnet_scope to change one that already exists."
    ),
    schema=AddExternalEpgSubnetRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=CORRECTION_NOTE + " 172.16.199.199/32 added to Nexus_ExtNet with scope=import-security; l3extSubnet confirmed in APIC.",
)
def add_external_epg_subnet(request: AddExternalEpgSubnetRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.add_external_epg_subnet(**request.model_dump())
    return {"external_epg_subnet": result,
            "note": (f"Subnet '{request.ip}' added to external EPG "
                     f"'{request.external_epg}' with scope {request.scope}.")}


@registry.register(
    name="add_match_rule_prefix",
    domain="cisco_aci",
    description=(
        "Add a prefix to an existing route-map match rule. Extending a deny "
        "rule is the normal way to widen a filter without rebuilding the map."
    ),
    schema=AddMatchRulePrefixRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=CORRECTION_NOTE + " 172.16.199.199/32 added to deny-prefix-out; the second rtctrlMatchRtDest confirmed in APIC.",
)
def add_match_rule_prefix(request: AddMatchRulePrefixRequest, *, nautobot: NautobotClient) -> dict:
    payload = request.model_dump()
    tenant = payload.pop("tenant")
    match_rule = payload.pop("match_rule")
    result = nautobot.add_match_rule_prefix(tenant=tenant, match_rule=match_rule, **payload)
    return {"match_rule_prefix": result,
            "note": f"Prefix '{request.ip}' added to match rule '{match_rule}' in tenant '{tenant}'."}


@registry.register(
    name="create_l3_domain",
    domain="cisco_aci",
    description=(
        "Create an external routed (L3) domain, optionally bound to a VLAN "
        "pool. An L3Out's encap VLAN must come from the pool bound to its L3 "
        "domain -- a domain with no pool leaves every L3Out encap outside any "
        "pool, which this simulator accepts but real hardware will not."
    ),
    schema=CreateL3DomainRequest,
    evidence=EVIDENCE_LEVEL,
    evidence_note=CORRECTION_NOTE + " ExtL3Dom bound to ExtL3_Pool (vlan 51-60); l3extDomP and its infraRsVlanNs relation confirmed in APIC.",
)
def create_l3_domain(request: CreateL3DomainRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_l3_domain(**request.model_dump())
    note = f"L3 domain '{request.name}' written to Location '{_resolved_location(result, request)}'."
    if not request.vlan_pool:
        note += (" WARNING: no VLAN pool bound -- any L3Out encap VLAN using this "
                 "domain will sit outside every pool.")
    return {"l3_domain": result, "note": note}
