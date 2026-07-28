#!/usr/bin/env python3
"""Execution Framework -- Stage 3 (Policy).

Calls OPA directly from GitLab CI, replacing the Phase 1-era in-process
TechnicalPolicyClient call pattern (see ADR-017's Consequences and ADR-014's
fail-closed principle). An unreachable OPA is treated as a denial, never a
silent pass.

Usage:
    export OPA_URL=http://localhost:8181   # optional, this is the default
    python3 policy_check.py <path-to-tenants.yaml> <domain_id>

<domain_id> must match an existing OPA package, e.g. "cisco_aci" for
policy/cisco_aci/*.rego (queried as data.platform.cisco_aci.decision).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

import yaml

OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: policy_check.py <path-to-tenants.yaml> <domain_id>", file=sys.stderr)
        return 2

    path, domain_id = sys.argv[1], sys.argv[2]
    with open(path, encoding="utf-8") as f:
        domain_intent = yaml.safe_load(f)

    body = json.dumps({"input": {"domain_intent": domain_intent}}).encode("utf-8")
    url = f"{OPA_URL.rstrip('/')}/v1/data/platform/{domain_id}/decision"
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            result = json.load(resp)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Fail closed: an unreachable OPA is a denial, per ADR-014.
        print(f"FAIL (fail-closed): could not reach OPA at {url}: {exc}", file=sys.stderr)
        return 1

    decision = result.get("result", {})
    if not decision.get("allow"):
        reasons = decision.get("reasons") or ["no reason returned"]
        print(f"DENIED by policy '{domain_id}': {'; '.join(reasons)}", file=sys.stderr)
        return 1

    print(f"ALLOWED by policy '{domain_id}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
