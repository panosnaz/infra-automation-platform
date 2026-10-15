"""Cisco ACI L3Out depth tools (2026-10-16): static routes, loopbacks, vPC
SVIs, and the BFD / BGP / OSPF / route-tag policies that L3Outs and VRFs use.

BFD is bound with bind_l3out_interface_profile_policies(bfd_interface_policy=)
and the VRF-wide policies with update_vrf; deleting a policy is
delete_tenant_object (refused while anything uses it); read is
get_tenant_intent. What none of them can set is declared per tool.

Imported by tools/aci.py, so importing the ACI tools registers these too.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.aci_l3out_depth import (
    CreateBfdInterfacePolicyRequest,
    CreateBgpBestPathPolicyRequest,
    CreateBgpRouteSummarizationPolicyRequest,
    CreateBgpTimersPolicyRequest,
    CreateL3OutStaticRouteRequest,
    CreateL3OutVpcSviRequest,
    CreateOspfTimersPolicyRequest,
    CreateRouteTagPolicyRequest,
    DeleteL3OutStaticRouteRequest,
    DeleteL3OutVpcSviRequest,
    L3OutLoopbackRequest,
    SetExternalSubnetRouteSummarizationRequest,
    SetL3OutBgpPoliciesRequest,
)
from mcp_server.tools.registry import registry


_LIVE = (
    "2026-10-16. Over the real MCP protocol against live Nautobot: 60/60 checks -- every write read back via "
    "REST, the APIC's own rules refused by name (hold <= keepalive incl. against the default keepalive, bounds "
    "measured on APIC 6.2, unpaired vPC leaves, side addresses in different subnets, duplicates), deletes "
    "refused while a VRF / L3Out / profile / subnet uses the policy, the generator run against live inventory, "
    "everything cleared through the tools, tenant deleted, Location byte-identical. Terraform: "
    "tests/fixtures/l3out-depth.yaml in an isolated state, 14/14: a VRF without depth intent plans no change; "
    "full apply, every object and relation read back 'formed', re-plan 'No changes'; all depth intent removed "
    "in one apply -- VRF relations back to tn-common defaults, nothing dangling; destroy; faults at baseline."
)


def _register(name: str, schema, description: str, not_settable: tuple[str, ...] = ()):
    return registry.register(name=name, domain="cisco_aci", description=description, schema=schema,
                             evidence="live-verified", evidence_note=_LIVE, not_settable=not_settable)


def _fields(request, *skip):
    return {k: v for k, v in request.model_dump().items() if k not in skip}


# --- tenant policies -------------------------------------------------------------------

@_register("create_bfd_interface_policy", CreateBfdInterfacePolicyRequest,
           "Create a BFD interface policy (timers, detect multiplier, echo) in a tenant. Bind it to an L3Out "
           "interface profile with bind_l3out_interface_profile_policies(bfd_interface_policy=...); turn BFD on for "
           "a static route with create_l3out_static_route(bfd=true).", not_settable=("NS-27",))
def create_bfd_interface_policy(request: CreateBfdInterfacePolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_bfd_interface_policy(**_fields(request))


@_register("create_bgp_timers_policy", CreateBgpTimersPolicyRequest,
           "Create a BGP timers policy (keepalive, hold, stale, graceful restart, max AS-path length). Use it for a "
           "whole VRF (update_vrf bgp_timers_policy=) or one L3Out (set_l3out_bgp_policies). The hold interval must "
           "be greater than the keepalive -- an omitted one counts as APIC's default (60 / 180).")
def create_bgp_timers_policy(request: CreateBgpTimersPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_bgp_timers_policy(**_fields(request))


@_register("create_bgp_best_path_policy", CreateBgpBestPathPolicyRequest,
           "Create a BGP best-path policy (AS-path multipath relax). Use it on an L3Out with set_l3out_bgp_policies.")
def create_bgp_best_path_policy(request: CreateBgpBestPathPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_bgp_best_path_policy(**_fields(request))


@_register("create_bgp_route_summarization_policy", CreateBgpRouteSummarizationPolicyRequest,
           "Create a BGP route summarization policy. Apply it to an external EPG subnet with "
           "set_external_subnet_route_summarization; the subnet is then advertised as one summary.")
def create_bgp_route_summarization_policy(request: CreateBgpRouteSummarizationPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_bgp_route_summarization_policy(**_fields(request))


@_register("create_ospf_timers_policy", CreateOspfTimersPolicyRequest,
           "Create an OSPF timers policy (reference bandwidth, distance, max ECMP, SPF throttle). Use it for a VRF "
           "with update_vrf(ospf_timers_policy=...).", not_settable=("NS-28",))
def create_ospf_timers_policy(request: CreateOspfTimersPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_ospf_timers_policy(**_fields(request))


@_register("create_route_tag_policy", CreateRouteTagPolicyRequest,
           "Create a route tag policy: the tag a VRF stamps on routes it redistributes, used to stop loops in transit "
           "designs. Use it with update_vrf(route_tag_policy=...).")
def create_route_tag_policy(request: CreateRouteTagPolicyRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_route_tag_policy(**_fields(request))


# --- static routes / loopbacks --------------------------------------------------------------

@_register("create_l3out_static_route", CreateL3OutStaticRouteRequest,
           "Add a static route on a border leaf of an L3Out, with next hops (or none: a null route) and optional "
           "BFD tracking.", not_settable=("NS-28",))
def create_l3out_static_route(request: CreateL3OutStaticRouteRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_l3out_static_route(**_fields(request))


@_register("delete_l3out_static_route", DeleteL3OutStaticRouteRequest, "Remove a static route from a border leaf of an L3Out.")
def delete_l3out_static_route(request: DeleteL3OutStaticRouteRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_l3out_static_route(**_fields(request))


@_register("create_l3out_loopback", L3OutLoopbackRequest,
           "Add a loopback address on a border leaf of an L3Out -- typically the source for BGP loopback peering.")
def create_l3out_loopback(request: L3OutLoopbackRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_l3out_loopback(**_fields(request))


@_register("delete_l3out_loopback", L3OutLoopbackRequest, "Remove a loopback address from a border leaf of an L3Out.")
def delete_l3out_loopback(request: L3OutLoopbackRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_l3out_loopback(**_fields(request))


# --- vPC SVI ------------------------------------------------------------------------------------

@_register("create_l3out_vpc_svi", CreateL3OutVpcSviRequest,
           "Add an SVI over a vPC to an L3Out interface profile: one VLAN, one address per leaf (side A / B). The "
           "policy group must be a vPC policy group and a vPC domain must pair the two leaves.", not_settable=("NS-28",))
def create_l3out_vpc_svi(request: CreateL3OutVpcSviRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.create_l3out_vpc_svi(**_fields(request))


@_register("delete_l3out_vpc_svi", DeleteL3OutVpcSviRequest,
           "Remove a vPC SVI from an L3Out interface profile. Refused while BGP peers are configured on it.")
def delete_l3out_vpc_svi(request: DeleteL3OutVpcSviRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_l3out_vpc_svi(**_fields(request))


# --- references -----------------------------------------------------------------------------------

@_register("set_l3out_bgp_policies", SetL3OutBgpPoliciesRequest,
           "Set a BGP L3Out's BGP timers and/or best-path policy (an empty string removes one). Refused on a "
           "non-BGP L3Out, where nothing would carry them.", not_settable=("NS-28",))
def set_l3out_bgp_policies(request: SetL3OutBgpPoliciesRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_l3out_bgp_policies(**_fields(request))


@_register("set_external_subnet_route_summarization", SetExternalSubnetRouteSummarizationRequest,
           "Summarise an external EPG subnet with a BGP route summarization policy (an empty string removes it).")
def set_external_subnet_route_summarization(request: SetExternalSubnetRouteSummarizationRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.set_external_subnet_route_summarization(**_fields(request))
