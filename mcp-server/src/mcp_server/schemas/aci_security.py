"""Request schemas for Endpoint Security Groups and vzAny (2026-10-15).

An ESG (fvESg) classifies endpoints by selectors -- EPGs, IP subnets, tags --
rather than by the EPG they attach through, and carries contracts like an
EPG. vzAny is the VRF-wide "every EPG and ESG in this VRF" object; contracts
on it apply to all of them, and its preferred-group switch is what makes
EPG / ESG preferred_group_member take effect.
"""
from __future__ import annotations

import ipaddress
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mcp_server.schemas.aci import _validate_aci_name
from mcp_server.schemas.aci_fabric import _require_a_change

ContractRelation = Literal["provided", "consumed"]
TagOperator = Literal["equals", "contains", "regex"]
SelectorType = Literal["epg", "ip_subnet", "tag"]

_TENANT = Field(description="Name of the Tenant.")
_ESG = Field(description="Name of the Endpoint Security Group (unique within the tenant).")


class _Named(BaseModel):
    @field_validator("name", "esg", "application_profile", "epg", "vrf", "contract", check_fields=False)
    @classmethod
    def _aci_name(cls, v):
        return v if v is None else _validate_aci_name(v)


class CreateEsgRequest(_Named):
    tenant: str = _TENANT
    application_profile: str = Field(description="Application profile the ESG lives in. Created if no EPG uses it yet.")
    name: str = Field(description="ESG name. Must be unique within the tenant.")
    vrf: str = Field(description="VRF the ESG belongs to. Every endpoint it selects must be in this VRF. "
                                 "update_esg does not change it -- delete and recreate the ESG instead.")
    description: str | None = Field(default=None, description="Free-text description.")
    preferred_group_member: bool | None = Field(
        default=None, description="Member of the VRF's preferred group. Has effect only when the VRF's preferred "
                                  "group is enabled (update_vrf preferred_group=true). APIC default: false.")
    intra_esg_isolation: bool | None = Field(
        default=None, description="Block traffic between endpoints inside this ESG. APIC default: false.")
    shutdown: bool | None = Field(
        default=None, description="Withdraw the ESG from every switch without deleting it. APIC default: false.")


class UpdateEsgRequest(_Named):
    tenant: str = _TENANT
    name: str = Field(description="Name of the existing ESG.")
    description: str | None = Field(default=None, description="New description.")
    preferred_group_member: bool | None = Field(default=None, description="Preferred group membership. APIC default: false.")
    intra_esg_isolation: bool | None = Field(default=None, description="Block traffic inside the ESG. APIC default: false.")
    shutdown: bool | None = Field(default=None, description="Withdraw the ESG from every switch. APIC default: false.")

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"tenant", "name"})
        return self


class CreateEsgEpgSelectorRequest(_Named):
    tenant: str = _TENANT
    esg: str = _ESG
    application_profile: str = Field(description="Application profile of the EPG to select.")
    epg: str = Field(description="EPG to select: all its endpoints become members of the ESG. Its bridge domain "
                                 "must be in the ESG's VRF, and an EPG can be selected by only one ESG.")
    description: str | None = Field(default=None, description="Free-text description.")


class CreateEsgIpSubnetSelectorRequest(_Named):
    tenant: str = _TENANT
    esg: str = _ESG
    subnet: str = Field(description="IPv4/IPv6 host or subnet, e.g. '10.1.1.0/24' or '10.1.1.10'. Endpoints with an "
                                    "IP in it join the ESG. A subnet can be in only one ESG per VRF.")
    description: str | None = Field(default=None, description="Free-text description.")

    @field_validator("subnet")
    @classmethod
    def _subnet(cls, v: str) -> str:
        try:
            net = ipaddress.ip_network(v, strict=True)
        except ValueError as exc:
            raise ValueError(f"'{v}' is not a valid IP host or subnet (host bits must be zero): {exc}") from exc
        return str(net) if "/" in v else str(net.network_address)


class CreateEsgTagSelectorRequest(_Named):
    tenant: str = _TENANT
    esg: str = _ESG
    key: str = Field(min_length=1, max_length=64, description="Endpoint tag key to match, e.g. 'app'. A key=value "
                                                               "pair can be in only one ESG per VRF.")
    value: str = Field(min_length=1, max_length=128, description="Tag value to match, e.g. 'web'.")
    operator: TagOperator = Field(default="equals", description="How the value is matched. APIC default: equals.")
    description: str | None = Field(default=None, description="Free-text description.")


class DeleteEsgSelectorRequest(_Named):
    tenant: str = _TENANT
    esg: str = _ESG
    selector_type: SelectorType = Field(description="Which kind of selector to remove.")
    application_profile: str | None = Field(default=None, description="selector_type 'epg': the EPG's application profile.")
    epg: str | None = Field(default=None, description="selector_type 'epg': the selected EPG.")
    subnet: str | None = Field(default=None, description="selector_type 'ip_subnet': the subnet, as stored.")
    key: str | None = Field(default=None, description="selector_type 'tag': the tag key.")
    value: str | None = Field(default=None, description="selector_type 'tag': the tag value.")

    @model_validator(mode="after")
    def _identifies_one_selector(self):
        needed = {"epg": ("application_profile", "epg"), "ip_subnet": ("subnet",), "tag": ("key", "value")}[self.selector_type]
        missing = [f for f in needed if getattr(self, f) is None]
        if missing:
            raise ValueError(f"selector_type '{self.selector_type}' needs {', '.join(missing)}")
        return self


class EsgContractRequest(_Named):
    tenant: str = _TENANT
    esg: str = _ESG
    contract: str = Field(description="Contract in the same tenant.")
    relation: ContractRelation = Field(description="'provided' or 'consumed'.")


class VzAnyContractRequest(_Named):
    tenant: str = _TENANT
    vrf: str = Field(description="VRF whose vzAny gets the contract. A contract on vzAny applies to EVERY EPG and "
                                 "ESG in the VRF.")
    contract: str = Field(description="Contract in the same tenant.")
    relation: ContractRelation = Field(description="'provided' or 'consumed'.")
