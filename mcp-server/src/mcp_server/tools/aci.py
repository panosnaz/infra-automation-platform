"""Cisco ACI domain tools. Per Platform-v2-Reference-Architecture.md §7.8,
covers create_tenant, create_vrf, create_bridge_domain, create_epg,
create_contract, and create_l3out -- one tool per ADR-020 Phase A item, added
the same way once each item's generator/Terraform support landed.
Also covers create_vmm_domain for VMware VMM Domain integration.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.aci import (
    CreateBridgeDomainRequest,
    CreateContractRequest,
    CreateEpgRequest,
    CreateL3OutRequest,
    CreateL4L7DeviceRequest,
    CreateOneArmServiceGraphRequest,
    CreatePbrContractRequest,
    CreatePbrPolicyRequest,
    CreateServiceGraphRequest,
    CreateTenantRequest,
    CreateVmmDomainRequest,
    CreateVrfRouteLeakRequest,
    CreateVlanPoolRequest,
    CreatePhysicalDomainRequest,
    CreateAaepRequest,
    CreateLeafInterfacePolicyGroupRequest,
    CreateLeafInterfaceProfileRequest,
    CreateInterfaceSelectorRequest,
    CreateStaticPathBindingRequest,
    BindEpgToPhysicalDomainRequest,
    BindEpgToVmmDomainRequest,
    CreateProtocolL3OutRequest,
    CreateL3OutNodeProfileRequest,
    CreateL3OutInterfaceProfileRequest,
    CreateL3OutInterfaceRequest,
    CreateBgpPeerRequest,
    CreateOspfInterfaceRequest,
    CreateOspfInterfacePolicyRequest,
    CreateVrfRequest,
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
        description=request.description,
    )
    return {
        "epg": vlan,
        "note": f"EPG '{request.name}' (Application Profile '{request.application_profile}') written to Nautobot under tenant '{request.tenant}'. Use show_status(name='{request.tenant}') to check the next pipeline run.",
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


@_fabric_tool("create_vlan_pool", CreateVlanPoolRequest, "create_vlan_pool", "Create a fabric VLAN pool and ranges in Nautobot.")
def create_vlan_pool(request: CreateVlanPoolRequest, *, nautobot: NautobotClient) -> dict:
    return {"vlan_pool": nautobot.create_vlan_pool(**request.model_dump())}


@_fabric_tool("create_physical_domain", CreatePhysicalDomainRequest, "create_physical_domain", "Create a physical ACI domain bound to a VLAN pool.")
def create_physical_domain(request: CreatePhysicalDomainRequest, *, nautobot: NautobotClient) -> dict:
    return {"physical_domain": nautobot.create_physical_domain(**request.model_dump())}


@_fabric_tool("create_aaep", CreateAaepRequest, "create_aaep", "Create an ACI AAEP and associate domains.")
def create_aaep(request: CreateAaepRequest, *, nautobot: NautobotClient) -> dict:
    return {"aaep": nautobot.create_aaep(**request.model_dump())}


@_fabric_tool("create_leaf_interface_policy_group", CreateLeafInterfacePolicyGroupRequest, "create_leaf_interface_policy_group", "Create a leaf interface policy group bound to an AAEP.")
def create_leaf_interface_policy_group(request: CreateLeafInterfacePolicyGroupRequest, *, nautobot: NautobotClient) -> dict:
    return {"leaf_interface_policy_group": nautobot.create_leaf_interface_policy_group(**request.model_dump())}


@_fabric_tool("create_leaf_interface_profile", CreateLeafInterfaceProfileRequest, "create_leaf_interface_profile", "Create a leaf interface profile intent.")
def create_leaf_interface_profile(request: CreateLeafInterfaceProfileRequest, *, nautobot: NautobotClient) -> dict:
    return {"leaf_interface_profile": nautobot.create_leaf_interface_profile(**request.model_dump())}


@_fabric_tool("create_interface_selector", CreateInterfaceSelectorRequest, "create_interface_selector", "Create a leaf interface selector bound to an IPG.")
def create_interface_selector(request: CreateInterfaceSelectorRequest, *, nautobot: NautobotClient) -> dict:
    return {"interface_selector": nautobot.create_interface_selector(**request.model_dump())}


@_fabric_tool("create_static_path_binding", CreateStaticPathBindingRequest, "create_static_path_binding", "Bind an EPG to a static leaf path.")
def create_static_path_binding(request: CreateStaticPathBindingRequest, *, nautobot: NautobotClient) -> dict:
    return {"static_path": nautobot.create_static_path_binding(**request.model_dump())}


@_fabric_tool("bind_epg_to_physical_domain", BindEpgToPhysicalDomainRequest, "bind_epg_to_physical_domain", "Bind an EPG to a physical domain.")
def bind_epg_to_physical_domain(request: BindEpgToPhysicalDomainRequest, *, nautobot: NautobotClient) -> dict:
    return {"binding": nautobot.bind_epg_to_physical_domain(**request.model_dump())}


@_fabric_tool("bind_epg_to_vmm_domain", BindEpgToVmmDomainRequest, "bind_epg_to_vmm_domain", "Bind an EPG to a VMM domain.")
def bind_epg_to_vmm_domain(request: BindEpgToVmmDomainRequest, *, nautobot: NautobotClient) -> dict:
    return {"binding": nautobot.bind_epg_to_vmm_domain(**request.model_dump())}


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
        "Create a VMware VMM Domain and vCenter Controller by writing a "
        "vmm_domains entry to the aci_fabric_policies JSON Custom Field "
        "on a Nautobot Location. vCenter credentials are supplied later "
        "at Terraform runtime, not through this tool."
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
        "note": f"VMM Domain '{request.name}' written to Location '{request.location}'. Check the next GitLab pipeline run before applying to APIC/vCenter.",
    }


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
    description="Create a Cisco ACI policy-based redirect policy with one destination by writing non-secret intent to the Tenant's aci_l4l7_services Nautobot Custom Field.",
    schema=CreatePbrPolicyRequest,
)
def create_pbr_policy(request: CreatePbrPolicyRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_pbr_policy(**request.model_dump())
    return {"pbr_policy": result, "note": f"PBR policy '{request.name}' written to tenant '{request.tenant}'."}


@registry.register(
    name="create_pbr_contract",
    domain="cisco_aci",
    description="Create a Contract attached to a Service Graph and bind it to existing consumer and provider VLAN-backed EPGs. The tool writes intent to Nautobot only.",
    schema=CreatePbrContractRequest,
)
def create_pbr_contract(request: CreatePbrContractRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.create_pbr_contract(**request.model_dump())
    return {"pbr_contract": result, "note": f"PBR Contract '{request.name}' bound to EPGs in tenant '{request.tenant}'."}
