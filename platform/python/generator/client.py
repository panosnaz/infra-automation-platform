"""Nautobot GraphQL client for querying ACI platform objects."""

from __future__ import annotations

from typing import Any

import requests

# ---------------------------------------------------------------------------
# GraphQL query definitions
# ---------------------------------------------------------------------------

_QUERY_TENANTS = """
{
  tenants {
    id
    name
    description
    _custom_field_data
    vrfs {
      id
      name
      description
      _custom_field_data
    }
  }
}
"""
# ADR-020 Phase A item 3: Contracts/Filters/Subjects have no natural home in
# Nautobot's existing Tenant/VRF/Prefix/VLAN model, so (per that item's design
# note) they are stored as a single structured JSON Custom Field on Tenant
# (`aci_contracts`, holding `{"filters": [...], "contracts": [...]}`) rather
# than adding new Nautobot models -- read via the `_custom_field_data` field
# added above. EPG-level provided/consumed contract references live on the
# EPG's own VLAN object (`aci_epg_contracts` JSON custom field), read via
# `_QUERY_VLANS`'s existing `_custom_field_data` field below.

_QUERY_PREFIXES = """
{
  prefixes {
    id
    prefix
    description
    tenant {
      name
    }
    vrfs {
      name
    }
    _custom_field_data
  }
}
"""

# ADR-020 Phase A item 2: EPGs are represented as VLANs (no new Nautobot
# plugin/model, per that decision's explicit constraint) -- only VLANs with
# both aci_application_profile and aci_epg_bridge_domain custom fields set
# are exported as EPGs (see transformer.py's _build_application_profiles()).
_QUERY_VLANS = """
{
  vlans {
    id
    name
    vid
    description
    tenant {
      name
    }
    _custom_field_data
  }
}
"""


class NautobotClient:
    """Thin wrapper around the Nautobot GraphQL endpoint."""

    def __init__(self, url: str, token: str, verify_ssl: bool = True) -> None:
        self._graphql_url = f"{url.rstrip('/')}/api/graphql/"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        self._verify_ssl = verify_ssl

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def get_tenants(self) -> list[dict[str, Any]]:
        """Return all tenants with their associated VRFs."""
        return self._query(_QUERY_TENANTS)["tenants"]

    def get_prefixes(self) -> list[dict[str, Any]]:
        """Return all prefixes with tenant and VRF associations."""
        return self._query(_QUERY_PREFIXES)["prefixes"]

    def get_vlans(self) -> list[dict[str, Any]]:
        """Return all VLANs with tenant association -- used to represent
        EPGs (ADR-020 Phase A item 2)."""
        return self._query(_QUERY_VLANS)["vlans"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self._session.post(
            self._graphql_url,
            json=payload,
            verify=self._verify_ssl,
            timeout=30,
        )
        response.raise_for_status()

        body = response.json()
        if errors := body.get("errors"):
            raise RuntimeError(f"GraphQL errors: {errors}")

        return body["data"]
