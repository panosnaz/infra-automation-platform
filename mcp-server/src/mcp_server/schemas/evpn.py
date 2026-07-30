"""EVPN-specific per-tool request schemas -- thin argument validation only,
never a cross-domain intent envelope (ADR-018). Mirrors schemas/aci.py's
pattern exactly."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Same naming convention the vxlan_evpn OPA policy enforces
# (docker/platform-api/policy/vxlan_evpn/tenant_naming.rego) -- validating it
# here too gives a fast, clear MCP-side error instead of a slower round trip
# that only fails once the pipeline's policy_check job runs.
_TENANT_NAME_RE = re.compile(r"^[a-z0-9-]+$")

# Nautobot VRF/VLAN object names -- looser than the Tenant policy above.
_EVPN_NAME_RE = re.compile(r"^[a-zA-Z0-9_.:-]+$")

# nxos_nvo's confirmed schema range for a VNI key (ADR-021 §1) -- not an
# invented limit, matches the vxlan_evpn OPA policy's own range check.
_MIN_VNI = 1
_MAX_VNI = 16777214


def _validate_evpn_name(v: str) -> str:
    if not _EVPN_NAME_RE.match(v):
        raise ValueError(
            f"'{v}' is not a valid EVPN object name (allowed: letters, digits, '_', '.', ':', '-')"
        )
    return v


class CreateEvpnTenantRequest(BaseModel):
    """Reuses NautobotClient.create_tenant() directly (that method is fully
    generic, no ACI-specific behavior baked in) -- this schema only adds the
    'EVPN:' prefix convention (ADR-021 §2) at validation time."""

    name: str = Field(description="Tenant name without the 'EVPN:' prefix, e.g. 'finance'. Must match ^[a-z0-9-]+$ (lowercase, digits, hyphens only) -- the same rule the vxlan_evpn OPA policy enforces.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _TENANT_NAME_RE.match(v):
            raise ValueError(
                f"tenant name '{v}' does not match required pattern ^[a-z0-9-]+$ "
                "(this mirrors the vxlan_evpn OPA policy -- fixing it here "
                "avoids a guaranteed pipeline denial later)"
            )
        return v


class CreateEvpnVrfRequest(BaseModel):
    """ADR-021 §2 coverage: a Nautobot ipam.vrf object with its L3 VNI set
    via the `evpn_l3_vni` Custom Field."""

    tenant: str = Field(description="Name of the existing EVPN tenant this VRF belongs to (without the 'EVPN:' prefix).")
    name: str = Field(description="VRF name.")
    l3_vni: int = Field(ge=_MIN_VNI, le=_MAX_VNI, description=f"L3 VNI, must be in the range {_MIN_VNI}-{_MAX_VNI} (nxos_nvo's confirmed schema range).")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_evpn_name(v)


class CreateEvpnBridgeDomainRequest(BaseModel):
    """ADR-021 §2 coverage: a Nautobot VLAN object (the EVPN Bridge Domain
    directly, not a Prefix-description encoding like ACI's) with its L2 VNI
    and VRF association set via Custom Fields."""

    tenant: str = Field(description="Name of the existing EVPN tenant this Bridge Domain belongs to (without the 'EVPN:' prefix).")
    vrf: str = Field(description="Name of the existing VRF this Bridge Domain is associated with.")
    name: str = Field(description="Bridge Domain (VLAN) name.")
    vlan_id: int = Field(ge=1, le=4094, description="802.1Q VLAN ID (1-4094).")
    l2_vni: int = Field(ge=_MIN_VNI, le=_MAX_VNI, description=f"L2 VNI, must be in the range {_MIN_VNI}-{_MAX_VNI} (nxos_nvo's confirmed schema range).")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_evpn_name(v)
