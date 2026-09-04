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
RBAC/Security Domains/Local Users coverage.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.aci import (
    BindEpgDomainRequest,
    CreateAepRequest,
    CreateBridgeDomainRequest,
    CreateContractRequest,
    CreateEpgRequest,
    CreateL3OutRequest,
    CreateLeafInterfacePolicyGroupRequest,
    CreateLocalUserRequest,
    CreatePhysicalDomainRequest,
    CreateSecurityDomainRequest,
    CreateTenantRequest,
    CreateVlanPoolRequest,
    CreateVmmDomainRequest,
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
