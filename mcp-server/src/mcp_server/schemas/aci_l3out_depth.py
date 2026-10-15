"""Request schemas for L3Out depth (2026-10-16).

Numeric bounds are the APIC's own, measured on APIC 6.2(1g) by posting each
boundary value (2026-10-16), not taken from documentation. BGP keepalive /
hold are only valid relative to each other; that rule is checked in the
client, against APIC's defaults when one of them is omitted.
"""
from __future__ import annotations

import ipaddress
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mcp_server.schemas.aci import _validate_aci_name
from mcp_server.schemas.aci_fabric import _require_a_change

EnabledDisabled = Literal["enabled", "disabled"]
_TENANT = Field(description="Name of the Tenant.")
_DESC = Field(default=None, description="Free-text description.")
_CLEAR = " Pass an empty string to remove the reference (APIC's default applies again)."


class _Named(BaseModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def _aci_name(cls, v):
        return _validate_aci_name(v)


# --- tenant policies ------------------------------------------------------------------

class CreateBfdInterfacePolicyRequest(_Named):
    tenant: str = _TENANT
    name: str = Field(description="Policy name.")
    admin_state: EnabledDisabled | None = Field(default=None, description="BFD on or off. APIC default: enabled.")
    detect_multiplier: int | None = Field(default=None, ge=1, le=50, description="Missed packets before the session is down. APIC default: 3.")
    min_rx_interval: int | None = Field(default=None, ge=50, le=999, description="Minimum receive interval, ms. APIC default: 50.")
    min_tx_interval: int | None = Field(default=None, ge=50, le=999, description="Minimum transmit interval, ms. APIC default: 50.")
    echo_admin_state: EnabledDisabled | None = Field(default=None, description="BFD echo mode. APIC default: enabled.")
    echo_rx_interval: int | None = Field(default=None, ge=0, le=999, description="Echo receive interval, ms. APIC default: 50.")
    description: str | None = _DESC


class CreateBgpTimersPolicyRequest(_Named):
    tenant: str = _TENANT
    name: str = Field(description="Policy name.")
    keepalive_interval: int | None = Field(default=None, ge=0, le=3600, description="Seconds. APIC default: 60. Must be below the hold interval.")
    hold_interval: int | None = Field(default=None, ge=0, le=3600, description="Seconds; 0 disables (then keepalive must be 0). APIC default: 180.")
    stale_interval: int | None = Field(default=None, ge=1, le=3600, description="Graceful-restart stale-path time, seconds. APIC default: 300.")
    graceful_restart_helper: bool | None = Field(default=None, description="Act as graceful-restart helper. APIC default: true.")
    max_as_limit: int | None = Field(default=None, ge=0, le=2000, description="Maximum AS-path length accepted; 0 = no limit. APIC default: 0.")
    description: str | None = _DESC


class CreateBgpBestPathPolicyRequest(_Named):
    tenant: str = _TENANT
    name: str = Field(description="Policy name.")
    as_path_multipath_relax: bool | None = Field(
        default=None, description="Load-share across eBGP paths from different neighbour ASes with equal AS-path length.")
    description: str | None = _DESC


class CreateBgpRouteSummarizationPolicyRequest(_Named):
    tenant: str = _TENANT
    name: str = Field(description="Policy name.")
    as_set: bool | None = Field(default=None, description="Keep the AS-set of the summarised routes (loop prevention).")
    description: str | None = _DESC


class CreateOspfTimersPolicyRequest(_Named):
    tenant: str = _TENANT
    name: str = Field(description="Policy name.")
    reference_bandwidth: int | None = Field(default=None, ge=1, le=4000000, description="Mbps, for cost calculation. APIC default: 40000.")
    distance: int | None = Field(default=None, ge=1, le=255, description="Administrative distance. APIC default: 110.")
    max_ecmp: int | None = Field(default=None, ge=1, le=64, description="Equal-cost paths. APIC default: 8.")
    spf_initial_delay: int | None = Field(default=None, ge=1, le=600000, description="ms. APIC default: 200.")
    spf_hold_interval: int | None = Field(default=None, ge=1, le=600000, description="ms. APIC default: 1000.")
    spf_max_interval: int | None = Field(default=None, ge=1, le=600000, description="ms. APIC default: 5000.")
    description: str | None = _DESC


class CreateRouteTagPolicyRequest(_Named):
    tenant: str = _TENANT
    name: str = Field(description="Policy name.")
    tag: int = Field(ge=0, le=4294967295, description="Tag stamped on routes the VRF redistributes (loop prevention in transit designs).")
    description: str | None = _DESC


# --- static routes / loopbacks -----------------------------------------------------------

class _L3OutNode(BaseModel):
    tenant: str = _TENANT
    l3out: str = Field(description="Existing L3Out.")
    node_profile: str = Field(description="Existing node profile of the L3Out.")
    node_id: int = Field(ge=1, le=4000, description="Border leaf already in the node profile.")


class NextHop(BaseModel):
    ip: str = Field(description="Next-hop IP address.")
    preference: int | None = Field(default=None, ge=0, le=255, description="Lower is preferred. APIC default: 0 (unspecified).")

    @field_validator("ip")
    @classmethod
    def _ip(cls, v: str) -> str:
        return str(ipaddress.ip_address(v))


class CreateL3OutStaticRouteRequest(_L3OutNode):
    prefix: str = Field(description="Destination prefix, e.g. '10.20.0.0/16' (host bits zero).")
    next_hops: list[NextHop] = Field(default_factory=list, description="Next hops. None at all makes a null route (discard).")
    preference: int | None = Field(default=None, ge=1, le=255, description="Route preference (distance). APIC default: 1.")
    bfd: bool | None = Field(default=None, description="Track the next hops with BFD.")
    description: str | None = _DESC

    @field_validator("prefix")
    @classmethod
    def _prefix(cls, v: str) -> str:
        try:
            return str(ipaddress.ip_network(v, strict=True))
        except ValueError as exc:
            raise ValueError(f"'{v}' is not a valid prefix (host bits must be zero): {exc}") from exc


class DeleteL3OutStaticRouteRequest(_L3OutNode):
    prefix: str = Field(description="Prefix of the static route to remove, as stored.")


class L3OutLoopbackRequest(_L3OutNode):
    ip: str = Field(description="Loopback address, e.g. '10.255.0.101' -- typically the BGP source for loopback peering.")

    @field_validator("ip")
    @classmethod
    def _ip(cls, v: str) -> str:
        return str(ipaddress.ip_address(v))


# --- vPC SVI ---------------------------------------------------------------------------------

class _VpcSvi(BaseModel):
    tenant: str = _TENANT
    l3out: str = Field(description="Existing L3Out.")
    node_profile: str = Field(description="Existing node profile holding both leaves.")
    interface_profile: str = Field(description="Existing interface profile in that node profile.")
    node_id: int = Field(ge=1, le=4000, description="First leaf of the vPC pair (side A).")
    node_id2: int = Field(ge=1, le=4000, description="Second leaf of the vPC pair (side B).")
    policy_group: str = Field(description="vPC interface policy group the SVI runs over.")

    @model_validator(mode="after")
    def _two_leaves(self):
        if self.node_id == self.node_id2:
            raise ValueError("a vPC needs two different leaves")
        return self


class CreateL3OutVpcSviRequest(_VpcSvi):
    vlan: int = Field(ge=1, le=4094, description="SVI encapsulation VLAN; must be in the L3 domain's VLAN pool.")
    side_a_ip: str = Field(description="Side A (node_id) address with prefix, e.g. '10.30.1.2/24'.")
    side_b_ip: str = Field(description="Side B (node_id2) address, same subnet as side A.")
    pod_id: int = Field(default=1, ge=1)
    mtu: str | None = Field(default=None, description="'inherit' or 576-9216. APIC default: inherit.")
    location: str | None = Field(default=None, description="Nautobot Location holding the vPC domain and policy group. Omit to auto-resolve.")

    @model_validator(mode="after")
    def _same_subnet(self):
        try:
            a, b = ipaddress.ip_interface(self.side_a_ip), ipaddress.ip_interface(self.side_b_ip)
        except ValueError as exc:
            raise ValueError(f"side addresses must be IP/prefix: {exc}") from exc
        if a.network != b.network:
            raise ValueError(f"side_a_ip {a} and side_b_ip {b} must be in the same subnet")
        if a.ip == b.ip:
            raise ValueError("side_a_ip and side_b_ip must differ")
        return self


class DeleteL3OutVpcSviRequest(_VpcSvi):
    pass


# --- references ------------------------------------------------------------------------------

class SetL3OutBgpPoliciesRequest(BaseModel):
    tenant: str = _TENANT
    l3out: str = Field(description="Existing BGP L3Out.")
    bgp_timers_policy: str | None = Field(default=None, description="BGP timers policy of this tenant." + _CLEAR)
    bgp_best_path_policy: str | None = Field(default=None, description="BGP best path policy of this tenant." + _CLEAR)

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"tenant", "l3out"})
        return self


class SetExternalSubnetRouteSummarizationRequest(BaseModel):
    tenant: str = _TENANT
    l3out: str = Field(description="Existing L3Out.")
    external_epg: str = Field(description="External EPG holding the subnet.")
    ip: str = Field(description="The external EPG subnet, as stored, e.g. '10.20.0.0/16'.")
    policy: str = Field(description="BGP route summarization policy of this tenant." + _CLEAR)
