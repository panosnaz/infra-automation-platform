#!/usr/bin/env python3
"""Milestone 1 smoke test — Vertical Slice v0.1, Intent Lifecycle only.

Proves the Milestone 1 checkpoint from
docs/05-Operations/14-Vertical-Slice-v0.1-Roadmap.md: SubmitIntent persists
a CanonicalIntent to Nautobot, and GetIntent reads it back from Nautobot —
not from the Platform API process's own memory. The Platform API container
is restarted mid-test to prove this.

Deliberately a plain script, not a pytest suite: this is a single ordered
sequence against live infrastructure (Platform API + Nautobot), not a set of
independent unit cases — a test runner framework would add nothing here.

Usage:
    export NAUTOBOT_TOKEN=<nautobot-superuser-api-token>
    python3 tests/integration/milestone1_smoke_test.py

Requires: the platform-api and nautobot lab stacks already running
(lab/docker/platform-api, lab/docker/nautobot), and `docker compose`
available on PATH to restart the platform-api container mid-test.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")
NAUTOBOT_URL = os.environ.get("NAUTOBOT_URL", "http://localhost:8080")
NAUTOBOT_TOKEN = os.environ.get("NAUTOBOT_TOKEN")

_PLATFORM_API_COMPOSE_DIR = Path(__file__).resolve().parents[2] / "lab" / "docker" / "platform-api"

_WEB_TENANT_DOMAIN_INTENT = {
    "apic": {
        "tenants": [
            {
                "name": "web-tenant",
                "description": "Platform Engineering vertical slice - web application tenant",
                "vrfs": [{"name": "web-vrf", "description": "Web tenant VRF"}],
                "bridge_domains": [
                    {
                        "name": "web-bd",
                        "unicast_routing": True,
                        "subnets": [{"ip": "10.10.10.1/24", "public": False, "private": True, "shared": False}],
                        "vrf": "web-vrf",
                    }
                ],
            }
        ]
    }
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def wait_for_health(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{PLATFORM_API_URL}/health", timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    fail(f"Platform API did not become healthy within {timeout}s of restart")


def main() -> None:
    if not NAUTOBOT_TOKEN:
        fail("NAUTOBOT_TOKEN is not set")

    # 1. SubmitIntent
    submit_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={
            "domain_id": "cisco_aci",
            "owner": "platform-engineering",
            "tags": {"environment-class": "lab"},
            "domain_intent": _WEB_TENANT_DOMAIN_INTENT,
        },
        timeout=10.0,
    )
    if submit_resp.status_code != 201:
        fail(f"SubmitIntent returned {submit_resp.status_code}: {submit_resp.text}")
    intent = submit_resp.json()
    intent_id = intent["intent_id"]
    print(f"PASS: SubmitIntent -> 201, intent_id={intent_id}")

    # 2. Confirm it actually landed in Nautobot, independent of the Platform API.
    tenant_resp = httpx.get(
        f"{NAUTOBOT_URL}/api/tenancy/tenants/",
        params={"name": "ACI:web-tenant"},
        headers={"Authorization": f"Token {NAUTOBOT_TOKEN}"},
        timeout=10.0,
    )
    tenant_resp.raise_for_status()
    results = tenant_resp.json()["results"]
    if not results or (results[0].get("custom_fields") or {}).get("canonical_intent", {}).get("intent_id") != intent_id:
        fail("CanonicalIntent was not found in Nautobot's Tenant.canonical_intent custom field")
    print("PASS: CanonicalIntent confirmed persisted in Nautobot (read independently of the Platform API)")

    # 3. Restart the Platform API container — proves GetIntent cannot be
    #    served from in-process memory.
    print("Restarting platform-api container...")
    subprocess.run(
        ["docker", "compose", "restart", "platform-api"],
        cwd=_PLATFORM_API_COMPOSE_DIR,
        check=True,
        capture_output=True,
    )
    wait_for_health()
    print("PASS: platform-api restarted and healthy")

    # 4. GetIntent after restart.
    get_resp = httpx.get(f"{PLATFORM_API_URL}/intents/{intent_id}/1", timeout=10.0)
    if get_resp.status_code != 200 or get_resp.json()["intent_id"] != intent_id:
        fail(f"GetIntent after restart returned {get_resp.status_code}: {get_resp.text}")
    print("PASS: GetIntent after restart returned the same CanonicalIntent, read from Nautobot")

    # 5. Error paths.
    bad_domain_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={"domain_id": "azure_networking", "owner": "x", "domain_intent": {}},
        timeout=10.0,
    )
    if bad_domain_resp.status_code != 422:
        fail(f"Expected 422 for unknown domain_id, got {bad_domain_resp.status_code}: {bad_domain_resp.text}")
    print("PASS: unknown domain_id correctly rejected with 422")

    missing_resp = httpx.get(f"{PLATFORM_API_URL}/intents/00000000-0000-0000-0000-000000000000/1", timeout=10.0)
    if missing_resp.status_code != 404:
        fail(f"Expected 404 for unknown intent_id, got {missing_resp.status_code}")
    print("PASS: unknown intent_id correctly returns 404")

    print("\nMilestone 1 checkpoint: PASSED")


if __name__ == "__main__":
    main()
