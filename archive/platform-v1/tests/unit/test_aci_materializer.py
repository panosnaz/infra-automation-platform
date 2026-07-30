"""Unit tests for ACI Domain Materialization — no live Nautobot required.

Uses httpx.MockTransport to exercise the real AciMaterializer's request
logic against fabricated Nautobot responses, mirroring the pattern already
established in test_technical_policy.py.
"""

from __future__ import annotations

import httpx
import pytest
from app.aci_materializer import AciMaterializer, MaterializationError, _to_network_prefix

_DOMAIN_INTENT = {
    "apic": {
        "tenants": [
            {
                "name": "test-tenant",
                "description": "test",
                "vrfs": [{"name": "test-vrf", "description": "test vrf"}],
                "bridge_domains": [
                    {
                        "name": "test-bd",
                        "unicast_routing": True,
                        "vrf": "test-vrf",
                        "subnets": [{"ip": "10.20.30.1/24", "public": False, "private": True, "shared": False}],
                    }
                ],
            }
        ]
    }
}


def test_to_network_prefix_converts_gateway_to_network() -> None:
    assert _to_network_prefix("10.10.10.1/24") == "10.10.10.0/24"


def test_to_network_prefix_leaves_network_address_unchanged() -> None:
    assert _to_network_prefix("10.10.10.0/24") == "10.10.10.0/24"


def test_malformed_domain_intent_raises() -> None:
    materializer = AciMaterializer(base_url="http://opa-unused", token="x")
    materializer._client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": []})))
    with pytest.raises(MaterializationError):
        materializer.materialize({"not": "the expected shape"})


def test_creates_tenant_namespace_vrf_prefix_assignment_when_none_exist() -> None:
    created_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET":
            if path == "/api/extras/statuses/":
                return httpx.Response(200, json={"results": [{"id": "status-active-id"}]})
            return httpx.Response(200, json={"results": []})  # nothing pre-exists
        if request.method == "POST":
            created_paths.append(path)
            body = httpx.Response(201, json={"id": f"new-id-for-{path}"})
            return body
        return httpx.Response(405)

    materializer = AciMaterializer(base_url="http://nautobot-unused", token="x")
    materializer._client = httpx.Client(base_url="http://nautobot-unused", transport=httpx.MockTransport(handler))

    materializer.materialize(_DOMAIN_INTENT)

    assert "/api/tenancy/tenants/" in created_paths
    assert "/api/ipam/namespaces/" in created_paths
    assert "/api/ipam/vrfs/" in created_paths
    assert "/api/ipam/prefixes/" in created_paths
    assert "/api/ipam/vrf-prefix-assignments/" in created_paths


def test_skips_creation_when_objects_already_exist() -> None:
    post_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET":
            if path == "/api/extras/statuses/":
                return httpx.Response(200, json={"results": [{"id": "status-active-id"}]})
            # Everything already exists.
            return httpx.Response(200, json={"results": [{"id": f"existing-id-for-{path}"}]})
        if request.method == "POST":
            post_calls.append(path)
            return httpx.Response(201, json={"id": "should-not-be-created"})
        return httpx.Response(405)

    materializer = AciMaterializer(base_url="http://nautobot-unused", token="x")
    materializer._client = httpx.Client(base_url="http://nautobot-unused", transport=httpx.MockTransport(handler))

    materializer.materialize(_DOMAIN_INTENT)

    assert post_calls == [], f"Expected no POST calls when everything already exists, got: {post_calls}"
