"""Nautobot GraphQL client for querying VXLAN EVPN platform objects.

Mirrors platform/python/generator/client.py's NautobotClient exactly (same
session/auth/error-handling shape) -- a separate module per ADR-021's file
layout decision, not a shared base class, matching ADR-018's "no shared
generic schema across domains" rule.
"""
from __future__ import annotations

from typing import Any

import requests

# ---------------------------------------------------------------------------
# GraphQL query definitions
# ---------------------------------------------------------------------------

# EVPN Tenants carry the "EVPN:" namespace prefix (see ADR-021 §2), mirroring
# ACI's "ACI:" convention but kept in a separate query so the two domains'
# Tenants are never conflated by a shared query shape.
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

# VLANs represent EVPN Bridge Domains directly (ADR-021 §2 -- unlike ACI,
# which derives Bridge Domains from Prefix descriptions, EVPN's bridge
# domain IS a VLAN in NX-OS's own data model).
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

# Prefixes supply the SVI gateway IP for a given VLAN (same "first host is
# the gateway" convention already used by the ACI generator).
_QUERY_PREFIXES = """
{
  prefixes {
    id
    prefix
    description
    tenant {
      name
    }
    vlan {
      id
      vid
    }
  }
}
"""

# Devices carry the fabric-wide BGP ASN and EVPN role (leaf/spine/border-leaf)
# -- genuinely per-device attributes, unlike ACI Phase B's fabric policies
# which are Location-scoped (see ADR-021 §2 for why Device, not Location,
# is correct here).
_QUERY_DEVICES = """
{
  devices {
    id
    name
    role {
      name
    }
    _custom_field_data
  }
}
"""


class NautobotEvpnClient:
    """Thin wrapper around the Nautobot GraphQL endpoint for EVPN objects."""

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

    def get_vlans(self) -> list[dict[str, Any]]:
        """Return all VLANs -- EVPN Bridge Domains."""
        return self._query(_QUERY_VLANS)["vlans"]

    def get_prefixes(self) -> list[dict[str, Any]]:
        """Return all prefixes -- used to derive each Bridge Domain's SVI gateway."""
        return self._query(_QUERY_PREFIXES)["prefixes"]

    def get_devices(self) -> list[dict[str, Any]]:
        """Return all devices -- the fabric's leaf/spine/border-leaf switches."""
        return self._query(_QUERY_DEVICES)["devices"]

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
