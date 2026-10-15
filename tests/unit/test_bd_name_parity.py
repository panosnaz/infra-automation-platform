"""The MCP Server and the generator must agree on what a bridge domain is called.

The generator decides a BD's name from its Prefix (description first, then a
name derived from the network). The MCP Server's read/update/delete tools
find BDs by that same name, using their own copy of the rule in
mcp_server/intent_refs.py -- the server container does not ship the
generator. If the two copies drift, update_bridge_domain and the delete tool
quietly stop finding BDs the pipeline still deploys.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform" / "python"))
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))

from generator.transformer import _parse_bd_name, _sanitise_prefix_as_bd_name  # noqa: E402
from mcp_server.intent_refs import bd_name_for_prefix  # noqa: E402


def _generator_name(prefix: str, description: str | None) -> str:
    return _parse_bd_name(description or "") or _sanitise_prefix_as_bd_name(prefix)


@pytest.mark.parametrize("prefix,description", [
    ("10.0.1.0/24", "ACI Bridge Domain: web-bd:sales"),
    ("10.0.1.0/24", "ACI Bridge Domain: web-bd:sales -- no-subnet"),
    ("10.0.1.0/24", "ACI Bridge Domain: web-bd:sales -- subnet-scope:public -- text: with colon"),
    ("10.0.1.0/24", "ACI Bridge Domain:   spaced-bd  :sales"),
    ("10.0.1.0/24", "  ACI Bridge Domain: padded:sales  "),
    ("10.0.3.0/24", "not an ACI description"),
    ("10.0.3.0/24", ""),
    ("10.0.3.0/24", None),
    ("2001:db8::/64", None),
])
def test_both_sides_name_the_bridge_domain_identically(prefix, description):
    assert bd_name_for_prefix(prefix, description) == _generator_name(prefix, description)
