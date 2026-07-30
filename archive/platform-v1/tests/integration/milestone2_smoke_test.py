#!/usr/bin/env python3
"""Milestone 2 smoke test — Vertical Slice v0.1, Technical Policy.

Proves the Milestone 2 checkpoint: SubmitIntent evaluates a real OPA sidecar
before persisting to Nautobot. Covers allow, deny (with audit record), and
fail-closed (OPA stopped mid-test) — the three failure/success paths ADR-014
Appendix A specifies.

Usage:
    export NAUTOBOT_TOKEN=<nautobot-superuser-api-token>
    python3 tests/integration/milestone2_smoke_test.py

Requires: the platform-api + opa stack already running
(lab/docker/platform-api), and `docker compose` available on PATH to stop/
start the opa container mid-test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")

_COMPOSE_DIR = Path(__file__).resolve().parents[2] / "docker" / "platform-api"
_AUDIT_LOG_PATH = _COMPOSE_DIR / "data" / "policy_denials.jsonl"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def _domain_intent(tenant_name: str) -> dict:
    return {"apic": {"tenants": [{"name": tenant_name, "vrfs": [], "bridge_domains": []}]}}


def _audit_line_count() -> int:
    if not _AUDIT_LOG_PATH.exists():
        return 0
    return sum(1 for _ in _AUDIT_LOG_PATH.open("r", encoding="utf-8"))


def main() -> None:
    # 1. Allow path — regression-equivalent to Milestone 1's existing tenant.
    allow_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={"domain_id": "cisco_aci", "owner": "platform-engineering", "domain_intent": _domain_intent("web-tenant")},
        timeout=10.0,
    )
    if allow_resp.status_code != 201:
        fail(f"Expected 201 for a compliant tenant name, got {allow_resp.status_code}: {allow_resp.text}")
    print("PASS: compliant tenant name -> 201 (Technical Policy allowed, persisted to Nautobot)")

    # 2. Deny path — non-compliant tenant name.
    lines_before = _audit_line_count()
    deny_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={"domain_id": "cisco_aci", "owner": "platform-engineering", "domain_intent": _domain_intent("Bad_Name")},
        timeout=10.0,
    )
    if deny_resp.status_code != 422:
        fail(f"Expected 422 for a non-compliant tenant name, got {deny_resp.status_code}: {deny_resp.text}")
    body = deny_resp.json()
    if body.get("detail", {}).get("error_code") != "TECHNICAL_POLICY_DENIED":
        fail(f"Expected error_code TECHNICAL_POLICY_DENIED, got: {body}")
    print("PASS: non-compliant tenant name -> 422 TECHNICAL_POLICY_DENIED")

    lines_after = _audit_line_count()
    if lines_after != lines_before + 1:
        fail(f"Expected exactly one new audit record for the denial, went from {lines_before} to {lines_after} lines")
    last_line = json.loads(_AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])
    if "Bad_Name" not in last_line["reasons"][0]:
        fail(f"Audit record does not reference the denied tenant name: {last_line}")
    print("PASS: exactly one durable audit record written for the denial")

    # 3. Fail-closed path — stop OPA, confirm 502 and no new audit record.
    print("Stopping opa container...")
    subprocess.run(["docker", "compose", "stop", "opa"], cwd=_COMPOSE_DIR, check=True, capture_output=True)
    time.sleep(1.0)

    lines_before_unavailable = _audit_line_count()
    unavailable_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={"domain_id": "cisco_aci", "owner": "platform-engineering", "domain_intent": _domain_intent("web-tenant")},
        timeout=10.0,
    )
    if unavailable_resp.status_code != 502:
        fail(f"Expected 502 while OPA is down, got {unavailable_resp.status_code}: {unavailable_resp.text}")
    if unavailable_resp.json().get("detail", {}).get("error_code") != "TECHNICAL_POLICY_UNAVAILABLE":
        fail(f"Expected error_code TECHNICAL_POLICY_UNAVAILABLE, got: {unavailable_resp.json()}")
    print("PASS: OPA unreachable -> 502 TECHNICAL_POLICY_UNAVAILABLE (fail closed)")

    if _audit_line_count() != lines_before_unavailable:
        fail("An audit record was written for an UNAVAILABLE decision — it must only be written for an actual denial")
    print("PASS: no audit record written for an unavailable decision (correctly distinct from a denial)")

    print("Restarting opa container...")
    subprocess.run(["docker", "compose", "start", "opa"], cwd=_COMPOSE_DIR, check=True, capture_output=True)
    time.sleep(2.0)

    print("\nMilestone 2 checkpoint: PASSED")


if __name__ == "__main__":
    main()
