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

from mcp_server.schemas.aci import (
    CreateAepRequest,
    CreateBridgeDomainRequest,
    CreateLeafInterfacePolicyGroupRequest,
    CreatePhysicalDomainRequest,
    CreateTenantRequest,
    CreateVlanPoolRequest,
    CreateVmmDomainRequest,
    CreateVrfRequest,
)
from mcp_server.tools.aci import (
    create_aep,
    create_bridge_domain,
    create_leaf_interface_policy_group,
    create_physical_domain,
    create_tenant,
    create_vlan_pool,
    create_vmm_domain,
    create_vrf,
)


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

    def create_vlan_pool(self, **kwargs):
        self.calls.append(("create_vlan_pool", kwargs))
        return {"location": kwargs["location"], "vlan_pool": kwargs["name"], "vlan_pools": []}

    def create_physical_domain(self, **kwargs):
        self.calls.append(("create_physical_domain", kwargs))
        return {"location": kwargs["location"], "physical_domain": kwargs["name"], "physical_domains": []}

    def create_aep(self, **kwargs):
        self.calls.append(("create_aep", kwargs))
        return {"location": kwargs["location"], "aep": kwargs["name"], "aeps": []}

    def create_leaf_interface_policy_group(self, **kwargs):
        self.calls.append(("create_leaf_interface_policy_group", kwargs))
        return {"location": kwargs["location"], "leaf_interface_policy_group": kwargs["name"], "leaf_interface_policy_groups": []}

    def create_vmm_domain(self, **kwargs):
        self.calls.append(("create_vmm_domain", kwargs))
        return {"location": kwargs["location"], "vmm_domain": kwargs["name"], "vmm_domains": []}


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


def test_create_vlan_pool_passes_range_through():
    fake = _FakeNautobotClient()
    request = CreateVlanPoolRequest(name="pool1", range_from=100, range_to=200)

    result = create_vlan_pool(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_vlan_pool",
            {
                "location": "ACI-Lab",
                "name": "pool1",
                "alloc_mode": "static",
                "range_from": 100,
                "range_to": 200,
                "range_alloc_mode": None,
                "role": "external",
                "description": "",
            },
        )
    ]
    assert result["vlan_pool"]["vlan_pool"] == "pool1"
    assert "100-200" in result["note"]


def test_create_physical_domain_passes_vlan_pool_through():
    fake = _FakeNautobotClient()
    request = CreatePhysicalDomainRequest(name="phys-dom1", vlan_pool="pool1")

    result = create_physical_domain(request, nautobot=fake)

    assert fake.calls == [
        ("create_physical_domain", {"location": "ACI-Lab", "name": "phys-dom1", "vlan_pool": "pool1"})
    ]
    assert result["physical_domain"]["physical_domain"] == "phys-dom1"


def test_create_aep_passes_domains_through():
    fake = _FakeNautobotClient()
    request = CreateAepRequest(name="aep1", domains=["phys-dom1", "phys-dom2"])

    result = create_aep(request, nautobot=fake)

    assert fake.calls == [
        ("create_aep", {"location": "ACI-Lab", "name": "aep1", "domains": ["phys-dom1", "phys-dom2"]})
    ]
    assert result["aep"]["aep"] == "aep1"


def test_create_aep_defaults_to_no_domains():
    fake = _FakeNautobotClient()
    request = CreateAepRequest(name="aep1")

    create_aep(request, nautobot=fake)

    assert fake.calls == [("create_aep", {"location": "ACI-Lab", "name": "aep1", "domains": []})]


def test_create_leaf_interface_policy_group_passes_aep_through():
    fake = _FakeNautobotClient()
    request = CreateLeafInterfacePolicyGroupRequest(name="leaf-pg1", aep="aep1")

    result = create_leaf_interface_policy_group(request, nautobot=fake)

    assert fake.calls == [
        ("create_leaf_interface_policy_group", {"location": "ACI-Lab", "name": "leaf-pg1", "aep": "aep1"})
    ]
    assert result["leaf_interface_policy_group"]["leaf_interface_policy_group"] == "leaf-pg1"


def test_create_vmm_domain_passes_fields_through():
    fake = _FakeNautobotClient()
    request = CreateVmmDomainRequest(
        name="vmm1",
        controller_name="vc1",
        host_or_ip="vcenter.example.com",
        root_cont_name="Datacenter1",
        vlan_pool="pool1",
        credential_name="vc1-cred",
    )

    result = create_vmm_domain(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_vmm_domain",
            {
                "location": "ACI-Lab",
                "name": "vmm1",
                "controller_name": "vc1",
                "host_or_ip": "vcenter.example.com",
                "root_cont_name": "Datacenter1",
                "vendor": "VMware",
                "vlan_pool": "pool1",
                "credential_name": "vc1-cred",
                "dvs_version": "unmanaged",
            },
        )
    ]
    assert result["vmm_domain"]["vmm_domain"] == "vmm1"
