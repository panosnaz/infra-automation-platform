"""Unit tests for ACI tool input validation -- no live Nautobot needed."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.schemas.aci import (
    CreateBridgeDomainRequest,
    CreateContractRequest,
    CreateEpgRequest,
    CreateL3OutRequest,
    CreateL4L7DeviceRequest,
    CreateOneArmServiceGraphRequest,
    CreatePbrContractRequest,
    CreatePbrPolicyRequest,
    CreateServiceGraphRequest,
    CreateTenantRequest,
    CreateVmmDomainRequest,
    CreateVrfRouteLeakRequest,
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


def test_valid_vmm_domain_request_defaults():
    req = CreateVmmDomainRequest(
        location="ACI-Lab",
        name="vmware-domain",
        controller_name="vcenter",
        host_or_ip="vcenter.example.com",
        root_cont_name="Datacenter",
    )
    assert req.vendor == "VMware"
    assert req.dvs_version == "unmanaged"
    assert req.vlan_pool is None
    assert req.credential_name is None


def test_invalid_vmm_domain_name_rejected():
    with pytest.raises(ValidationError):
        CreateVmmDomainRequest(
            location="ACI-Lab",
            name="bad name",
            controller_name="vcenter",
            host_or_ip="vcenter.example.com",
            root_cont_name="Datacenter",
        )


def test_l4l7_and_pbr_request_defaults():
    device = CreateL4L7DeviceRequest(
        tenant="finance", name="fw", consumer_interface="inside", provider_interface="outside", vmm_domain="finance-vmm"
    )
    graph = CreateServiceGraphRequest(
        tenant="finance",
        name="fw-graph",
        contract="web-to-db",
        device="fw",
        consumer_logical_interface="inside",
        consumer_redirect_policy="inside-pbr",
        provider_logical_interface="outside",
        provider_redirect_policy="outside-pbr",
    )
    policy = CreatePbrPolicyRequest(tenant="finance", name="web-pbr", destination_ip="10.0.0.10")
    contract = CreatePbrContractRequest(
        tenant="finance",
        name="web-to-db",
        filter_name="tcp-filter",
        service_graph="fw-graph",
        consumer_epg="web",
        provider_epg="db",
    )

    assert device.service_type == "FW"
    assert graph.node_name == "node-1"
    assert policy.destination_type == "L3"
    assert contract.ip_protocol == "unspecified"


def test_invalid_service_graph_name_rejected():
    with pytest.raises(ValidationError):
        CreateServiceGraphRequest(
            tenant="finance",
            name="bad graph",
            contract="web-to-db",
            device="fw",
            consumer_logical_interface="inside",
            consumer_redirect_policy="inside-pbr",
            provider_logical_interface="outside",
            provider_redirect_policy="outside-pbr",
        )


def test_virtual_l4l7_device_requires_vmm_domain():
    with pytest.raises(ValidationError):
        CreateL4L7DeviceRequest(tenant="finance", name="fw", consumer_interface="inside", provider_interface="outside")


def test_one_arm_device_and_service_graph_request():
    device = CreateL4L7DeviceRequest(tenant="finance", name="adc", consumer_interface="client", vmm_domain="finance-vmm")
    graph = CreateOneArmServiceGraphRequest(
        tenant="finance", name="adc-graph", contract="client-to-app", device="adc", logical_interface="client", redirect_policy="adc-pbr"
    )

    assert device.provider_interface is None
    assert graph.template_type == "ONE_NODE_ADC_ONE_ARM"


def test_vrf_route_leak_request_defaults_and_distinct_vrfs():
    request = CreateVrfRouteLeakRequest(
        tenant="finance",
        name="shared-to-app",
        source_vrf="shared-vrf",
        destination_vrf="app-vrf",
        subnet="10.10.10.0/24",
    )

    assert request.allow_l3out_advertisement is False


def test_vrf_route_leak_rejects_same_source_and_destination():
    with pytest.raises(ValidationError):
        CreateVrfRouteLeakRequest(
            tenant="finance",
            name="invalid-leak",
            source_vrf="app-vrf",
            destination_vrf="app-vrf",
            subnet="10.10.10.0/24",
        )
