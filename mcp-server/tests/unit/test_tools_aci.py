"""Unit tests for tools/aci.py's business logic -- no live Nautobot needed.

Uses a lightweight fake NautobotClient double (duck-typed, registry.py's
dispatcher has no isinstance check) instead of mocking pynautobot's HTTP
layer -- these tests exist to catch regressions in what the tool *does*
with NautobotClient's return value (namespacing, field pass-through,
response shape), not to re-test NautobotClient itself.

This is the layer that had two real bugs caught only by live testing
during ADR-020 development (create_vrf missing a namespace, create_
bridge_domain embedding the raw 'ACI:' prefixed tenant name in its
description) -- these tests exist so a regression here is caught for
free next time, not only by re-running live verification.
"""
from __future__ import annotations

from mcp_server.schemas.aci import CreateBridgeDomainRequest, CreateL4L7DeviceRequest, CreateOneArmServiceGraphRequest, CreatePbrContractRequest, CreatePbrPolicyRequest, CreateServiceGraphRequest, CreateTenantRequest, CreateVmmDomainRequest, CreateVrfRequest, CreateVrfRouteLeakRequest
from mcp_server.tools.aci import create_bridge_domain, create_l4l7_device, create_one_arm_service_graph, create_pbr_contract, create_pbr_policy, create_service_graph, create_tenant, create_vmm_domain, create_vrf, create_vrf_route_leak


class _FakeNautobotClient:
    """Records every call it receives; returns a fixed fixture dict."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def create_tenant(self, **kwargs):
        self.calls.append(("create_tenant", kwargs))
        return {"id": "tenant-id", **kwargs}

    def create_vrf(self, **kwargs):
        self.calls.append(("create_vrf", kwargs))
        return {"id": "vrf-id", **kwargs}

    def create_bridge_domain(self, **kwargs):
        self.calls.append(("create_bridge_domain", kwargs))
        return {"id": "prefix-id", **kwargs}

    def create_vmm_domain(self, **kwargs):
        self.calls.append(("create_vmm_domain", kwargs))
        return {"id": "vmm-id", **kwargs}

    def create_l4l7_device(self, **kwargs):
        self.calls.append(("create_l4l7_device", kwargs))
        return {"id": "device-id", **kwargs}

    def create_service_graph(self, **kwargs):
        self.calls.append(("create_service_graph", kwargs))
        return {"id": "graph-id", **kwargs}

    def create_pbr_policy(self, **kwargs):
        self.calls.append(("create_pbr_policy", kwargs))
        return {"id": "policy-id", **kwargs}

    def create_pbr_contract(self, **kwargs):
        self.calls.append(("create_pbr_contract", kwargs))
        return {"id": "contract-id", **kwargs}

    def create_one_arm_service_graph(self, **kwargs):
        self.calls.append(("create_one_arm_service_graph", kwargs))
        return {"id": "one-arm-graph-id", **kwargs}

    def create_vrf_route_leak(self, **kwargs):
        self.calls.append(("create_vrf_route_leak", kwargs))
        return {"id": "route-leak-id", **kwargs}


def test_create_tenant_passes_name_through_unprefixed():
    """Current, real behavior: CreateTenantRequest.name is validated against
    ^[a-z0-9-]+$ (no colon allowed) and create_tenant() passes it straight
    through to NautobotClient.create_tenant() with no 'ACI:' prefix added --
    unlike EVPN's create_evpn_tenant, which adds 'EVPN:' itself. This means
    a tenant created via this MCP tool as-is will NOT carry the 'ACI:'
    prefix the live OPA tenant_naming policy expects (see the real
    'ACI:Sales' -> 'ACI:sales' incident in Platform-Status-and-Pending-
    Items.md) and would fail the pipeline's policy_check job. Documented
    here as a real gap, not asserted as correct/desired behavior."""
    fake = _FakeNautobotClient()
    request = CreateTenantRequest(name="acme", description="d")

    result = create_tenant(request, nautobot=fake)

    assert fake.calls == [("create_tenant", {"name": "acme", "description": "d"})]
    assert result["tenant"]["name"] == "acme"


def test_create_vrf_passes_tenant_and_name_through():
    fake = _FakeNautobotClient()
    request = CreateVrfRequest(tenant="ACI:acme", name="acme-vrf")

    result = create_vrf(request, nautobot=fake)

    assert fake.calls == [("create_vrf", {"tenant": "ACI:acme", "name": "acme-vrf", "description": ""})]
    assert result["vrf"]["name"] == "acme-vrf"
    assert "ACI:acme" in result["note"]


def test_create_bridge_domain_passes_gateway_ip_through():
    fake = _FakeNautobotClient()
    request = CreateBridgeDomainRequest(
        tenant="ACI:acme", vrf="acme-vrf", name="acme-bd", gateway_ip="10.0.0.1/24"
    )

    result = create_bridge_domain(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_bridge_domain",
            {
                "tenant": "ACI:acme",
                "vrf": "acme-vrf",
                "name": "acme-bd",
                "gateway_ip": "10.0.0.1/24",
                "description": "",
            },
        )
    ]
    assert result["prefix"]["name"] == "acme-bd"


def test_create_vmm_domain_passes_non_secret_metadata_only():
    fake = _FakeNautobotClient()
    request = CreateVmmDomainRequest(
        location="ACI-Lab",
        name="vmware-domain",
        controller_name="vcenter",
        host_or_ip="vcenter.example.com",
        root_cont_name="Datacenter",
        vlan_pool="pool1",
        credential_name="vcenter-cred",
    )

    result = create_vmm_domain(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_vmm_domain",
            {
                "location": "ACI-Lab",
                "name": "vmware-domain",
                "controller_name": "vcenter",
                "host_or_ip": "vcenter.example.com",
                "root_cont_name": "Datacenter",
                "vendor": "VMware",
                "vlan_pool": "pool1",
                "credential_name": "vcenter-cred",
                "dvs_version": "unmanaged",
            },
        )
    ]
    assert result["vmm_domain"]["name"] == "vmware-domain"


def test_l4l7_tools_pass_tenant_intent_through():
    fake = _FakeNautobotClient()

    device = create_l4l7_device(
        CreateL4L7DeviceRequest(tenant="ACI:acme", name="fw", consumer_interface="inside", provider_interface="outside", vmm_domain="acme-vmm"),
        nautobot=fake,
    )
    graph = create_service_graph(
        CreateServiceGraphRequest(
            tenant="ACI:acme",
            name="fw-graph",
            contract="web-to-db",
            device="fw",
            consumer_logical_interface="inside",
            consumer_redirect_policy="inside-pbr",
            provider_logical_interface="outside",
            provider_redirect_policy="outside-pbr",
        ),
        nautobot=fake,
    )
    policy = create_pbr_policy(
        CreatePbrPolicyRequest(tenant="ACI:acme", name="web-pbr", destination_ip="10.0.0.10"),
        nautobot=fake,
    )
    contract = create_pbr_contract(
        CreatePbrContractRequest(tenant="ACI:acme", name="web-to-db", filter_name="tcp-filter", service_graph="fw-graph", consumer_epg="web", provider_epg="db"),
        nautobot=fake,
    )

    assert [call[0] for call in fake.calls] == ["create_l4l7_device", "create_service_graph", "create_pbr_policy", "create_pbr_contract"]
    assert device["l4l7_device"]["name"] == "fw"
    assert graph["service_graph"]["name"] == "fw-graph"
    assert policy["pbr_policy"]["name"] == "web-pbr"
    assert contract["pbr_contract"]["name"] == "web-to-db"


def test_create_one_arm_service_graph_passes_single_arm_binding():
    fake = _FakeNautobotClient()
    request = CreateOneArmServiceGraphRequest(
        tenant="ACI:acme", name="adc-graph", contract="client-to-app", device="adc", logical_interface="client", redirect_policy="adc-pbr"
    )

    result = create_one_arm_service_graph(request, nautobot=fake)

    assert fake.calls[0][0] == "create_one_arm_service_graph"
    assert fake.calls[0][1]["redirect_policy"] == "adc-pbr"
    assert result["service_graph"]["name"] == "adc-graph"


def test_create_vrf_route_leak_passes_source_and_destination():
    fake = _FakeNautobotClient()
    request = CreateVrfRouteLeakRequest(
        tenant="ACI:acme",
        name="shared-to-app",
        source_vrf="shared-vrf",
        destination_vrf="app-vrf",
        subnet="10.10.10.0/24",
        allow_l3out_advertisement=True,
    )

    result = create_vrf_route_leak(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_vrf_route_leak",
            {
                "tenant": "ACI:acme",
                "name": "shared-to-app",
                "source_vrf": "shared-vrf",
                "destination_vrf": "app-vrf",
                "subnet": "10.10.10.0/24",
                "allow_l3out_advertisement": True,
                "description": "",
            },
        )
    ]
    assert result["vrf_route_leak"]["source_vrf"] == "shared-vrf"
