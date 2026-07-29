"""Unit tests for ACI tool input validation -- no live Nautobot needed."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.schemas.aci import CreateTenantRequest


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
