"""ACI Domain Materialization — Vertical Slice v0.1, Business Approval follow-up.

Creates Nautobot Tenant/Namespace/VRF/Prefix/VRFPrefixAssignment objects
for a cisco_aci CanonicalIntent's domain_intent, closing the Milestone 1 gap
where SubmitIntent required the target Tenant to already exist.

Domain-specific by nature — matches platform/python/generator/
transformer.py's *read-side* expectations exactly (the "ACI:" tenant
prefix, the "ACI Bridge Domain: <bd>:<tenant>" description encoding, VRFs
associated via the tenants.vrfs relationship, BDs derived from Prefix +
VRFPrefixAssignment) so a materialized tenant round-trips correctly
through the existing generator. Lives at the domain-aware boundary,
alongside _aci_tenant_name() in main.py — never inside NautobotIntentStore,
which must stay domain-agnostic (Contract #1's opacity rule for
domain_intent, the same rule the Milestone 1 Architecture Validation
Review already enforced once).

Scope: create-if-missing only. An object that already exists (matched by
name/prefix) is left as-is — this does not reconcile drift between a
resubmitted domain_intent and what's already in Nautobot. Drift detection/
reconciliation is DRIFTED's job (Contract #3), not implemented yet.
"""

from __future__ import annotations

import ipaddress
from typing import Any

import httpx

_ACI_TENANT_PREFIX = "ACI:"  # matches platform/python/generator/transformer.py


class MaterializationError(Exception):
    """Raised when domain_intent cannot be materialized into Nautobot objects."""


class AciMaterializer:
    def __init__(self, base_url: str, token: str, timeout: float = 10.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), headers={"Authorization": f"Token {token}"}, timeout=timeout)
        self._active_status_id: str | None = None

    def close(self) -> None:
        self._client.close()

    def materialize(self, domain_intent: dict[str, Any]) -> None:
        try:
            aci_tenants = domain_intent["apic"]["tenants"]
        except (KeyError, TypeError) as exc:
            raise MaterializationError(f"domain_intent does not have the expected cisco_aci shape: {exc}") from exc

        for tenant_spec in aci_tenants:
            self._materialize_tenant(tenant_spec)

    def _materialize_tenant(self, tenant_spec: dict[str, Any]) -> None:
        tenant_name = f"{_ACI_TENANT_PREFIX}{tenant_spec['name']}"
        tenant_id = self._ensure_tenant(tenant_name, tenant_spec.get("description", ""))
        namespace_id = self._ensure_namespace(tenant_name)

        vrf_ids: dict[str, str] = {}
        for vrf_spec in tenant_spec.get("vrfs", []):
            vrf_ids[vrf_spec["name"]] = self._ensure_vrf(vrf_spec, tenant_id, namespace_id)

        for bd_spec in tenant_spec.get("bridge_domains", []):
            self._materialize_bridge_domain(bd_spec, tenant_spec["name"], tenant_id, namespace_id, vrf_ids)

    def _ensure_tenant(self, tenant_name: str, description: str) -> str:
        existing = self._get("/api/tenancy/tenants/", {"name": tenant_name})
        if existing:
            return existing[0]["id"]
        created = self._post("/api/tenancy/tenants/", {"name": tenant_name, "description": description})
        return created["id"]

    def _ensure_namespace(self, tenant_name: str) -> str:
        existing = self._get("/api/ipam/namespaces/", {"name": tenant_name})
        if existing:
            return existing[0]["id"]
        created = self._post("/api/ipam/namespaces/", {"name": tenant_name})
        return created["id"]

    def _ensure_vrf(self, vrf_spec: dict[str, Any], tenant_id: str, namespace_id: str) -> str:
        existing = self._get("/api/ipam/vrfs/", {"name": vrf_spec["name"], "tenant_id": tenant_id})
        if existing:
            return existing[0]["id"]
        payload = {
            "name": vrf_spec["name"],
            "tenant": tenant_id,
            "namespace": namespace_id,
            "description": vrf_spec.get("description", ""),
        }
        created = self._post("/api/ipam/vrfs/", payload)
        return created["id"]

    def _materialize_bridge_domain(
        self, bd_spec: dict[str, Any], tenant_name: str, tenant_id: str, namespace_id: str, vrf_ids: dict[str, str]
    ) -> None:
        for subnet_spec in bd_spec.get("subnets", []):
            network = _to_network_prefix(subnet_spec["ip"])
            existing = self._get("/api/ipam/prefixes/", {"prefix": network, "tenant_id": tenant_id})
            if existing:
                prefix_id = existing[0]["id"]
            else:
                payload = {
                    "prefix": network,
                    "tenant": tenant_id,
                    "namespace": namespace_id,
                    "status": self._active_status(),
                    "description": f"ACI Bridge Domain: {bd_spec['name']}:{tenant_name}",
                }
                created = self._post("/api/ipam/prefixes/", payload)
                prefix_id = created["id"]

            vrf_name = bd_spec.get("vrf")
            if vrf_name and vrf_name in vrf_ids:
                self._ensure_vrf_prefix_assignment(vrf_ids[vrf_name], prefix_id)

    def _ensure_vrf_prefix_assignment(self, vrf_id: str, prefix_id: str) -> None:
        # Nautobot's filter fields are `vrf`/`prefix`, NOT `vrf_id`/`prefix_id`
        # (confirmed empirically -- the assignment endpoint rejects the _id
        # suffix with "Unknown filter field", unlike vrfs/prefixes which accept it).
        existing = self._get("/api/ipam/vrf-prefix-assignments/", {"vrf": vrf_id, "prefix": prefix_id})
        if existing:
            return
        self._post("/api/ipam/vrf-prefix-assignments/", {"vrf": vrf_id, "prefix": prefix_id})

    def _active_status(self) -> str:
        if self._active_status_id is None:
            results = self._get("/api/extras/statuses/", {"name": "Active", "content_types": "ipam.prefix"})
            if not results:
                raise MaterializationError("No 'Active' status found for ipam.prefix in Nautobot")
            self._active_status_id = results[0]["id"]
        return self._active_status_id

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        response = self._client.get(path, params=params)
        if response.status_code != 200:
            raise MaterializationError(f"GET {path} failed: {response.status_code} {response.text}")
        return response.json()["results"]

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(path, json=payload)
        if response.status_code not in (200, 201):
            raise MaterializationError(f"POST {path} failed: {response.status_code} {response.text}")
        return response.json()


def _to_network_prefix(host_prefix: str) -> str:
    """Convert a gateway/host address like '10.10.10.1/24' to its network address '10.10.10.0/24'.

    domain_intent carries the ACI BD gateway IP (a host address); Nautobot
    Prefix objects store network addresses. This is the forward-direction
    counterpart of transformer.py's _to_gateway_ip(), which does the
    reverse when reading Nautobot data back out.
    """
    network = ipaddress.ip_network(host_prefix, strict=False)
    return str(network)
