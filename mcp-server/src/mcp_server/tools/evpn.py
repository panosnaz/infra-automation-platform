"""VXLAN EVPN domain tools (ADR-021). Covers create_evpn_tenant,
create_evpn_vrf, create_evpn_bridge_domain -- the first EVPN MCP tools,
mirroring tools/aci.py's exact pattern (thin schema, direct Nautobot write,
no intent envelope, per ADR-018). Domain-isolated from tools/aci.py: this
module never imports from it, and vice versa.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.schemas.evpn import (
    CreateEvpnBridgeDomainRequest,
    CreateEvpnVrfRequest,
    CreateEvpnTenantRequest,
)
from mcp_server.tools.registry import registry


@registry.register(
    name="create_evpn_tenant",
    domain="vxlan_evpn",
    description=(
        "Create a new VXLAN EVPN Tenant by writing a Tenant object "
        "(name prefixed 'EVPN:') directly to Nautobot (the Source of "
        "Truth). This triggers Nautobot's tenancy.tenant webhook, which "
        "starts the EVPN GitLab CI pipeline once it is wired into the "
        "root pipeline (ADR-021 -- not yet, pending a Nexus 9Kv "
        "simulator). Use show_status afterward to check on the deployment."
    ),
    schema=CreateEvpnTenantRequest,
)
def create_evpn_tenant(request: CreateEvpnTenantRequest, *, nautobot: NautobotClient) -> dict:
    tenant = nautobot.create_tenant(name=f"EVPN:{request.name}", description=request.description)
    return {
        "tenant": tenant,
        "note": (
            "Tenant written to Nautobot with the 'EVPN:' namespace prefix. "
            "The EVPN pipeline is not yet wired into the root GitLab "
            "pipeline (ADR-021) -- this write will not trigger a deployment "
            "until that is resolved."
        ),
    }


@registry.register(
    name="create_evpn_vrf",
    domain="vxlan_evpn",
    description=(
        "Create a VRF inside an existing VXLAN EVPN Tenant by writing an "
        "ipam.vrf object directly to Nautobot, with its L3 VNI set via the "
        "evpn_l3_vni Custom Field (ADR-021 §2). Use "
        "show_status(name=<tenant>) afterward."
    ),
    schema=CreateEvpnVrfRequest,
)
def create_evpn_vrf(request: CreateEvpnVrfRequest, *, nautobot: NautobotClient) -> dict:
    vrf = nautobot.create_evpn_vrf(
        tenant=f"EVPN:{request.tenant}",
        name=request.name,
        l3_vni=request.l3_vni,
        description=request.description,
    )
    return {
        "vrf": vrf,
        "note": f"VRF written to Nautobot under tenant 'EVPN:{request.tenant}' with L3 VNI {request.l3_vni}.",
    }


@registry.register(
    name="create_evpn_bridge_domain",
    domain="vxlan_evpn",
    description=(
        "Create a Bridge Domain inside an existing VXLAN EVPN Tenant/VRF "
        "by writing a Nautobot VLAN object directly (the Bridge Domain "
        "IS a VLAN in this domain, unlike ACI's Prefix-description "
        "encoding -- ADR-021 §2), with its L2 VNI and VRF association set "
        "via Custom Fields. Use show_status(name=<tenant>) afterward."
    ),
    schema=CreateEvpnBridgeDomainRequest,
)
def create_evpn_bridge_domain(request: CreateEvpnBridgeDomainRequest, *, nautobot: NautobotClient) -> dict:
    vlan = nautobot.create_evpn_bridge_domain(
        tenant=f"EVPN:{request.tenant}",
        vrf=request.vrf,
        name=request.name,
        vlan_id=request.vlan_id,
        l2_vni=request.l2_vni,
        description=request.description,
    )
    return {
        "vlan": vlan,
        "note": f"Bridge Domain '{request.name}' (VLAN {request.vlan_id}, L2 VNI {request.l2_vni}) written to Nautobot under tenant 'EVPN:{request.tenant}'.",
    }
