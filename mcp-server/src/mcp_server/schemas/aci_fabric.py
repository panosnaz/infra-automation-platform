"""Request schemas for the fabric-wide policy tools (2026-10-13).

Defaults in the descriptions are APIC's own, read from a freshly reset APIC
on 2026-10-13 -- not the values a previous lab left behind (that lab had
COOP 'strict' and ISIS metric 60; a fresh APIC has 'compatible' and 32). Value sets are Literals so the agent sees them in
tools/list.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mcp_server.schemas.aci import _validate_aci_name

_LOCATION = Field(default=None, description="Nautobot Location holding the fabric intent. Omit to auto-resolve.")
_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
FabricPolicy = Literal["ntp", "dns", "snmp", "coop", "isis", "fault_lifecycle", "syslog_message", "syslog_rate_limit",
                       "bgp_route_reflector", "pod_profile"]


def _ip_or_host(v: str) -> str:
    try:
        ipaddress.ip_address(v)
        return v
    except ValueError:
        if _HOST_RE.match(v):
            return v
    raise ValueError(f"'{v}' is neither an IP address nor a valid host name")


def _ip(v: str) -> str:
    ipaddress.ip_address(v)
    return v


def _require_a_change(model: BaseModel, identifiers: set[str]) -> None:
    if not [k for k, v in model.model_dump().items() if k not in identifiers and v is not None]:
        raise ValueError("nothing to update: pass at least one field to change")


# --- NTP --------------------------------------------------------------------------

class SetNtpPolicyRequest(BaseModel):
    admin_state: Literal["enabled", "disabled"] = Field(description="NTP on the fabric. APIC default: enabled.")
    location: str | None = _LOCATION


class CreateNtpServerRequest(BaseModel):
    address: str = Field(description="NTP server IP address or host name.")
    preferred: bool = Field(default=False, description="Prefer this server.")
    min_poll: int = Field(default=4, ge=4, le=16, description="Minimum poll interval, as a power of 2 seconds. APIC default: 4.")
    max_poll: int = Field(default=6, ge=4, le=16, description="Maximum poll interval, as a power of 2 seconds. APIC default: 6.")
    location: str | None = _LOCATION

    _address = field_validator("address")(classmethod(lambda cls, v: _ip_or_host(v)))

    @model_validator(mode="after")
    def _poll_order(self):
        if self.min_poll > self.max_poll:
            raise ValueError("min_poll cannot exceed max_poll")
        return self


class UpdateNtpServerRequest(BaseModel):
    address: str = Field(description="Existing NTP server.")
    preferred: bool | None = None
    min_poll: int | None = Field(default=None, ge=4, le=16)
    max_poll: int | None = Field(default=None, ge=4, le=16)
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"address", "location"})
        return self


class DeleteNtpServerRequest(BaseModel):
    address: str
    location: str | None = _LOCATION


# --- DNS --------------------------------------------------------------------------

class CreateDnsServerRequest(BaseModel):
    address: str = Field(description="DNS server IP address.")
    preferred: bool = Field(default=False, description="Prefer this DNS server.")
    location: str | None = _LOCATION

    _address = field_validator("address")(classmethod(lambda cls, v: _ip(v)))


class UpdateDnsServerRequest(BaseModel):
    address: str
    preferred: bool | None = None
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"address", "location"})
        return self


class DeleteDnsServerRequest(BaseModel):
    address: str
    location: str | None = _LOCATION


class CreateDnsDomainRequest(BaseModel):
    name: str = Field(description="DNS search domain, e.g. 'corp.example.com'.")
    is_default: bool = Field(default=False, description="The default search domain. Only one can be; setting this demotes any other.")
    location: str | None = _LOCATION

    @field_validator("name")
    @classmethod
    def _domain(cls, v: str) -> str:
        if not _HOST_RE.match(v):
            raise ValueError(f"'{v}' is not a valid DNS domain")
        return v


class UpdateDnsDomainRequest(BaseModel):
    name: str
    is_default: bool | None = None
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"name", "location"})
        return self


class DeleteDnsDomainRequest(BaseModel):
    name: str
    location: str | None = _LOCATION


# --- SNMP -------------------------------------------------------------------------

class SetSnmpPolicyRequest(BaseModel):
    admin_state: Literal["enabled", "disabled"] | None = Field(default=None, description="SNMP on the fabric. APIC default: disabled.")
    contact: str | None = Field(default=None, max_length=255, description="sysContact.")
    system_location: str | None = Field(default=None, max_length=255, description="sysLocation (the SNMP field, not a Nautobot Location).")
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"location"})
        return self


class CreateSnmpCommunityRequest(BaseModel):
    ref: str = Field(
        description="A REFERENCE name for the community, e.g. 'ro-monitoring' -- NOT the community string. "
                    "The string itself is a credential and is supplied at apply time in the sensitive Terraform "
                    "variable snmp_community_strings, keyed by this reference. It never goes into Nautobot or Git."
    )
    location: str | None = _LOCATION

    @field_validator("ref")
    @classmethod
    def _ref(cls, v: str) -> str:
        return _validate_aci_name(v)


class DeleteSnmpCommunityRequest(BaseModel):
    ref: str
    location: str | None = _LOCATION


# --- COOP / ISIS / fault lifecycle / syslog ---------------------------------------

class SetCoopPolicyRequest(BaseModel):
    type: Literal["compatible", "strict"] = Field(description="COOP group policy type. APIC default: compatible.")
    location: str | None = _LOCATION


class SetIsisPolicyRequest(BaseModel):
    mtu: int | None = Field(default=None, ge=128, le=4352, description="ISIS domain MTU. APIC default: 1492.")
    redistrib_metric: int | None = Field(default=None, ge=1, le=63, description="Metric for redistributed routes. APIC default: 32.")
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"location"})
        return self


class SetFaultLifecyclePolicyRequest(BaseModel):
    soak: int | None = Field(default=None, ge=0, le=3600, description="Seconds a new fault soaks before it is raised. APIC default: 120.")
    retain: int | None = Field(default=None, ge=0, le=31536000, description="Seconds a cleared fault is retained. APIC default: 3600.")
    clear: int | None = Field(default=None, ge=0, le=3600, description="Seconds a fault stays clearing. APIC default: 120.")
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"location"})
        return self


class SetSyslogMessagePolicyRequest(BaseModel):
    admin_state: str = Field(description="Syslog system message handling (systemSyslogMsgHdl). APIC default: 'monitor'.")
    location: str | None = _LOCATION


class SetSyslogRateLimitRequest(BaseModel):
    enabled: bool | None = Field(default=None, description="Rate-limit syslog messages. APIC default: true.")
    limit_per_sec: int | None = Field(default=None, ge=1, description="Messages per second. APIC default: 500.")
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"location"})
        return self


class ResetFabricPolicyRequest(BaseModel):
    policy: FabricPolicy = Field(description="Which fabric-wide policy to hand back to APIC's defaults.")
    location: str | None = _LOCATION


# --- BGP route reflector policy / pod assignment (2026-10-14) ----------------------

class SetBgpRouteReflectorPolicyRequest(BaseModel):
    asn: int = Field(ge=1, le=4294967295, description="The fabric's BGP autonomous system number (2- or 4-byte). "
                                                         "A fresh APIC has none.")
    location: str | None = _LOCATION


class CreateBgpRouteReflectorNodeRequest(BaseModel):
    node: str = Field(description="Spine switch, by Nautobot device name or ACI node ID. Must be a spine in the "
                                  "Nautobot fabric inventory.")
    pod_id: int | None = Field(default=None, ge=1, description="Pod of the spine. Omitted: the device's aci_pod_id.")
    location: str | None = _LOCATION


class DeleteBgpRouteReflectorNodeRequest(BaseModel):
    node_id: int = Field(ge=1, le=4000, description="Node ID of the route reflector to remove.")
    location: str | None = _LOCATION


class AssignPodPolicyGroupRequest(BaseModel):
    policy_group: str = Field(description="Existing Pod Policy Group to assign to the default pod selector (all pods).")
    location: str | None = _LOCATION
