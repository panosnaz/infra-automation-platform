"""Unit tests for EVPN tool input validation -- no live Nautobot needed.

Mirrors mcp-server/tests/unit/test_schemas_aci.py's pattern.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.schemas.evpn import (
    CreateEvpnBridgeDomainRequest,
    CreateEvpnTenantRequest,
    CreateEvpnVrfRequest,
)


def test_valid_tenant_name():
    req = CreateEvpnTenantRequest(name="finance", description="d")
    assert req.name == "finance"


def test_valid_tenant_name_with_hyphen_and_digits():
    CreateEvpnTenantRequest(name="finance-2")


@pytest.mark.parametrize(
    "bad_name",
    ["Finance", "finance_dept", "finance dept", "Finance_2", "UPPER"],
)
def test_invalid_tenant_name_rejected(bad_name):
    """Mirrors the live vxlan_evpn OPA policy's naming rule
    (docker/platform-api/policy/vxlan_evpn/tenant_naming.rego) -- catching
    this at the MCP layer avoids a guaranteed pipeline denial later."""
    with pytest.raises(ValidationError):
        CreateEvpnTenantRequest(name=bad_name)


def test_tenant_description_defaults_to_empty_string():
    req = CreateEvpnTenantRequest(name="finance")
    assert req.description == ""


def test_valid_vrf_request():
    req = CreateEvpnVrfRequest(tenant="finance", name="finance-vrf", l3_vni=10010)
    assert req.tenant == "finance"
    assert req.l3_vni == 10010
    assert req.description == ""


@pytest.mark.parametrize("bad_vni", [0, -1, 16777215, 100_000_000])
def test_vrf_l3_vni_out_of_range_rejected(bad_vni):
    """nxos_nvo's confirmed schema range is 1-16777214 -- matches the
    vxlan_evpn OPA policy's own range check."""
    with pytest.raises(ValidationError):
        CreateEvpnVrfRequest(tenant="finance", name="finance-vrf", l3_vni=bad_vni)


@pytest.mark.parametrize("bad_name", ["bad name", "bad/name", "bad#name"])
def test_invalid_vrf_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateEvpnVrfRequest(tenant="finance", name=bad_name, l3_vni=10010)


def test_valid_bridge_domain_request():
    req = CreateEvpnBridgeDomainRequest(
        tenant="finance",
        vrf="finance-vrf",
        name="finance-bd",
        vlan_id=100,
        l2_vni=10010,
    )
    assert req.vlan_id == 100
    assert req.l2_vni == 10010
    assert req.description == ""


@pytest.mark.parametrize("bad_vlan_id", [0, -1, 4095])
def test_bridge_domain_vlan_id_out_of_range_rejected(bad_vlan_id):
    """802.1Q VLAN ID must be 1-4094."""
    with pytest.raises(ValidationError):
        CreateEvpnBridgeDomainRequest(
            tenant="finance", vrf="finance-vrf", name="finance-bd", vlan_id=bad_vlan_id, l2_vni=10010
        )


@pytest.mark.parametrize("bad_vni", [0, -1, 16777215])
def test_bridge_domain_l2_vni_out_of_range_rejected(bad_vni):
    with pytest.raises(ValidationError):
        CreateEvpnBridgeDomainRequest(
            tenant="finance", vrf="finance-vrf", name="finance-bd", vlan_id=100, l2_vni=bad_vni
        )
