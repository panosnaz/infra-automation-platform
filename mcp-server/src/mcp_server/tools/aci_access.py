"""Cisco ACI port-channel / vPC and node management tools (2026-10-12).

Configure and update live here. Read is get_fabric_intent (vPC domains, LACP
and PC/vPC policy groups, in-band EPGs, and every node's management
addresses) and get_tenant_intent (each EPG's static paths). Delete is
delete_fabric_object for the four new fabric kinds -- with the same refusal
while referenced -- plus delete_node_mgmt_address and unbind_epg_static_path
here.

Imported by tools/aci.py, so importing the ACI tools registers these too.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.aci_access import (
    CreateInbandMgmtEpgRequest,
    CreateLacpPolicyRequest,
    CreateNodeMgmtAddressRequest,
    CreatePcVpcPolicyGroupRequest,
    CreateVpcDomainRequest,
    DeleteNodeMgmtAddressRequest,
    UnbindEpgStaticPathRequest,
    UpdateInbandMgmtEpgRequest,
    UpdateLacpPolicyRequest,
    UpdateNodeMgmtAddressRequest,
    UpdatePcVpcPolicyGroupRequest,
    UpdateVpcDomainRequest,
)
from mcp_server.tools.registry import registry

_LIVE = (
    "2026-10-12. Over the real MCP protocol against live Nautobot: 68/68 checks (throwaway "
    "switches 901/902, objects lcv-*) -- every write read back via Nautobot REST, every "
    "refusal confirmed to write nothing, the generator run against live Nautobot, the real "
    "Location's intent byte-identical afterwards. Terraform: the same object kinds applied "
    "and destroyed against the lab APIC from tests/fixtures/pc-vpc-mgmt.yaml (28 added, 28 "
    "destroyed), read back from APIC -- AEP/LACP/selector/in-band-BD relations formed, "
    "paths and node addresses unformed (no switches); only new faults F1298 'Node Cannot "
    "Deploy', 41 before / 41 after destroy."
)


def _register(name: str, schema, description: str, not_settable: tuple[str, ...] = ()):
    return registry.register(name=name, domain="cisco_aci", description=description, schema=schema,
                             evidence="live-verified", evidence_note=_LIVE, not_settable=not_settable)


# --- LACP ---------------------------------------------------------------------

@_register("create_lacp_policy", CreateLacpPolicyRequest,
           "Create a named LACP policy (Fabric > Access Policies > Policies > Interface > Port Channel) "
           "that PC/vPC policy groups reference. Mode 'active' is the usual choice for a switch or server "
           "running LACP.",
           not_settable=("NS-04",))
def create_lacp_policy(request: CreateLacpPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_lacp_policy(request.location, request.name, request.mode,
                                       request.min_links, request.max_links, request.controls)


@_register("update_lacp_policy", UpdateLacpPolicyRequest,
           "Change an existing LACP policy's mode, min/max links or control flags. Only the fields passed change.",
           not_settable=("NS-04",))
def update_lacp_policy(request: UpdateLacpPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_lacp_policy(request.location, request.name, mode=request.mode,
                                       min_links=request.min_links, max_links=request.max_links,
                                       controls=request.controls)


# --- vPC domain -----------------------------------------------------------------

@_register("create_vpc_domain", CreateVpcDomainRequest,
           "Pair two leaves into a vPC domain (an explicit VPC protection group, Fabric > Access Policies > "
           "Policies > Switch > Virtual Port Channel default). Refuses a leaf that is not in the Nautobot fabric "
           "inventory, a leaf already in another vPC pair, and a domain ID already in use.",
           not_settable=("NS-05",))
def create_vpc_domain(request: CreateVpcDomainRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_vpc_domain(request.location, request.name, request.domain_id, request.node1, request.node2)


@_register("update_vpc_domain", UpdateVpcDomainRequest,
           "Change a vPC domain's ID or its leaves. Changing the leaves is refused while any EPG is still bound "
           "to a vPC on the old pair.",
           not_settable=("NS-05",))
def update_vpc_domain(request: UpdateVpcDomainRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_vpc_domain(request.location, request.name, request.domain_id, request.node1, request.node2)


# --- PC / vPC policy group --------------------------------------------------------

@_register("create_pc_vpc_policy_group", CreatePcVpcPolicyGroupRequest,
           "Create a PC or vPC interface policy group (bundle). Bind it to ports with create_access_port_selector "
           "(on each leaf's interface profile) and to EPGs with create_static_path_binding(path_type='port_channel' "
           "or 'vpc'). The AEP and LACP policy must already exist.",
           not_settable=("NS-02",))
def create_pc_vpc_policy_group(request: CreatePcVpcPolicyGroupRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_pc_vpc_policy_group(request.location, request.name, request.bundle_type,
                                               request.aep, request.lacp_policy, request.description)


@_register("update_pc_vpc_policy_group", UpdatePcVpcPolicyGroupRequest,
           "Change a PC/vPC policy group's AEP, LACP policy or description. The bundle type cannot change.",
           not_settable=("NS-02",))
def update_pc_vpc_policy_group(request: UpdatePcVpcPolicyGroupRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_pc_vpc_policy_group(request.location, request.name, request.aep,
                                               request.lacp_policy, request.description)


# --- Management -------------------------------------------------------------------

@_register("create_inband_mgmt_epg", CreateInbandMgmtEpgRequest,
           "Create an in-band management EPG in tenant mgmt (encap VLAN + the 'inb' bridge domain). Needed "
           "before any in-band node address. Out-of-band needs nothing: it uses the built-in OOB EPG 'default'.",
           not_settable=("NS-08",))
def create_inband_mgmt_epg(request: CreateInbandMgmtEpgRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_inband_mgmt_epg(request.location, request.name, request.encap_vlan, request.bridge_domain)


@_register("update_inband_mgmt_epg", UpdateInbandMgmtEpgRequest,
           "Change an in-band management EPG's encap VLAN or bridge domain.",
           not_settable=("NS-08",))
def update_inband_mgmt_epg(request: UpdateInbandMgmtEpgRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_inband_mgmt_epg(request.location, request.name, request.encap_vlan, request.bridge_domain)


@_register("create_node_mgmt_address", CreateNodeMgmtAddressRequest,
           "Give a fabric switch a static out-of-band or in-band management address. Stored as a native Nautobot "
           "IP Address on the switch's management interface (mgmt0 / inband-mgmt, created if missing), so IPAM "
           "refuses a duplicate. If Nautobot holds no prefix for the subnet, one is created and reported. One "
           "address per switch per type.",
           not_settable=("NS-07", "NS-08"))
def create_node_mgmt_address(request: CreateNodeMgmtAddressRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_node_mgmt_address(request.node, request.type, request.address, request.gateway,
                                             request.epg, request.location)


@_register("update_node_mgmt_address", UpdateNodeMgmtAddressRequest,
           "Change a switch's management address, gateway or (in-band) EPG. A new address replaces the old IP "
           "Address on the same interface.",
           not_settable=("NS-07", "NS-08"))
def update_node_mgmt_address(request: UpdateNodeMgmtAddressRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_node_mgmt_address(request.node, request.type, request.address, request.gateway,
                                             request.epg, request.location)


@_register("delete_node_mgmt_address", DeleteNodeMgmtAddressRequest,
           "Remove a switch's out-of-band or in-band management address. The interface itself is kept.")
def delete_node_mgmt_address(request: DeleteNodeMgmtAddressRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_node_mgmt_address(request.node, request.type)


# --- EPG static path removal -----------------------------------------------------

@_register("unbind_epg_static_path", UnbindEpgStaticPathRequest,
           "Remove one static path (port, port-channel or vPC) from an EPG, leaving its other paths in place. "
           "Inverse of create_static_path_binding.")
def unbind_epg_static_path(request: UnbindEpgStaticPathRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.unbind_epg_static_path(request.tenant, request.application_profile, request.epg,
                                           request.as_path())
