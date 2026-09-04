"""Unit tests for ACI tool input validation -- no live Nautobot needed."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.schemas.aci import (
    CreateAepRequest,
    CreateBridgeDomainRequest,
    CreateContractRequest,
    CreateEpgRequest,
    CreateL3OutRequest,
    CreateLeafInterfacePolicyGroupRequest,
    CreatePhysicalDomainRequest,
    CreateTenantRequest,
    CreateVlanPoolRequest,
    CreateVmmDomainRequest,
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


def test_valid_vlan_pool_request_defaults():
    req = CreateVlanPoolRequest(name="pool1", range_from=100, range_to=200)
    assert req.location == "ACI-Lab"
    assert req.alloc_mode == "static"
    assert req.role == "external"
    assert req.range_alloc_mode is None


@pytest.mark.parametrize("bad_vid", [0, 4095])
def test_vlan_pool_range_out_of_bounds_rejected(bad_vid):
    with pytest.raises(ValidationError):
        CreateVlanPoolRequest(name="pool1", range_from=bad_vid, range_to=200)


def test_valid_physical_domain_request_defaults():
    req = CreatePhysicalDomainRequest(name="phys-dom1")
    assert req.location == "ACI-Lab"
    assert req.vlan_pool is None


def test_valid_aep_request_defaults():
    req = CreateAepRequest(name="aep1")
    assert req.domains == []


def test_aep_request_with_domains():
    req = CreateAepRequest(name="aep1", domains=["phys-dom1", "phys-dom2"])
    assert req.domains == ["phys-dom1", "phys-dom2"]


def test_valid_leaf_interface_policy_group_request_defaults():
    req = CreateLeafInterfacePolicyGroupRequest(name="leaf-pg1")
    assert req.aep is None


def test_valid_vmm_domain_request_defaults():
    req = CreateVmmDomainRequest(
        name="vmm1", controller_name="vc1", host_or_ip="vcenter.example.com", root_cont_name="Datacenter1"
    )
    assert req.location == "ACI-Lab"
    assert req.vendor == "VMware"
    assert req.vlan_pool is None
    assert req.credential_name is None
    assert req.dvs_version == "unmanaged"


def test_vmm_domain_request_with_optional_fields():
    req = CreateVmmDomainRequest(
        name="vmm1",
        controller_name="vc1",
        host_or_ip="vcenter.example.com",
        root_cont_name="Datacenter1",
        vlan_pool="pool1",
        credential_name="vc1-cred",
    )
    assert req.vlan_pool == "pool1"
    assert req.credential_name == "vc1-cred"


@pytest.mark.parametrize("bad_name", ["bad name", "bad/name", "bad#name"])
def test_invalid_vmm_domain_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateVmmDomainRequest(
            name=bad_name, controller_name="vc1", host_or_ip="vcenter.example.com", root_cont_name="Datacenter1"
        )
