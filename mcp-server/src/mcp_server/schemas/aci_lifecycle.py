"""Request schemas for the ACI read / update / delete tools.

Value sets are Literals, so they appear in the JSON Schema an MCP client
receives from tools/list -- the agent sees the allowed values before calling,
instead of discovering them from a rejection.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mcp_server.intent_refs import FABRIC_KINDS, SYSTEM_TENANTS, TENANT_KINDS, bare_tenant_name

TenantKind = Literal[TENANT_KINDS]  # type: ignore[valid-type]
FabricKind = Literal[tuple(FABRIC_KINDS)]  # type: ignore[valid-type]

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

_LOCATION_FIELD = Field(
    default=None,
    description="Nautobot Location holding the fabric intent. Omit to auto-resolve (refused if ambiguous).",
)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

class ListAciTenantsRequest(BaseModel):
    """No arguments."""


class GetTenantIntentRequest(BaseModel):
    tenant: str = Field(description="Tenant name exactly as stored in Nautobot, e.g. 'ACI:sales' or 'sales'.")


class GetFabricIntentRequest(BaseModel):
    location: str | None = _LOCATION_FIELD


# ---------------------------------------------------------------------------
# Update. Every field except the identifiers is optional and means "leave
# unchanged" when omitted; at least one must be given.
# ---------------------------------------------------------------------------

_NO_CLEAR = (
    " There is no 'unset': removing a value only makes Terraform stop managing "
    "the attribute, it does not restore the ACI default. To go back to the "
    "default, set the default value explicitly."
)


def _require_a_change(model: BaseModel, identifiers: set[str]) -> None:
    changes = [k for k, v in model.model_dump().items() if k not in identifiers and v is not None]
    if not changes:
        raise ValueError("nothing to update: pass at least one field to change")


class UpdateVrfRequest(BaseModel):
    tenant: str = Field(description="Name of the Tenant that owns the VRF.")
    name: str = Field(description="Name of the existing VRF.")
    description: str | None = Field(default=None, description="New description.")
    ip_data_plane_learning: bool | None = Field(default=None, description="VRF data-plane IP learning. ACI default: true.")
    policy_control_enforcement_direction: Literal["ingress", "egress"] | None = Field(
        default=None, description="Where contracts are enforced. ACI default: ingress."
    )
    policy_control_enforcement_mode: Literal["enforced", "unenforced"] | None = Field(
        default=None,
        description="'unenforced' lets every EPG in the VRF talk without contracts. ACI default: enforced.",
    )
    preferred_group: bool | None = Field(
        default=None,
        description="Enable the VRF's preferred group (vzAny): EPGs and ESGs marked preferred_group_member then "
                    "talk to each other without contracts. Without it their membership has no effect. ACI default: false.",
    )
    bgp_timers_policy: str | None = Field(
        default=None, description="BGP timers policy of this tenant for the whole VRF. Empty string: back to the default.")
    ospf_timers_policy: str | None = Field(
        default=None, description="OSPF timers policy of this tenant for the whole VRF. Empty string: back to the default.")
    route_tag_policy: str | None = Field(
        default=None, description="Route tag policy of this tenant: the tag stamped on routes the VRF redistributes. "
                                  "Empty string: back to the default.")

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"tenant", "name"})
        return self


class UpdateBridgeDomainRequest(BaseModel):
    tenant: str = Field(description="Name of the Tenant that owns the bridge domain.")
    name: str = Field(description="Name of the existing bridge domain. Applied to every subnet (Prefix) it has.")
    description: str | None = Field(default=None, description="New free-text description.")
    subnet_scope: Literal["private", "public", "shared", "public,shared"] | None = Field(
        default=None,
        description="Subnet scope. 'public' is required for the subnet to be advertised out of an L3Out "
                    "(together with l3outs). ACI default: private.",
    )
    l3outs: list[str] | None = Field(
        default=None,
        description="Replace the L3Outs this BD may advertise through. Each must already exist in the tenant.",
    )
    mac: str | None = Field(default=None, description="BD MAC address. ACI default: 00:22:BD:F8:19:FF.")
    arp_flooding: bool | None = Field(default=None, description="Flood ARP. ACI default: false.")
    advertise_host_routes: bool | None = Field(default=None, description="Advertise /32 host routes. ACI default: false.")
    l2_unknown_unicast: Literal["proxy", "flood"] | None = Field(default=None, description="ACI default: proxy.")
    l3_unknown_multicast: Literal["flood", "opt-flood"] | None = Field(default=None, description="ACI default: flood.")
    multi_destination: Literal["bd-flood", "encap-flood", "drop"] | None = Field(
        default=None, description="ACI default: bd-flood."
    )
    ep_move_detect_mode: Literal["garp"] | None = Field(
        default=None, description="Enable GARP-based endpoint move detection."
    )
    pim: bool | None = Field(default=None, description="Enable PIM (L3 multicast) on the BD. ACI default: false.")

    @field_validator("mac")
    @classmethod
    def _mac(cls, v: str | None) -> str | None:
        if v is not None and not _MAC_RE.match(v):
            raise ValueError(f"'{v}' is not a MAC address of the form 00:22:BD:F8:19:FF")
        return v

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"tenant", "name"})
        return self


class UpdateEpgRequest(BaseModel):
    tenant: str = Field(description="Name of the Tenant that owns the EPG.")
    application_profile: str = Field(description="Application profile the EPG belongs to.")
    name: str = Field(description="Name of the existing EPG.")
    bridge_domain: str | None = Field(default=None, description="Move the EPG to this existing bridge domain.")
    description: str | None = Field(default=None, description="New description.")
    preferred_group_member: bool | None = Field(
        default=None, description="Member of the VRF's preferred group (contract-free inside the group)."
    )

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"tenant", "application_profile", "name"})
        return self


for _cls in (UpdateVrfRequest, UpdateBridgeDomainRequest, UpdateEpgRequest):
    _cls.__doc__ = (_cls.__doc__ or "") + _NO_CLEAR


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class DeleteTenantObjectRequest(BaseModel):
    tenant: str = Field(description="Name of the Tenant that owns the object.")
    kind: TenantKind = Field(description="What kind of object to delete.")
    name: str = Field(description="Name of the object to delete.")
    application_profile: str | None = Field(
        default=None, description="Required when kind is 'epg': the EPG's application profile."
    )
    l3out: str | None = Field(
        default=None, description="Required when kind is 'route_control_profile': the L3Out holding the route map."
    )

    @model_validator(mode="after")
    def _context_present(self):
        if self.kind == "epg" and not self.application_profile:
            raise ValueError("kind='epg' needs application_profile -- EPG names are only unique within one")
        if self.kind == "route_control_profile" and not self.l3out:
            raise ValueError("kind='route_control_profile' needs l3out -- route maps live inside an L3Out")
        return self


class DeleteFabricObjectRequest(BaseModel):
    kind: FabricKind = Field(description="What kind of fabric-wide object to delete.")
    name: str = Field(description="Name of the object to delete.")
    location: str | None = _LOCATION_FIELD


class UnbindEpgContractRequest(BaseModel):
    tenant: str = Field(description="Name of the Tenant.")
    application_profile: str = Field(description="Application profile the EPG belongs to.")
    epg: str = Field(description="EPG name.")
    contract: str = Field(description="Contract to remove from the EPG.")
    relation: Literal["provided", "consumed"] = Field(description="Which binding to remove.")


class UnbindEpgDomainRequest(BaseModel):
    tenant: str = Field(description="Name of the Tenant.")
    application_profile: str = Field(description="Application profile the EPG belongs to.")
    epg: str = Field(description="EPG name.")
    domain: str = Field(description="Domain to unbind.")
    domain_type: Literal["physical", "vmm"] = Field(description="Type of the domain binding to remove.")


class DeleteTenantRequest(BaseModel):
    name: str = Field(description="Tenant to delete, exactly as stored in Nautobot.")
    confirm: str = Field(
        description="Type the tenant name again. Deleting a tenant removes it from the APIC at the next "
                    "pipeline run, with everything in it."
    )

    @model_validator(mode="after")
    def _guarded(self):
        if bare_tenant_name(self.name).lower() in SYSTEM_TENANTS:
            raise ValueError(f"'{self.name}' is an ACI system tenant (common/infra/mgmt) and is never deleted")
        if self.confirm != self.name:
            raise ValueError("confirm must repeat the tenant name exactly")
        return self
