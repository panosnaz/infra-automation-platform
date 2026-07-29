"""Unit tests for ACI tool input validation -- no live Nautobot needed."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.schemas.aci import (
    CreateBridgeDomainRequest,
    CreateContractRequest,
    CreateEpgRequest,
    CreateL3OutRequest,
    CreateTenantRequest,
    CreateVrfRequest,
)


def test_valid_tenant_name():
    req = CreateTenantRequest(name="finance", description="d")
    assert req.name == "finance"


def test_valid_tenant_name_with_hyphen_and_digits():
    CreateTenantRequest(name="finance-2")


@pytest.mark.parametrize(
    "bad_name",
    ["Finance", "finance_dept", "finance dept", "Finance_2", "UPPER"],
)
def test_invalid_tenant_name_rejected(bad_name):
    """Mirrors the live OPA policy_check job's naming rule
    (docker/platform-api/policy/cisco_aci/tenant_naming.rego) -- catching
    this at the MCP layer avoids a guaranteed pipeline denial later."""
    with pytest.raises(ValidationError):
        CreateTenantRequest(name=bad_name)


def test_description_defaults_to_empty_string():
    req = CreateTenantRequest(name="finance")
    assert req.description == ""


def test_valid_vrf_request():
    req = CreateVrfRequest(tenant="finance", name="finance-vrf")
    assert req.tenant == "finance"
    assert req.description == ""


@pytest.mark.parametrize("bad_name", ["bad name", "bad/name", "bad#name"])
def test_invalid_vrf_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateVrfRequest(tenant="finance", name=bad_name)


def test_vrf_name_allows_underscore_and_period():
    """ACI object names (unlike Tenant names) allow underscore/period/colon."""
    CreateVrfRequest(tenant="finance", name="finance_vrf.v1:prod")


def test_valid_bridge_domain_request():
    req = CreateBridgeDomainRequest(
        tenant="finance", vrf="finance-vrf", name="finance-bd", gateway_ip="10.10.10.1/24"
    )
    assert req.gateway_ip == "10.10.10.1/24"


def test_valid_epg_request():
    req = CreateEpgRequest(
        tenant="finance",
        application_profile="finance-ap",
        bridge_domain="finance-bd",
        name="finance-epg",
        vid=100,
    )
    assert req.vid == 100


@pytest.mark.parametrize("bad_vid", [0, 4095, -1])
def test_epg_vid_out_of_range_rejected(bad_vid):
    with pytest.raises(ValidationError):
        CreateEpgRequest(
            tenant="finance",
            application_profile="finance-ap",
            bridge_domain="finance-bd",
            name="finance-epg",
            vid=bad_vid,
        )


def test_valid_contract_request_defaults():
    req = CreateContractRequest(tenant="finance", name="web-to-db", filter_name="web-filter")
    assert req.scope == "context"
    assert req.ether_type == "ip"
    assert req.ip_protocol == "unspecified"


def test_valid_l3out_request_defaults():
    req = CreateL3OutRequest(
        tenant="finance", vrf="finance-vrf", name="l3out-internet", external_epg_name="ext-epg-internet"
    )
    assert req.subnet == "0.0.0.0/0"
    assert req.description == ""
