#!/usr/bin/env python3
"""Business Approval smoke test — ADR-015, PENDING_APPROVAL / ApproveDeployment / DenyDeployment.

Proves: production requires approval (rests at PENDING_APPROVAL, 202);
approving resumes the pipeline through to STABLE; denying reaches FAILED
without ever running the pipeline; acting on an already-resolved deployment
is a 409 no-op error, not silently accepted; lab environment is unaffected
(regression against Milestone 3's existing immediate-ACCEPTED behavior).

Usage:
    export NAUTOBOT_TOKEN=<nautobot-superuser-api-token>
    python3 tests/integration/business_approval_smoke_test.py
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


def _submit_intent() -> dict:
    resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={
            "domain_id": "cisco_aci",
            "owner": "platform-engineering",
            "domain_intent": {"apic": {"tenants": [{"name": "web-tenant", "vrfs": [], "bridge_domains": []}]}},
        },
        timeout=10.0,
    )
    if resp.status_code != 201:
        fail(f"SubmitIntent returned {resp.status_code}: {resp.text}")
    return resp.json()


def _request_deployment(intent: dict, environment: str) -> dict:
    resp = httpx.post(
        f"{PLATFORM_API_URL}/deployments",
        json={
            "intent_id": intent["intent_id"],
            "engineering_version": intent["engineering_version"],
            "requester": "business-approval-smoke-test",
            "entry_point": "cli",
            "environment": environment,
        },
        timeout=10.0,
    )
    return resp


def main() -> None:
    # 1. Production requires approval -> 202, PENDING_APPROVAL.
    intent = _submit_intent()
    resp = _request_deployment(intent, "production")
    if resp.status_code != 202:
        fail(f"Expected 202 for production RequestDeployment, got {resp.status_code}: {resp.text}")
    deployment = resp.json()
    deployment_id = deployment["deployment_context"]["deployment_id"]
    if deployment["execution_state"]["lifecycle_state"] != "pending_approval":
        fail(f"Expected PENDING_APPROVAL, got: {deployment['execution_state']['lifecycle_state']}")
    print(f"PASS: production RequestDeployment -> 202, PENDING_APPROVAL, deployment_id={deployment_id}")

    # 2. Approve -> ACCEPTED, then pipeline resumes to STABLE.
    approve_resp = httpx.post(
        f"{PLATFORM_API_URL}/deployments/{deployment_id}/approve", json={"approved_by": "platform-admin"}, timeout=10.0
    )
    if approve_resp.status_code != 200:
        fail(f"ApproveDeployment returned {approve_resp.status_code}: {approve_resp.text}")
    if approve_resp.json()["execution_state"]["lifecycle_state"] != "accepted":
        fail(f"Expected ACCEPTED immediately after approval, got: {approve_resp.json()['execution_state']}")
    print("PASS: ApproveDeployment -> 200, ACCEPTED")

    deadline = time.monotonic() + 10.0
    final_state = None
    while time.monotonic() < deadline:
        status_resp = httpx.get(f"{PLATFORM_API_URL}/deployments/{deployment_id}", timeout=10.0)
        final_state = status_resp.json()["execution_state"]
        if final_state["lifecycle_state"] == "stable":
            break
        time.sleep(0.2)
    else:
        fail(f"Approved deployment did not reach STABLE within 10s; last state: {final_state}")
    if final_state["applied_version"] != intent["engineering_version"]:
        fail(f"applied_version did not converge after approval: {final_state}")
    print("PASS: approved deployment's pipeline resumed and reached STABLE")

    # 3. Re-approving an already-resolved deployment is a 409, not a silent no-op.
    reapprove_resp = httpx.post(
        f"{PLATFORM_API_URL}/deployments/{deployment_id}/approve", json={"approved_by": "someone-else"}, timeout=10.0
    )
    if reapprove_resp.status_code != 409:
        fail(f"Expected 409 for re-approving a resolved deployment, got {reapprove_resp.status_code}")
    print("PASS: re-approving an already-ACCEPTED deployment correctly returns 409")

    # 4. Deny path -> FAILED, pipeline never runs.
    intent2 = _submit_intent()
    deny_setup_resp = _request_deployment(intent2, "production")
    deny_deployment_id = deny_setup_resp.json()["deployment_context"]["deployment_id"]

    deny_resp = httpx.post(
        f"{PLATFORM_API_URL}/deployments/{deny_deployment_id}/deny", json={"approved_by": "platform-admin"}, timeout=10.0
    )
    if deny_resp.status_code != 200:
        fail(f"DenyDeployment returned {deny_resp.status_code}: {deny_resp.text}")
    if deny_resp.json()["execution_state"]["lifecycle_state"] != "failed":
        fail(f"Expected FAILED after denial, got: {deny_resp.json()['execution_state']}")
    print("PASS: DenyDeployment -> 200, FAILED")

    time.sleep(1.0)  # give a hypothetical (incorrect) pipeline a chance to have run, if it wrongly did
    final_denied_state = httpx.get(f"{PLATFORM_API_URL}/deployments/{deny_deployment_id}", timeout=10.0).json()["execution_state"]
    if final_denied_state["lifecycle_state"] != "failed":
        fail(f"Denied deployment's state changed after denial -- pipeline must not have run: {final_denied_state}")
    if final_denied_state["deployed_at"] is not None:
        fail("Denied deployment has deployed_at set -- the pipeline incorrectly ran after a denial")
    print("PASS: denied deployment stays FAILED, pipeline never ran (deployed_at still null)")

    # 5. Lab environment unaffected -- still immediate ACCEPTED (Milestone 3 regression).
    lab_resp = _request_deployment(intent2, "lab")
    if lab_resp.status_code != 201:
        fail(f"Expected 201 for lab RequestDeployment, got {lab_resp.status_code}: {lab_resp.text}")
    if lab_resp.json()["execution_state"]["lifecycle_state"] != "accepted":
        fail(f"Expected immediate ACCEPTED for lab, got: {lab_resp.json()['execution_state']}")
    print("PASS: lab environment still reaches ACCEPTED immediately, unaffected by Business Approval")

    print("\nBusiness Approval checkpoint: PASSED")


if __name__ == "__main__":
    main()
