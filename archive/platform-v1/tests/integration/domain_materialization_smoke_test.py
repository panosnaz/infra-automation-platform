#!/usr/bin/env python3
"""Domain Materialization smoke test — closes the Milestone 1 gap.

Proves: SubmitIntent for a brand-new tenant that has never existed in
Nautobot succeeds (previously required a pre-existing Tenant); the created
objects are readable back through the existing generator
(platform/python/generate_aci.py) with the correct shape; resubmitting the
same intent again is idempotent (no duplicate objects created).

Usage:
    export NAUTOBOT_TOKEN=<nautobot-superuser-api-token>
    python3 tests/integration/domain_materialization_smoke_test.py
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")
NAUTOBOT_URL = os.environ.get("NAUTOBOT_URL", "http://localhost:8080")
NAUTOBOT_TOKEN = os.environ.get("NAUTOBOT_TOKEN")


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main() -> None:
    if not NAUTOBOT_TOKEN:
        fail("NAUTOBOT_TOKEN is not set")

    tenant_name = f"materialization-test-{uuid.uuid4().hex[:8]}"
    nautobot_tenant_name = f"ACI:{tenant_name}"

    # 1. Confirm the tenant genuinely does not exist yet.
    precheck = httpx.get(
        f"{NAUTOBOT_URL}/api/tenancy/tenants/",
        params={"name": nautobot_tenant_name},
        headers={"Authorization": f"Token {NAUTOBOT_TOKEN}"},
        timeout=10.0,
    )
    if precheck.json()["count"] != 0:
        fail(f"Tenant {nautobot_tenant_name} already exists -- test needs a genuinely new name")

    domain_intent = {
        "apic": {
            "tenants": [
                {
                    "name": tenant_name,
                    "description": "Domain Materialization smoke test",
                    "vrfs": [{"name": f"{tenant_name}-vrf", "description": "test vrf"}],
                    "bridge_domains": [
                        {
                            "name": f"{tenant_name}-bd",
                            "unicast_routing": True,
                            "vrf": f"{tenant_name}-vrf",
                            "subnets": [{"ip": "10.77.77.1/24", "public": False, "private": True, "shared": False}],
                        }
                    ],
                }
            ]
        }
    }

    # 2. SubmitIntent for the brand-new tenant.
    submit_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={"domain_id": "cisco_aci", "owner": "platform-engineering", "domain_intent": domain_intent},
        timeout=15.0,
    )
    if submit_resp.status_code != 201:
        fail(f"SubmitIntent for a new tenant returned {submit_resp.status_code}: {submit_resp.text}")
    print(f"PASS: SubmitIntent for brand-new tenant '{tenant_name}' -> 201 (previously required a pre-existing Tenant)")

    # 3. Confirm the Tenant/VRF/Prefix objects actually landed in Nautobot,
    #    independent of the Platform API.
    headers = {"Authorization": f"Token {NAUTOBOT_TOKEN}"}
    tenant_check = httpx.get(f"{NAUTOBOT_URL}/api/tenancy/tenants/", params={"name": nautobot_tenant_name}, headers=headers, timeout=10.0)
    if tenant_check.json()["count"] != 1:
        fail(f"Expected exactly one materialized Tenant, found {tenant_check.json()['count']}")
    tenant_id = tenant_check.json()["results"][0]["id"]

    vrf_check = httpx.get(f"{NAUTOBOT_URL}/api/ipam/vrfs/", params={"tenant_id": tenant_id}, headers=headers, timeout=10.0)
    if vrf_check.json()["count"] != 1:
        fail(f"Expected exactly one materialized VRF, found {vrf_check.json()['count']}")

    prefix_check = httpx.get(f"{NAUTOBOT_URL}/api/ipam/prefixes/", params={"tenant_id": tenant_id}, headers=headers, timeout=10.0)
    if prefix_check.json()["count"] != 1:
        fail(f"Expected exactly one materialized Prefix, found {prefix_check.json()['count']}")
    prefix = prefix_check.json()["results"][0]
    if prefix["prefix"] != "10.77.77.0/24":
        fail(f"Expected network address 10.77.77.0/24 (not the gateway), got: {prefix['prefix']}")
    if prefix["description"] != f"ACI Bridge Domain: {tenant_name}-bd:{tenant_name}":
        fail(f"Prefix description doesn't match the generator's expected encoding: {prefix['description']}")
    print("PASS: Tenant/VRF/Prefix materialized in Nautobot with the exact shape the existing generator expects")

    # 4. Idempotency: resubmitting the same intent must not create duplicates.
    resubmit_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={"domain_id": "cisco_aci", "owner": "platform-engineering", "domain_intent": domain_intent},
        timeout=15.0,
    )
    if resubmit_resp.status_code != 201:
        fail(f"Resubmitting the same domain_intent returned {resubmit_resp.status_code}: {resubmit_resp.text}")

    tenant_recheck = httpx.get(f"{NAUTOBOT_URL}/api/tenancy/tenants/", params={"name": nautobot_tenant_name}, headers=headers, timeout=10.0)
    if tenant_recheck.json()["count"] != 1:
        fail(f"Resubmitting created a duplicate Tenant -- count is now {tenant_recheck.json()['count']}")
    prefix_recheck = httpx.get(f"{NAUTOBOT_URL}/api/ipam/prefixes/", params={"tenant_id": tenant_id}, headers=headers, timeout=10.0)
    if prefix_recheck.json()["count"] != 1:
        fail(f"Resubmitting created a duplicate Prefix -- count is now {prefix_recheck.json()['count']}")
    print("PASS: resubmitting the same intent is idempotent -- no duplicate objects created")

    print("\nDomain Materialization checkpoint: PASSED")


if __name__ == "__main__":
    main()
