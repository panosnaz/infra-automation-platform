"""Cisco ACI Endpoint Security Group and vzAny tools (2026-10-15).

ESG: create / update, EPG / IP subnet / tag selectors, contracts. Delete is
`delete_tenant_object(kind='esg')`; read is `get_tenant_intent`. vzAny:
contracts per VRF here; the VRF preferred-group switch is
`update_vrf(preferred_group=...)`. What none of them can set is declared per
tool (not_settable=, see mcp_server/not_settable.py).

Imported by tools/aci.py, so importing the ACI tools registers these too.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.aci_security import (
    CreateEsgEpgSelectorRequest,
    CreateEsgIpSubnetSelectorRequest,
    CreateEsgRequest,
    CreateEsgTagSelectorRequest,
    DeleteEsgSelectorRequest,
    EsgContractRequest,
    UpdateEsgRequest,
    VzAnyContractRequest,
)
from mcp_server.tools.registry import registry


_LIVE = (
    "2026-10-15. Over the real MCP protocol against live Nautobot: 56/56 checks -- every write read back via "
    "REST, every APIC conflict rule refused by name (EPG from another VRF, EPG in two ESGs, subnet / tag in two "
    "ESGs of a VRF, vzAny providing a non-VRF-scoped contract), deletes refused while an ESG or vzAny holds the "
    "EPG / contract / VRF, the generator run against live Nautobot, the throwaway tenant deleted. Terraform: "
    "tests/fixtures/esg-vzany.yaml applied, every value read back from APIC with all relations 'formed', no "
    "new faults; intent cleared and applied, the APIC matched; vzAny scoping proven 14/14 (an untouched VRF's "
    "hand-made vzAny left alone, preferred-group-only intent leaves contracts unmanaged, tool-shaped clearing "
    "removes, dropping the intent keeps the last values -- NS-26); destroy, tenant gone, faults at baseline."
)


def _register(name: str, schema, description: str, not_settable: tuple[str, ...] = ()):
    return registry.register(name=name, domain="cisco_aci", description=description, schema=schema,
                             evidence="live-verified", evidence_note=_LIVE, not_settable=not_settable)


# --- ESG ----------------------------------------------------------------------------

@_register("create_esg", CreateEsgRequest,
           "Create an Endpoint Security Group: a security classification by selectors (EPGs, IP subnets, tags) "
           "instead of by attachment EPG, with its own contracts. It belongs to one VRF, chosen now (update_esg "
           "does not change it). Add members with create_esg_epg_selector / create_esg_ip_subnet_selector / "
           "create_esg_tag_selector and contracts with bind_esg_contract. An ESG with no selector has no members.",
           not_settable=("NS-24",))
def create_esg(request: CreateEsgRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_esg(request.tenant, request.application_profile, request.name, request.vrf,
                               request.description, request.preferred_group_member,
                               request.intra_esg_isolation, request.shutdown)


@_register("update_esg", UpdateEsgRequest,
           "Change an existing ESG's description, preferred-group membership, intra-ESG isolation or shutdown. "
           "Only the fields you pass change; to return one to its APIC default, pass the default value.",
           not_settable=("NS-24",))
def update_esg(request: UpdateEsgRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.update_esg(request.tenant, request.name, request.description, request.preferred_group_member,
                               request.intra_esg_isolation, request.shutdown)


# --- selectors ------------------------------------------------------------------------

@_register("create_esg_epg_selector", CreateEsgEpgSelectorRequest,
           "Make every endpoint of an EPG a member of an ESG. The EPG must be in the ESG's VRF and can be "
           "selected by only one ESG -- both are refused here; APIC would reject them at apply time.")
def create_esg_epg_selector(request: CreateEsgEpgSelectorRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_esg_epg_selector(request.tenant, request.esg, request.application_profile,
                                            request.epg, request.description)


@_register("create_esg_ip_subnet_selector", CreateEsgIpSubnetSelectorRequest,
           "Make endpoints whose IP is in a host or subnet members of an ESG. One subnet can be in only one ESG "
           "per VRF.", not_settable=("NS-25",))
def create_esg_ip_subnet_selector(request: CreateEsgIpSubnetSelectorRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_esg_ip_subnet_selector(request.tenant, request.esg, request.subnet, request.description)


@_register("create_esg_tag_selector", CreateEsgTagSelectorRequest,
           "Make endpoints carrying a tag (key = value) members of an ESG. One key=value can be in only one ESG "
           "per VRF. The tags themselves are NOT set by this platform -- until an endpoint is tagged on the APIC "
           "the selector matches nothing.",
           not_settable=("NS-25",))
def create_esg_tag_selector(request: CreateEsgTagSelectorRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_esg_tag_selector(request.tenant, request.esg, request.key, request.value,
                                            request.operator, request.description)


@_register("delete_esg_selector", DeleteEsgSelectorRequest,
           "Remove one selector from an ESG: an EPG (application_profile + epg), an IP subnet (subnet) or a tag "
           "(key + value). Its endpoints leave the ESG.")
def delete_esg_selector(request: DeleteEsgSelectorRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_esg_selector(request.tenant, request.esg, request.selector_type,
                                        application_profile=request.application_profile, epg=request.epg,
                                        subnet=request.subnet, key=request.key, value=request.value)


# --- contracts ---------------------------------------------------------------------------

@_register("bind_esg_contract", EsgContractRequest,
           "Make an ESG provide or consume a contract of the same tenant.", not_settable=("NS-24",))
def bind_esg_contract(request: EsgContractRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.bind_esg_contract(request.tenant, request.esg, request.contract, request.relation)


@_register("unbind_esg_contract", EsgContractRequest, "Stop an ESG providing or consuming a contract.")
def unbind_esg_contract(request: EsgContractRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.unbind_esg_contract(request.tenant, request.esg, request.contract, request.relation)


@_register("bind_vzany_contract", VzAnyContractRequest,
           "Make vzAny of a VRF provide or consume a contract: the contract then applies to EVERY EPG and ESG in "
           "that VRF -- e.g. one 'shared services' contract consumed by all of them. Use with care. vzAny is "
           "managed only for VRFs given vzAny intent; this makes the VRF one. vzAny can PROVIDE only contracts "
           "whose scope is 'context' (VRF); it can consume any.",
           not_settable=("NS-24", "NS-26"))
def bind_vzany_contract(request: VzAnyContractRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.bind_vzany_contract(request.tenant, request.vrf, request.contract, request.relation)


@_register("unbind_vzany_contract", VzAnyContractRequest,
           "Remove a contract from vzAny of a VRF. The VRF stays managed, so the relation is removed on the APIC.",
           not_settable=("NS-26",))
def unbind_vzany_contract(request: VzAnyContractRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.unbind_vzany_contract(request.tenant, request.vrf, request.contract, request.relation)
