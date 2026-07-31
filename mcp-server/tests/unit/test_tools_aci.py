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

from mcp_server.schemas.aci import CreateBridgeDomainRequest, CreateTenantRequest, CreateVrfRequest
from mcp_server.tools.aci import create_bridge_domain, create_tenant, create_vrf


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
