"""Request schemas for port-channel / vPC and node management tools.

Value sets are Literals so the allowed values reach the agent in tools/list.
ACI rules that are cheap to check without Nautobot (a vPC needs two different
leaves, a gateway must sit inside its own subnet) are checked here; rules that
need current intent (does the LACP policy exist, is the leaf already in
another vPC pair) are checked by the client.
"""
from __future__ import annotations

import ipaddress
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mcp_server.schemas.aci import _validate_aci_name

LacpMode = Literal["active", "passive", "off", "mac-pin", "mac-pin-nicload", "explicit-failover"]
LacpControl = Literal["susp-individual", "graceful-conv", "fast-sel-hot-stdby", "load-defer", "symmetric-hash"]
MgmtType = Literal["out_of_band", "in_band"]

_LOCATION = Field(default=None, description="Nautobot Location holding the fabric intent. Omit to auto-resolve.")
_NO_CHANGE = "nothing to update: pass at least one field to change"


def _require_a_change(model: BaseModel, identifiers: set[str]) -> None:
    if not [k for k, v in model.model_dump().items() if k not in identifiers and v is not None]:
        raise ValueError(_NO_CHANGE)


class _Named(BaseModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def _aci_name(cls, v: str) -> str:
        return _validate_aci_name(v)


# ---------------------------------------------------------------------------
# LACP
# ---------------------------------------------------------------------------

class CreateLacpPolicyRequest(_Named):
    name: str = Field(description="LACP policy name, e.g. 'LACP_Active'.")
    mode: LacpMode = Field(default="active", description="'active'/'passive' run LACP; 'off' is a static channel; mac-pin* are for hypervisor uplinks without LACP.")
    min_links: int | None = Field(default=None, ge=1, le=16, description="Minimum active links before the channel goes down. ACI default: 1.")
    max_links: int | None = Field(default=None, ge=1, le=16, description="Maximum active links. ACI default: 16.")
    controls: list[LacpControl] | None = Field(default=None, description="LACP control flags. ACI default: fast-sel-hot-stdby, graceful-conv, susp-individual.")
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _links(self):
        if self.min_links and self.max_links and self.min_links > self.max_links:
            raise ValueError("min_links cannot exceed max_links")
        return self


class UpdateLacpPolicyRequest(BaseModel):
    name: str = Field(description="Existing LACP policy.")
    mode: LacpMode | None = None
    min_links: int | None = Field(default=None, ge=1, le=16)
    max_links: int | None = Field(default=None, ge=1, le=16)
    controls: list[LacpControl] | None = None
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"name", "location"})
        return self


# ---------------------------------------------------------------------------
# vPC domain
# ---------------------------------------------------------------------------

class CreateVpcDomainRequest(_Named):
    name: str = Field(description="vPC explicit protection group name, e.g. 'Leaf101_102_vPC'.")
    domain_id: int = Field(ge=1, le=1000, description="Logical vPC domain ID (1-1000), unique in the fabric.")
    node1: int = Field(ge=1, le=4000, description="First leaf node ID.")
    node2: int = Field(ge=1, le=4000, description="Second leaf node ID.")
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _two_leaves(self):
        if self.node1 == self.node2:
            raise ValueError("a vPC domain pairs two DIFFERENT leaves")
        return self


class UpdateVpcDomainRequest(BaseModel):
    name: str = Field(description="Existing vPC domain.")
    domain_id: int | None = Field(default=None, ge=1, le=1000)
    node1: int | None = Field(default=None, ge=1, le=4000)
    node2: int | None = Field(default=None, ge=1, le=4000)
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"name", "location"})
        if self.node1 is not None and self.node1 == self.node2:
            raise ValueError("a vPC domain pairs two DIFFERENT leaves")
        return self


# ---------------------------------------------------------------------------
# PC / vPC interface policy group
# ---------------------------------------------------------------------------

class CreatePcVpcPolicyGroupRequest(_Named):
    name: str = Field(description="Policy group name. Must not clash with an access-port policy group.")
    bundle_type: Literal["port_channel", "vpc"] = Field(description="'port_channel' (one leaf) or 'vpc' (two leaves).")
    aep: str | None = Field(default=None, description="Existing AEP -- what lets the bundle carry EPG VLANs.")
    lacp_policy: str | None = Field(default=None, description="Existing LACP policy. Omitted = APIC default, mode 'off' (static).")
    description: str = ""
    location: str | None = _LOCATION


class UpdatePcVpcPolicyGroupRequest(BaseModel):
    name: str = Field(description="Existing PC/vPC policy group. Its bundle type cannot change -- bindings depend on it.")
    aep: str | None = None
    lacp_policy: str | None = None
    description: str | None = None
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"name", "location"})
        return self


# ---------------------------------------------------------------------------
# Management
# ---------------------------------------------------------------------------

class CreateInbandMgmtEpgRequest(_Named):
    name: str = Field(description="In-band management EPG name (in tenant mgmt).")
    encap_vlan: int = Field(ge=1, le=4094, description="VLAN the in-band management traffic uses.")
    bridge_domain: str = Field(default="inb", description="mgmt-tenant bridge domain. ACI ships 'inb'.")
    location: str | None = _LOCATION


class UpdateInbandMgmtEpgRequest(BaseModel):
    name: str
    encap_vlan: int | None = Field(default=None, ge=1, le=4094)
    bridge_domain: str | None = None
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _something_changes(self):
        _require_a_change(self, {"name", "location"})
        return self


def _check_address(address: str | None, gateway: str | None) -> None:
    if address is not None:
        if "/" not in address:
            raise ValueError(f"address '{address}' needs a prefix length, e.g. 10.0.0.11/24")
        iface = ipaddress.ip_interface(address)
        if iface.ip == iface.network.network_address and iface.network.prefixlen < 31:
            raise ValueError(f"'{address}' is the subnet's network address, not a host")
        if gateway is not None:
            gw = ipaddress.ip_address(gateway)
            if gw not in iface.network:
                raise ValueError(f"gateway {gateway} is not inside {iface.network}")
            if gw == iface.ip:
                raise ValueError("the gateway cannot be the node's own address")
    elif gateway is not None:
        ipaddress.ip_address(gateway)


class CreateNodeMgmtAddressRequest(BaseModel):
    node: str = Field(description="Fabric switch, by Nautobot device name or ACI node ID.")
    type: MgmtType = Field(description="'out_of_band' (mgmt0, the built-in OOB EPG) or 'in_band'.")
    address: str = Field(description="Address with prefix length, e.g. '10.48.0.101/24'.")
    gateway: str = Field(description="Default gateway inside the same subnet, e.g. '10.48.0.1'.")
    epg: str | None = Field(default=None, description="In-band only: the in-band management EPG.")
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _valid(self):
        _check_address(self.address, self.gateway)
        if self.type == "in_band" and not self.epg:
            raise ValueError("an in_band address needs epg (create it with create_inband_mgmt_epg)")
        if self.type == "out_of_band" and self.epg not in (None, "default"):
            raise ValueError("out_of_band addresses always use the built-in OOB EPG 'default'")
        return self


class UpdateNodeMgmtAddressRequest(BaseModel):
    node: str = Field(description="Fabric switch, by Nautobot device name or ACI node ID.")
    type: MgmtType
    address: str | None = Field(default=None, description="New address with prefix length.")
    gateway: str | None = None
    epg: str | None = Field(default=None, description="In-band only.")
    location: str | None = _LOCATION

    @model_validator(mode="after")
    def _valid(self):
        _require_a_change(self, {"node", "type", "location"})
        _check_address(self.address, self.gateway)
        if self.type == "out_of_band" and self.epg not in (None, "default"):
            raise ValueError("out_of_band addresses always use the built-in OOB EPG 'default'")
        return self


class DeleteNodeMgmtAddressRequest(BaseModel):
    node: str = Field(description="Fabric switch, by Nautobot device name or ACI node ID.")
    type: MgmtType


# ---------------------------------------------------------------------------
# Unbinding a static path
# ---------------------------------------------------------------------------

class UnbindEpgStaticPathRequest(BaseModel):
    tenant: str
    application_profile: str
    epg: str
    node_id: int = Field(ge=1)
    path_type: Literal["port", "port_channel", "vpc"] = "port"
    node_id2: int | None = Field(default=None, ge=1)
    module: int | None = Field(default=None, ge=1)
    port: int | None = Field(default=None, ge=1)
    policy_group: str | None = None
    pod_id: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _shape(self):
        if self.path_type == "port" and (self.module is None or self.port is None):
            raise ValueError("a 'port' path is identified by module and port")
        if self.path_type != "port" and not self.policy_group:
            raise ValueError(f"a '{self.path_type}' path is identified by its policy_group")
        if self.path_type == "vpc" and self.node_id2 is None:
            raise ValueError("a 'vpc' path needs node_id2")
        return self

    def as_path(self) -> dict:
        path = {"path_type": self.path_type, "pod_id": self.pod_id, "node_id": self.node_id}
        if self.path_type == "port":
            path.update(module=self.module, port=self.port)
        else:
            path["policy_group"] = self.policy_group
            if self.path_type == "vpc":
                path["node_id2"] = self.node_id2
        return path
