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
    vrfs {
      id
      name
      description
    }
  }
}
"""

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
