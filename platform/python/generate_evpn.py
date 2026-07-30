#!/usr/bin/env python3
"""Nautobot → VXLAN EVPN NetAsCode-equivalent YAML Generator
==============================================================
Queries Nautobot via GraphQL, transforms the result, and writes an
EVPN-domain YAML (platform/netascode/evpn/fabric.yaml) consumed by the
CiscoDevNet/nxos Terraform provider (ADR-021).

Mirrors platform/python/generate_aci.py's structure exactly -- a sibling
script, not a shared code path, per ADR-018's "each domain gets its own
generator" rule.

Usage
-----
    # From repo root:
    python platform/python/generate_evpn.py --token <TOKEN>

    # Using environment variable:
    NAUTOBOT_TOKEN=<TOKEN> python platform/python/generate_evpn.py

    # Dry-run (print YAML, do not write files):
    python platform/python/generate_evpn.py --token <TOKEN> --dry-run

    # Read credentials from HashiCorp Vault (lab stack at http://localhost:8200):
    python platform/python/generate_evpn.py \
        --vault-addr http://localhost:8200 \
        --vault-token <ROOT_TOKEN>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import requests
import yaml

# Allow running as a plain script from anywhere in the repo tree
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from generator.evpn_client import NautobotEvpnClient
from generator.evpn_transformer import build_evpn_fabric_yaml

_DEFAULT_URL = "http://localhost:8080"
# Default output: platform/netascode/evpn/ (sibling of platform/python/)
_DEFAULT_OUTPUT = _HERE.parent / "netascode" / "evpn"


def _vault_read_secret(vault_addr: str, vault_token: str, path: str) -> dict[str, str]:
    """Read a KV v2 secret from Vault using stdlib HTTP (no hvac required)."""
    url = f"{vault_addr.rstrip('/')}/v1/secret/data/{path}"
    req = urllib.request.Request(url, headers={"X-Vault-Token": vault_token})
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return json.loads(resp.read())["data"]["data"]
    except Exception as exc:
        raise RuntimeError(f"Vault: failed to read '{path}' from {vault_addr}: {exc}") from exc


def main() -> None:
    args = _parse_args()

    vault_addr = args.vault_addr or os.environ.get("VAULT_ADDR", "")
    vault_token = args.vault_token or os.environ.get("VAULT_TOKEN", "")

    token = args.token or os.environ.get("NAUTOBOT_TOKEN", "")
    nautobot_url = args.url

    if vault_addr and vault_token and not token:
        print(f"[generator] Reading Nautobot token from Vault at {vault_addr}")
        try:
            platform_secret = _vault_read_secret(vault_addr, vault_token, "lab/platform")
            token = token or platform_secret.get("nautobot_api_token", "")
        except RuntimeError as exc:
            print(f"WARNING: {exc}", file=sys.stderr)

    if not token:
        print(
            "ERROR: Nautobot API token required. Use --token, set NAUTOBOT_TOKEN, "
            "or provide --vault-addr + --vault-token.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = NautobotEvpnClient(
        url=nautobot_url,
        token=token,
        verify_ssl=not args.no_verify,
    )

    print(f"[generator] Querying Nautobot at {nautobot_url}")
    try:
        tenants = client.get_tenants()
        vlans = client.get_vlans()
        prefixes = client.get_prefixes()
        devices = client.get_devices()
    except requests.RequestException as exc:
        print(f"ERROR: Failed to query Nautobot at {nautobot_url}: {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"ERROR: Nautobot GraphQL query failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(
        f"[generator]   tenants={len(tenants)}  vlans={len(vlans)}  "
        f"prefixes={len(prefixes)}  devices={len(devices)}"
    )

    data = build_evpn_fabric_yaml(
        tenants=tenants,
        vlans=vlans,
        prefixes=prefixes,
        devices=devices,
    )

    exported = len(data.get("fabric", {}).get("tenants", []))
    onboarded_devices = len(data.get("fabric", {}).get("devices", []))
    print(f"[generator]   exporting {exported} tenant(s), {onboarded_devices} onboarded device(s)")

    if args.dry_run:
        print("[generator]   --dry-run: output below\n")
        print("---")
        yaml.dump(data, sys.stdout, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return

    args.output.mkdir(parents=True, exist_ok=True)
    out_file = args.output / "fabric.yaml"
    with open(out_file, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"[generator]   written → {out_file}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("NAUTOBOT_URL", _DEFAULT_URL),
        metavar="URL",
        help="Nautobot base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--token",
        default="",
        metavar="TOKEN",
        help="Nautobot API token (or set NAUTOBOT_TOKEN env var)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        metavar="DIR",
        help="Output directory for YAML files (default: %(default)s)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Disable SSL certificate verification",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print YAML to stdout without writing files",
    )
    parser.add_argument(
        "--vault-addr",
        default="",
        metavar="URL",
        help="Vault address (e.g. http://localhost:8200). Reads credentials from secret/lab/platform "
             "when --token is not set. Also accepts VAULT_ADDR env var.",
    )
    parser.add_argument(
        "--vault-token",
        default="",
        metavar="TOKEN",
        help="Vault token (or set VAULT_TOKEN env var).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
