"""Unit tests for tools/evpn.py's business logic -- no live Nautobot needed.

Uses a lightweight fake NautobotClient double (duck-typed, registry.py's
dispatcher has no isinstance check) instead of mocking pynautobot's HTTP
layer -- these tests exist to catch regressions in what the tool *does*
with NautobotClient's return value (namespacing, field pass-through,
response shape), not to re-test NautobotClient itself.

Unlike tools/aci.py, every EVPN tool here explicitly adds the 'EVPN:'
tenant-namespace prefix itself (schemas/evpn.py's own docstring confirms
this is deliberate) -- these tests assert that prefixing actually happens.
"""
from __future__ import annotations

from mcp_server.schemas.evpn import (
    CreateEvpnBridgeDomainRequest,
    CreateEvpnTenantRequest,
    CreateEvpnVrfRequest,
)
from mcp_server.tools.evpn import create_evpn_bridge_domain, create_evpn_tenant, create_evpn_vrf


class _FakeNautobotClient:
    """Records every call it receives; returns a fixed fixture dict."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def create_tenant(self, **kwargs):
        self.calls.append(("create_tenant", kwargs))
        return {"id": "tenant-id", **kwargs}

    def create_evpn_vrf(self, **kwargs):
        self.calls.append(("create_evpn_vrf", kwargs))
        return {"id": "vrf-id", **kwargs}

    def create_evpn_bridge_domain(self, **kwargs):
        self.calls.append(("create_evpn_bridge_domain", kwargs))
        return {"id": "vlan-id", **kwargs}


def test_create_evpn_tenant_adds_evpn_prefix():
    fake = _FakeNautobotClient()
    request = CreateEvpnTenantRequest(name="acme", description="d")

    result = create_evpn_tenant(request, nautobot=fake)

    assert fake.calls == [("create_tenant", {"name": "EVPN:acme", "description": "d"})]
    assert result["tenant"]["name"] == "EVPN:acme"


def test_create_evpn_vrf_adds_evpn_prefix_and_passes_l3_vni():
    fake = _FakeNautobotClient()
    request = CreateEvpnVrfRequest(tenant="acme", name="acme-vrf", l3_vni=10001)

    result = create_evpn_vrf(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_evpn_vrf",
            {"tenant": "EVPN:acme", "name": "acme-vrf", "l3_vni": 10001, "description": ""},
        )
    ]
    assert result["vrf"]["l3_vni"] == 10001
    assert "EVPN:acme" in result["note"]
    assert "10001" in result["note"]


def test_create_evpn_bridge_domain_adds_evpn_prefix_and_passes_vlan_and_l2_vni():
    fake = _FakeNautobotClient()
    request = CreateEvpnBridgeDomainRequest(
        tenant="acme", vrf="acme-vrf", name="acme-bd", vlan_id=100, l2_vni=20001
    )

    result = create_evpn_bridge_domain(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_evpn_bridge_domain",
            {
                "tenant": "EVPN:acme",
                "vrf": "acme-vrf",
                "name": "acme-bd",
                "vlan_id": 100,
                "l2_vni": 20001,
                "description": "",
            },
        )
    ]
    assert result["vlan"]["l2_vni"] == 20001
    assert "EVPN:acme" in result["note"]
    assert "100" in result["note"]
    assert "20001" in result["note"]
