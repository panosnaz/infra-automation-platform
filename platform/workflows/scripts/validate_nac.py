#!/usr/bin/env python3
"""Execution Framework -- Stage 2 (Validation), schema/determinism half.

Confirms a NetAsCode YAML file is well-formed before it enters the pipeline.
Does not touch Nautobot or OPA -- referential validation against live
Nautobot and Policy evaluation are separate, later stages (see
knowledge/architecture/Execution-Framework.md §2.2).

Usage:
    python3 validate_nac.py <path-to-tenants.yaml>
"""
from __future__ import annotations

import sys

import yaml


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_nac.py <path-to-tenants.yaml>", file=sys.stderr)
        return 2

    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "apic" not in data:
        print(f"FAIL: {path} is missing the top-level 'apic' key", file=sys.stderr)
        return 1

    tenants = data["apic"].get("tenants")
    if not tenants:
        print(f"FAIL: {path} has no tenants under 'apic.tenants'", file=sys.stderr)
        return 1

    for tenant in tenants:
        if "name" not in tenant:
            print(f"FAIL: a tenant entry is missing 'name': {tenant}", file=sys.stderr)
            return 1

    names = ", ".join(t["name"] for t in tenants)
    print(f"OK: {path} is well-formed -- {len(tenants)} tenant(s) found: {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
