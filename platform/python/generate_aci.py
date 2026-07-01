#!/usr/bin/env python3
"""Nautobot → NetAsCode ACI YAML Generator
==========================================
Queries Nautobot via GraphQL, transforms the result, and writes
NetAsCode-compatible YAML to platform/netascode/aci/ for consumption
by the netascode/aci Terraform provider.

Usage
-----
    # From repo root:
    python platform/python/generate_aci.py --token <TOKEN>

    # Using environment variable:
    NAUTOBOT_TOKEN=<TOKEN> python platform/python/generate_aci.py

    # Dry-run (print YAML, do not write files):
    python platform/python/generate_aci.py --token <TOKEN> --dry-run

    # Include ACI system tenants (common/infra/mgmt) — useful in lab:
    python platform/python/generate_aci.py --token <TOKEN> --include-system-tenants
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

# Allow running as a plain script from anywhere in the repo tree
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from generator.client import NautobotClient
from generator.transformer import build_netascode_yaml

_DEFAULT_URL = "http://localhost:8080"
# Default output: platform/netascode/aci/ (sibling of platform/python/)
_DEFAULT_OUTPUT = _HERE.parent / "netascode" / "aci"


def main() -> None:
    args = _parse_args()

    token = args.token or os.environ.get("NAUTOBOT_TOKEN", "")
    if not token:
        print(
            "ERROR: Nautobot API token required. Use --token or set NAUTOBOT_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = NautobotClient(
        url=args.url,
        token=token,
        verify_ssl=not args.no_verify,
    )

    print(f"[generator] Querying Nautobot at {args.url}")
    tenants = client.get_tenants()
    prefixes = client.get_prefixes()
    print(f"[generator]   tenants={len(tenants)}  prefixes={len(prefixes)}")

    data = build_netascode_yaml(
        tenants=tenants,
        prefixes=prefixes,
        include_system_tenants=args.include_system_tenants,
    )

    exported = len(data.get("apic", {}).get("tenants", []))
    skipped = len(tenants) - exported
    print(
        f"[generator]   exporting {exported} tenant(s)"
        f"  (system tenants {'included' if args.include_system_tenants else f'excluded: {skipped} skipped'})"
    )

    if args.dry_run:
        print("[generator]   --dry-run: output below\n")
        print("---")
        yaml.dump(data, sys.stdout, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return

    args.output.mkdir(parents=True, exist_ok=True)
    out_file = args.output / "tenants.yaml"
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
        "--include-system-tenants",
        action="store_true",
        help="Include ACI system tenants (common/infra/mgmt) in output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print YAML to stdout without writing files",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
