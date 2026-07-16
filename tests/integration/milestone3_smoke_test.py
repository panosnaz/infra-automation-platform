#!/usr/bin/env python3
"""Milestone 3 smoke test — Vertical Slice v0.1, Deployment Lifecycle.

Proves the Milestone 3 checkpoint: SubmitIntent -> RequestDeployment ->
ACCEPTED -> DEPLOYING -> VALIDATING -> STABLE, with every transition
persisted in the Execution Store (not held in the Platform API process).

Usage:
    export NAUTOBOT_TOKEN=<nautobot-superuser-api-token>
    python3 tests/integration/milestone3_smoke_test.py

Requires: the platform-api + opa stack already running
(lab/docker/platform-api).
"""

from __future__ import annotations

import os
import sys
import time

import httpx

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main() -> None:
    # 1. SubmitIntent — reuse the same known-good web-tenant payload M1/M2 use.
    submit_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={
            "domain_id": "cisco_aci",
            "owner": "platform-engineering",
            "domain_intent": {"apic": {"tenants": [{"name": "web-tenant", "vrfs": [], "bridge_domains": []}]}},
        },
        timeout=10.0,
    )
    if submit_resp.status_code != 201:
        fail(f"SubmitIntent returned {submit_resp.status_code}: {submit_resp.text}")
    intent = submit_resp.json()
    print(f"PASS: SubmitIntent -> 201, intent_id={intent['intent_id']}")

    # 2. RequestDeployment — must return immediately at ACCEPTED (Contract #2 §3),
    #    not wait for the full lifecycle to complete.
    deploy_resp = httpx.post(
        f"{PLATFORM_API_URL}/deployments",
        json={
            "intent_id": intent["intent_id"],
            "engineering_version": intent["engineering_version"],
            "requester": "milestone3-smoke-test",
            "entry_point": "cli",
        },
        timeout=10.0,
    )
    if deploy_resp.status_code != 201:
        fail(f"RequestDeployment returned {deploy_resp.status_code}: {deploy_resp.text}")
    deployment = deploy_resp.json()
    deployment_id = deployment["deployment_context"]["deployment_id"]
    if deployment["execution_state"]["lifecycle_state"] != "accepted":
        fail(f"Expected RequestDeployment to return ACCEPTED, got: {deployment['execution_state']['lifecycle_state']}")
    print(f"PASS: RequestDeployment -> 201, ACCEPTED, deployment_id={deployment_id} (returned before DEPLOYING/VALIDATING/STABLE)")

    # 3. Poll GetDeployment until STABLE (the background pipeline runs after
    #    the response above was already sent — this is the asynchronous part).
    #    Milestone 6A: real Terraform init/plan/apply against the live APIC
    #    takes real time (observed ~15-20s), unlike the near-instant stub this
    #    timeout was originally written for.
    deadline = time.monotonic() + 90.0
    final_state = None
    while time.monotonic() < deadline:
        status_resp = httpx.get(f"{PLATFORM_API_URL}/deployments/{deployment_id}", timeout=10.0)
        if status_resp.status_code != 200:
            fail(f"GetDeployment returned {status_resp.status_code}: {status_resp.text}")
        final_state = status_resp.json()["execution_state"]
        if final_state["lifecycle_state"] == "stable":
            break
        time.sleep(0.2)
    else:
        fail(f"Deployment did not reach STABLE within 90s; last observed state: {final_state}")

    print("PASS: deployment reached STABLE via GetDeployment (polled, not held in Platform API memory)")

    # 4. Verify every field the lifecycle is supposed to have set along the way.
    if final_state["desired_version"] != intent["engineering_version"]:
        fail(f"desired_version mismatch: {final_state}")
    if final_state["applied_version"] != intent["engineering_version"]:
        fail(f"applied_version did not converge to desired_version: {final_state}")
    if final_state["deployed_at"] is None:
        fail("deployed_at was never set (Terraform stub did not run)")
    if final_state["validated_at"] is None:
        fail("validated_at was never set (Validation stub did not run)")
    print("PASS: desired_version == applied_version, deployed_at and validated_at both set")

    # 5. Missing deployment_id -> 404.
    missing_resp = httpx.get(f"{PLATFORM_API_URL}/deployments/00000000-0000-0000-0000-000000000000", timeout=10.0)
    if missing_resp.status_code != 404:
        fail(f"Expected 404 for unknown deployment_id, got {missing_resp.status_code}")
    print("PASS: unknown deployment_id correctly returns 404")

    print("\nMilestone 3 checkpoint: PASSED")


if __name__ == "__main__":
    main()
