"""Nautobot-backed persistence for CanonicalIntent — Vertical Slice v0.1, Milestone 1.

Per docs/11-Specifications/03-Platform-Execution-Model-Specification.md §5
(Persistence Boundary), CanonicalIntent is the only Contract #1 object that
belongs in Nautobot. This module is the minimum real implementation of that
boundary: a CanonicalIntent is stored/retrieved as JSON in a Nautobot
Tenant's `canonical_intent` custom field (type JSON, content type
tenancy.tenant — created via the Nautobot REST API, no custom app/plugin).

Scope note (found during Milestone 1 implementation, not yet resolved):
domain_intent's Tenant/VRF/BridgeDomain/Prefix objects are NOT created or
updated by this module. SubmitIntent only requires a matching Nautobot
Tenant to already exist (see docs/05-Operations/14-Vertical-Slice-v0.1-Roadmap.md,
Milestone 1). Materializing domain_intent into new Nautobot inventory
objects is a real gap surfaced by this implementation, not yet assigned to
a milestone.
"""

from __future__ import annotations

import httpx

from canonical_intent import CanonicalIntent

_ACI_TENANT_PREFIX = "ACI:"  # matches platform/python/generator/transformer.py


class NautobotStoreError(Exception):
    """Raised when a CanonicalIntent cannot be persisted to or read from Nautobot."""


def _tenant_name(intent: CanonicalIntent) -> str:
    """Extract the ACI tenant name this intent targets.

    Milestone 1 scope: exactly one domain (cisco_aci), exactly one tenant
    per CanonicalIntent — matches the existing web-tenant vertical slice.
    Multi-tenant intents are out of scope until a Domain Provider
    Specification exists to define domain_intent's shape formally.
    """
    try:
        tenants = intent.domain_intent["apic"]["tenants"]
        return tenants[0]["name"]
    except (KeyError, IndexError, TypeError) as exc:
        raise NautobotStoreError(
            f"Could not extract a tenant name from domain_intent for domain_id={intent.domain_id!r}. "
            "Milestone 1 only supports the cisco_aci shape used by the existing vertical slice "
            "(domain_intent['apic']['tenants'][0]['name'])."
        ) from exc


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

    def save(self, intent: CanonicalIntent) -> None:
        tenant_id = self._find_tenant_id(intent)
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

    def _find_tenant_id(self, intent: CanonicalIntent) -> str:
        tenant_name = f"{_ACI_TENANT_PREFIX}{_tenant_name(intent)}"
        response = self._client.get("/api/tenancy/tenants/", params={"name": tenant_name})
        if response.status_code != 200:
            raise NautobotStoreError(
                f"Failed to look up Nautobot tenant {tenant_name!r}: {response.status_code} {response.text}"
            )
        results = response.json()["results"]
        if not results:
            raise NautobotStoreError(
                f"Nautobot tenant {tenant_name!r} does not exist. Milestone 1 requires the target tenant "
                "to already exist in Nautobot (SubmitIntent does not create infrastructure objects yet — "
                "see docs/05-Operations/14-Vertical-Slice-v0.1-Roadmap.md)."
            )
        return results[0]["id"]
