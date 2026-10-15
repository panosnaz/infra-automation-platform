"""Cisco ACI read / update / delete tools.

Until these existed every ACI tool was a create_*: an agent could add intent
but not look at what was there, change an attribute, or remove anything.

Updates are typed per object (one tool each for VRF, bridge domain and EPG)
because their attributes are flat, known and enumerable -- a generic
"set any field" tool would let a misspelt key through, and Nautobot stores it
without complaint while the generator ignores it.

Deletes are two tools with a typed `kind` rather than one tool per kind: every
delete has the same shape (find by name, refuse while referenced, remove), and
thirty near-identical tools would crowd the catalogue an agent has to choose
from. The refusal is the important part -- see intent_refs.py.

Imported by tools/aci.py, so importing the ACI tools registers these too.
"""
from __future__ import annotations

from mcp_server.clients.nautobot import NautobotClient
from mcp_server.clients.nautobot_lifecycle import DEPLOY_NOT_TRIGGERED as _DEPLOY_OBJECT
from mcp_server.schemas.aci_lifecycle import (
    DeleteFabricObjectRequest,
    DeleteTenantObjectRequest,
    DeleteTenantRequest,
    GetFabricIntentRequest,
    GetTenantIntentRequest,
    ListAciTenantsRequest,
    UnbindEpgContractRequest,
    UnbindEpgDomainRequest,
    UpdateBridgeDomainRequest,
    UpdateEpgRequest,
    UpdateVrfRequest,
)
from mcp_server.tools.registry import registry

_LIVE = (
    "2026-10-12, over the real MCP protocol against live Nautobot (48/48 checks, throwaway "
    "tenant lifecycle-test + fabric objects lc-test-*): every write read back independently "
    "via Nautobot REST, every update confirmed in the generator's NetAsCode output, every "
    "refusal confirmed to change nothing, and the real Location's fabric intent byte-identical "
    "afterwards. Not applied to the APIC: no generator or Terraform code changed, and removal "
    "from intent becomes a destroy through the existing pipeline."
)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@registry.register(
    name="list_aci_tenants",
    domain="cisco_aci",
    description=(
        "List every Tenant in Nautobot with a summary of its ACI intent: how many VRFs, "
        "bridge domains and EPGs it has, which JSON intent it carries (contracts, L3Outs, "
        "L4-L7, route control, ...) with entry counts, and its last pipeline validation "
        "status. Read-only. Use it to see what exists before creating or deleting anything."
    ),
    schema=ListAciTenantsRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def list_aci_tenants(request: ListAciTenantsRequest, *, nautobot: NautobotClient) -> dict:
    tenants = nautobot.list_aci_tenants()
    return {"count": len(tenants), "tenants": tenants}


@registry.register(
    name="get_tenant_intent",
    domain="cisco_aci",
    description=(
        "Return everything Nautobot holds as intent for one Tenant: VRFs with their "
        "attributes, bridge domains (grouped across their subnets, named exactly as the "
        "generator names them), EPGs by application profile with contracts/domains/paths, "
        "all JSON intent (contracts, filters, L3Outs, route maps, L4-L7, interface "
        "policies), and the last deployment status. Read-only. This is desired state -- "
        "what the APIC SHOULD contain -- not what the APIC currently contains."
    ),
    schema=GetTenantIntentRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def get_tenant_intent(request: GetTenantIntentRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.get_tenant_intent(request.tenant)


@registry.register(
    name="get_fabric_intent",
    domain="cisco_aci",
    description=(
        "Return the fabric-wide ACI intent on a Location: access policies (VLAN pools, "
        "domains, AEPs, policy groups, interface/switch profiles), fabric policies "
        "(NTP/DNS/SNMP, COOP, ISIS, ...), AAA (security domains, local users), and the "
        "fabric nodes registered at that Location. Read-only."
    ),
    schema=GetFabricIntentRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def get_fabric_intent(request: GetFabricIntentRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.get_fabric_intent(request.location)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@registry.register(
    name="update_vrf",
    not_settable=("NS-10", "NS-11", "NS-26"),
    domain="cisco_aci",
    description=(
        "Change attributes of an existing VRF: description, data-plane IP learning, "
        "policy-control enforcement direction/mode, the preferred group (vzAny) that makes "
        "EPG / ESG preferred_group_member take effect, and the VRF's BGP timers / OSPF timers / "
        "route tag policies. Only the fields you pass change. To "
        "return an attribute to its ACI default, pass the default value (stated per field) "
        "-- there is no unset."
    ),
    schema=UpdateVrfRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def update_vrf(request: UpdateVrfRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.update_vrf(
        tenant=request.tenant, name=request.name, description=request.description,
        ip_data_plane_learning=request.ip_data_plane_learning,
        policy_control_enforcement_direction=request.policy_control_enforcement_direction,
        policy_control_enforcement_mode=request.policy_control_enforcement_mode,
        preferred_group=request.preferred_group,
        bgp_timers_policy=request.bgp_timers_policy,
        ospf_timers_policy=request.ospf_timers_policy,
        route_tag_policy=request.route_tag_policy,
    )
    return {**result, "deploy": _DEPLOY_OBJECT.format(what="VRF")}


@registry.register(
    name="update_bridge_domain",
    not_settable=("NS-09", "NS-10", "NS-11"),
    domain="cisco_aci",
    description=(
        "Change attributes of an existing bridge domain: description, subnet scope "
        "(private/public/shared), the L3Outs it advertises through, MAC, ARP flooding, host "
        "route advertisement, unknown-unicast/multicast/multi-destination flooding, GARP "
        "move detection, PIM. Applied to every subnet of a multi-subnet BD. Only the fields "
        "you pass change; to return to an ACI default pass the default value -- there is "
        "no unset. Changing gateway IPs is not supported here."
    ),
    schema=UpdateBridgeDomainRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def update_bridge_domain(request: UpdateBridgeDomainRequest, *, nautobot: NautobotClient) -> dict:
    attrs = request.model_dump(exclude={"tenant", "name", "description", "subnet_scope"})
    result = nautobot.update_bridge_domain(
        tenant=request.tenant, name=request.name, description=request.description,
        subnet_scope=request.subnet_scope, **attrs,
    )
    note = _DEPLOY_OBJECT.format(what="Prefix (bridge domain)")
    if request.subnet_scope in ("public", "public,shared") and request.l3outs == []:
        note += " WARNING: a public subnet with no L3Out is never advertised."
    return {**result, "deploy": note}


@registry.register(
    name="update_epg",
    not_settable=("NS-10", "NS-11"),
    domain="cisco_aci",
    description=(
        "Change an existing EPG: move it to another existing bridge domain, change its "
        "description, or set preferred-group membership. Contracts and domains have their "
        "own bind_*/unbind_* tools."
    ),
    schema=UpdateEpgRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def update_epg(request: UpdateEpgRequest, *, nautobot: NautobotClient) -> dict:
    result = nautobot.update_epg(
        tenant=request.tenant, application_profile=request.application_profile, name=request.name,
        bridge_domain=request.bridge_domain, description=request.description,
        preferred_group_member=request.preferred_group_member,
    )
    return {**result, "deploy": _DEPLOY_OBJECT.format(what="VLAN (EPG)")}


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@registry.register(
    name="delete_tenant_object",
    not_settable=("NS-16",),
    domain="cisco_aci",
    description=(
        "Delete one object inside a Tenant: a VRF, bridge domain, EPG, contract, filter, "
        "L3Out, route map, match rule, VRF route leak, OSPF/ND/DPP/PIM/IGMP/custom-QoS "
        "policy, or an L4-L7 device / service graph / PBR policy / health group / IP SLA "
        "policy. REFUSES while anything still references the object, and names every "
        "reference, because a dangling reference fails the next pipeline. Remove those "
        "first. The APIC object is removed by the next pipeline run, after the manual "
        "apply approval."
    ),
    schema=DeleteTenantObjectRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def delete_tenant_object(request: DeleteTenantObjectRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_tenant_object(
        tenant=request.tenant, kind=request.kind, name=request.name,
        application_profile=request.application_profile, l3out=request.l3out,
    )


@registry.register(
    name="delete_fabric_object",
    not_settable=("NS-16",),
    domain="cisco_aci",
    description=(
        "Delete one fabric-wide access/AAA policy object from a Location: VLAN pool, "
        "physical / L3 / VMM domain, AEP, leaf interface policy group, pod policy group, "
        "leaf interface profile, interface selector, access port profile, leaf profile, "
        "security domain or local user. REFUSES while anything still references it -- "
        "including EPGs, L3Outs and L4-L7 devices in ANY tenant for domains -- and names "
        "each reference. Removes every entry of that name, so it also clears duplicates."
    ),
    schema=DeleteFabricObjectRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def delete_fabric_object(request: DeleteFabricObjectRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_fabric_object(kind=request.kind, name=request.name, location=request.location)


@registry.register(
    name="unbind_epg_contract",
    domain="cisco_aci",
    description="Remove a provided or consumed contract from an EPG. Inverse of bind_epg_contract.",
    schema=UnbindEpgContractRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def unbind_epg_contract(request: UnbindEpgContractRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.unbind_epg_contract(
        tenant=request.tenant, application_profile=request.application_profile,
        epg=request.epg, contract=request.contract, relation=request.relation,
    )


@registry.register(
    name="unbind_epg_domain",
    domain="cisco_aci",
    description="Remove a physical or VMM domain binding from an EPG. Inverse of bind_epg_domain.",
    schema=UnbindEpgDomainRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def unbind_epg_domain(request: UnbindEpgDomainRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.unbind_epg_domain(
        tenant=request.tenant, application_profile=request.application_profile,
        epg=request.epg, domain=request.domain, domain_type=request.domain_type,
    )


@registry.register(
    name="delete_tenant",
    domain="cisco_aci",
    description=(
        "Delete a whole Tenant from Nautobot together with its VRFs, bridge domains and "
        "EPGs. `confirm` must repeat the name. Never deletes the ACI system tenants "
        "(common, infra, mgmt), and refuses a tenant that also owns devices or IP "
        "addresses. The APIC tenant -- and everything in it -- is destroyed by the next "
        "pipeline run once the apply is approved; review that plan."
    ),
    schema=DeleteTenantRequest,
    evidence="live-verified",
    evidence_note=_LIVE,
)
def delete_tenant(request: DeleteTenantRequest, *, nautobot: NautobotClient) -> dict:
    return nautobot.delete_tenant(request.name)
