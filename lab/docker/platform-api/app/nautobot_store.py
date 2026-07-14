"""Nautobot-backed persistence for CanonicalIntent — Vertical Slice v0.1, Milestone 1.

Per docs/11-Specifications/03-Platform-Execution-Model-Specification.md §5
(Persistence Boundary), CanonicalIntent is the only Contract #1 object that
belongs in Nautobot. This module is the minimum real implementation of that
boundary: a CanonicalIntent is stored/retrieved as JSON in a Nautobot
Tenant's `canonical_intent` custom field (type JSON, content type
tenancy.tenant — created via the Nautobot REST API, no custom app/plugin).

SubmitIntent requires the target Tenant to already exist by the time
save() is called — app/aci_materializer.py creates it (and its VRF/Prefix
objects) beforehand, closing what was a real gap through Milestone 3.
"""

from __future__ import annotations

import httpx

from canonical_intent import CanonicalIntent


class NautobotStoreError(Exception):
    """Raised when a CanonicalIntent cannot be persisted to or read from Nautobot."""


class NautobotIntentStore:
    """Persists/retrieves CanonicalIntent via a Nautobot Tenant's `canonical_intent` custom field."""

    def __init__(self, base_url: str, token: str, timeout: float = 5.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Token {token}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def save(self, intent: CanonicalIntent, tenant_name: str) -> None:
        """Persist intent to the Nautobot Tenant named `tenant_name`.

        `tenant_name` must be the exact Nautobot Tenant.name value (e.g.
        already carrying any domain-specific namespace prefix) — resolving
        it from domain_intent is the caller's responsibility, not this
        store's. This method has no knowledge of domain_intent's shape.
        """
        tenant_id = self._find_tenant_id(tenant_name)
        response = self._client.patch(
            f"/api/tenancy/tenants/{tenant_id}/",
            json={"custom_fields": {"canonical_intent": intent.model_dump(mode="json")}},
        )
        if response.status_code != 200:
            raise NautobotStoreError(
                f"Failed to persist CanonicalIntent {intent.intent_id} to Nautobot Tenant {tenant_id}: "
                f"{response.status_code} {response.text}"
            )

    def get(self, intent_id: str, engineering_version: int) -> CanonicalIntent:
        """Retrieve a CanonicalIntent by scanning tenants for a matching custom field value.

        Milestone 1 scope: a linear scan over tenants with a non-null
        `canonical_intent` custom field — the vertical slice has one
        tenant, so an index would be speculative right now. If this
        becomes a real bottleneck in a later milestone, that is a concrete
        signal to add one; it is not built ahead of that signal.
        """
        response = self._client.get("/api/tenancy/tenants/", params={"limit": 0})
        if response.status_code != 200:
            raise NautobotStoreError(f"Failed to list Nautobot tenants: {response.status_code} {response.text}")

        for tenant in response.json()["results"]:
            raw = (tenant.get("custom_fields") or {}).get("canonical_intent")
            if not raw:
                continue
            if raw.get("intent_id") == str(intent_id) and raw.get("engineering_version") == engineering_version:
                return CanonicalIntent.model_validate(raw)

        raise NautobotStoreError(
            f"No CanonicalIntent found for intent_id={intent_id} engineering_version={engineering_version}"
        )

    def _find_tenant_id(self, tenant_name: str) -> str:
        response = self._client.get("/api/tenancy/tenants/", params={"name": tenant_name})
        if response.status_code != 200:
            raise NautobotStoreError(
                f"Failed to look up Nautobot tenant {tenant_name!r}: {response.status_code} {response.text}"
            )
        results = response.json()["results"]
        if not results:
            raise NautobotStoreError(
                f"Nautobot tenant {tenant_name!r} does not exist and materialization did not create it "
                "(app/aci_materializer.py runs before this call — this indicates a real bug, not an "
                "expected/known limitation)."
            )
        return results[0]["id"]
