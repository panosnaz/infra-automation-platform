"""Thin pynautobot wrapper -- the only place tools touch the Nautobot SDK
directly, so client construction/error-mapping stays in one place.
"""
from __future__ import annotations

import pynautobot

from mcp_server.errors import NautobotError


class NautobotClient:
    def __init__(self, url: str, token: str) -> None:
        self._url = url
        self._token = token
        self._api: pynautobot.api | None = None

    @property
    def api(self) -> pynautobot.api:
        if self._api is None:
            self._api = pynautobot.api(self._url, token=self._token)
        return self._api

    def create_tenant(self, name: str, description: str = "") -> dict:
        """Create a Tenant object -- the same shape a human editing the
        Nautobot UI would produce (ADR-018: no intermediate intent schema).
        """
        try:
            tenant = self.api.tenancy.tenants.create(
                name=name,
                description=description,
            )
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected tenant '{name}': {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - network/auth failures, mapped uniformly
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return dict(tenant)

    def get_tenant_status(self, name: str) -> dict | None:
        """Read back the custom_fields write_results.py (Milestone 4) writes
        after a pipeline run -- validation_status/last_pipeline_id/etc.
        """
        try:
            tenant = self.api.tenancy.tenants.get(name=name)
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        if tenant is None:
            return None
        return dict(tenant)

    def ping(self) -> None:
        """Cheap reachability check for the /health endpoint (Ref-Arch §7.6)
        -- raises NautobotError on failure, returns None on success."""
        try:
            self.api.status()
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
