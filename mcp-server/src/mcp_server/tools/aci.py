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



@registry.register(
    name="create_tenant",
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
    )
    return {
        "prefix": prefix,
        "note": f"Bridge Domain '{request.name}' written to Nautobot under tenant '{request.tenant}'/VRF '{request.vrf}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
    }


@registry.register(
    name="create_epg",
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
        "note": f"Pod Policy Group '{request.name}' written to Nautobot under location '{request.location}'.",
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
        "note": f"VLAN Pool '{request.name}' (range {request.range_from}-{request.range_to}) written to Location '{request.location}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_physical_domain",
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
        "note": f"Physical Domain '{request.name}' written to Location '{request.location}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_aep",
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
        domains=request.domains,
    )
    return {
        "aep": result,
        "note": f"AEP '{request.name}' written to Location '{request.location}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_leaf_interface_policy_group",
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
        "note": f"Leaf Interface Policy Group '{request.name}' written to Location '{request.location}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
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
        "note": f"VMM Domain '{request.name}' written to Location '{request.location}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_security_domain",
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
        "note": f"Security Domain '{request.name}' written to Location '{request.location}'. Use show_status(name=<any tenant>) to check the next pipeline run.",
    }


@registry.register(
    name="create_local_user",
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
        "note": f"Local User '{request.name}' written to Location '{request.location}'. Set TF_VAR_local_user_passwords[\"{request.name}\"] before the next terraform apply. Use show_status(name=<any tenant>) to check the pipeline run.",
    }


# Ported from copilot/aci-platform-comparison (2026-09-08) -- L4-L7/PBR/
# Service Graph tools, genuinely new and non-overlapping.
@registry.register(
    name="create_l4l7_device",
    domain="cisco_aci",
    description="Create a logical Cisco ACI L4-L7 device with consumer/provider logical interfaces by writing non-secret intent to the Tenant's aci_l4l7_services Nautobot Custom Field.",
    schema=CreateL4L7DeviceRequest,
)
def create_l4l7_device(request: CreateL4L7DeviceRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_l4l7_device(**request.model_dump())
    return {"l4l7_device": result, "note": f"L4-L7 device '{request.name}' written to tenant '{request.tenant}'."}


@registry.register(
    name="create_service_graph",
    domain="cisco_aci",
    description="Create a Cisco ACI Service Graph intent that binds an existing Contract to a logical L4-L7 device. It does not create or store service-device credentials.",
    schema=CreateServiceGraphRequest,
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
)
def create_pbr_contract(request: CreatePbrContractRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_pbr_contract(**request.model_dump())
    return {"pbr_contract": result, "note": f"PBR Contract '{request.name}' bound to EPGs in tenant '{request.tenant}'."}

