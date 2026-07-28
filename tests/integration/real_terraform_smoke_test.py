#!/usr/bin/env python3
"""Real Terraform smoke test — Milestone 6A, Real Terraform Integration.

Proves the M6A checkpoint: RequestDeployment now drives an actual
`terraform init/plan/apply` against platform/terraform/aci/ and the live
APIC — not terraform_stub.py's simulated success. Covers both the success
path (independently verified against the live APIC, not just
GetDeploymentStatus) and the failure path (Vault stopped mid-test, mirroring
milestone2_smoke_test.py's existing OPA-unavailable pattern).

Usage:
    export NAUTOBOT_TOKEN=<nautobot-superuser-api-token>
    export VAULT_TOKEN=<vault-root-or-scoped-token>
    python3 tests/integration/real_terraform_smoke_test.py

Requires: the platform-api + opa stack already running
(lab/docker/platform-api), the vault stack running (lab/docker/vault), and
`docker compose` available on PATH to stop/start the vault container.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")

_VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://localhost:8200")
_VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "")

_VAULT_COMPOSE_DIR = Path(__file__).resolve().parents[2] / "docker" / "vault"
_KNOWLEDGE_LOG_PATH = Path(__file__).resolve().parents[2] / "docker" / "platform-api" / "data" / "knowledge" / "deployments.jsonl"
_AUDIT_LOG_PATH = Path(__file__).resolve().parents[2] / "docker" / "platform-api" / "data" / "policy_denials.jsonl"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def _domain_intent(tenant_name: str) -> dict:
    return {"apic": {"tenants": [{"name": tenant_name, "vrfs": [{"name": f"{tenant_name}-vrf"}], "bridge_domains": []}]}}


def _submit_and_deploy(tenant_name: str) -> tuple[dict, str]:
    submit_resp = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={"domain_id": "cisco_aci", "owner": "platform-engineering", "domain_intent": _domain_intent(tenant_name)},
        timeout=10.0,
    )
    if submit_resp.status_code != 201:
        fail(f"SubmitIntent returned {submit_resp.status_code}: {submit_resp.text}")
    intent = submit_resp.json()

    deploy_resp = httpx.post(
        f"{PLATFORM_API_URL}/deployments",
        json={
            "intent_id": intent["intent_id"],
            "engineering_version": intent["engineering_version"],
            "requester": "real-terraform-smoke-test",
            "entry_point": "cli",
        },
        timeout=10.0,
    )
    if deploy_resp.status_code != 201:
        fail(f"RequestDeployment returned {deploy_resp.status_code}: {deploy_resp.text}")
    return intent, deploy_resp.json()["deployment_context"]["deployment_id"]


def _poll_until(deployment_id: str, target_states: set[str], timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    final = None
    while time.monotonic() < deadline:
        resp = httpx.get(f"{PLATFORM_API_URL}/deployments/{deployment_id}", timeout=10.0)
        final = resp.json()
        if final["execution_state"]["lifecycle_state"] in target_states:
            return final
        time.sleep(0.5)
    fail(f"Deployment {deployment_id} did not reach {target_states} within {timeout}s; last observed: {final}")


def _apic_login_and_get_tenant(tenant_name: str) -> dict | None:
    """Independently verify against the live APIC — not GetDeploymentStatus, not Nautobot."""
    vault_resp = httpx.get(
        f"{_VAULT_ADDR.rstrip('/')}/v1/secret/data/lab/platform",
        headers={"X-Vault-Token": _VAULT_TOKEN},
        timeout=5.0,
    )
    vault_resp.raise_for_status()
    creds = vault_resp.json()["data"]["data"]
    verify_tls = str(creds.get("aci_insecure", "true")).lower() != "true"

    login = httpx.post(
        f"{creds['aci_url']}/api/aaaLogin.json",
        json={"aaaUser": {"attributes": {"name": creds["aci_username"], "pwd": creds["aci_password"]}}},
        verify=verify_tls,
        timeout=10.0,
    )
    login.raise_for_status()
    token = login.cookies.get("APIC-cookie")

    query = httpx.get(
        f"{creds['aci_url']}/api/class/fvTenant.json",
        params={"query-target-filter": f'eq(fvTenant.name,"{tenant_name}")'},
        cookies={"APIC-cookie": token},
        verify=verify_tls,
        timeout=10.0,
    )
    query.raise_for_status()
    results = query.json()["imdata"]
    return results[0]["fvTenant"] if results else None


def _knowledge_record_for(deployment_id: str) -> dict | None:
    if not _KNOWLEDGE_LOG_PATH.exists():
        return None
    for line in reversed(_KNOWLEDGE_LOG_PATH.read_text(encoding="utf-8").splitlines()):
        record = json.loads(line)
        if record["deployment_id"] == deployment_id:
            return record
    return None


def _wait_for_knowledge_record(deployment_id: str, timeout: float = 15.0) -> dict | None:
    """The Knowledge Capture call happens a few lines after the lifecycle_state

    a poller observes via GetDeploymentStatus is committed -- both run inside
    the same BackgroundTask, but a concurrent poll can see the terminal state
    microseconds before the capture call executes (the same race
    knowledge_capture_smoke_test.py already accounts for).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = _knowledge_record_for(deployment_id)
        if record is not None:
            return record
        time.sleep(0.3)
    return None


def _audit_line_count() -> int:
    if not _AUDIT_LOG_PATH.exists():
        return 0
    return sum(1 for _ in _AUDIT_LOG_PATH.open("r", encoding="utf-8"))


def main() -> None:
    if not _VAULT_TOKEN:
        fail("VAULT_TOKEN must be set to independently verify against the live APIC")

    # 1. Success path — real terraform init/plan/apply, verified against the live APIC.
    tenant_name = f"real-tf-test-{uuid.uuid4().hex[:8]}"
    intent, deployment_id = _submit_and_deploy(tenant_name)
    final = _poll_until(deployment_id, {"stable", "failed"}, timeout=90.0)
    if final["execution_state"]["lifecycle_state"] != "stable":
        fail(f"Expected STABLE for a clean deployment, got: {final['execution_state']}")
    print(f"PASS: deployment {deployment_id} reached STABLE (real terraform init/plan/apply)")

    apic_tenant = _apic_login_and_get_tenant(tenant_name)
    if apic_tenant is None:
        fail(f"Tenant {tenant_name!r} was not found in the live APIC -- Terraform did not actually provision it")
    if apic_tenant["attributes"]["annotation"] != "orchestrator:terraform":
        fail(f"Tenant {tenant_name!r} exists but was not created by Terraform: {apic_tenant}")
    print(f"PASS: tenant {tenant_name!r} independently confirmed in the live APIC (orchestrator:terraform)")

    record = _wait_for_knowledge_record(deployment_id)
    if record is None:
        fail(f"No Knowledge Capture record found for deployment {deployment_id}")
    if record["lifecycle_state"] != "stable":
        fail(f"Knowledge Capture record has unexpected lifecycle_state: {record}")
    print("PASS: Knowledge Capture recorded the real deployment")

    # 2. Failure path — Vault stopped mid-test (mirrors milestone2_smoke_test.py's OPA-unavailable pattern).
    lines_before = _audit_line_count()

    print("Stopping vault container...")
    subprocess.run(["docker", "compose", "stop", "vault"], cwd=_VAULT_COMPOSE_DIR, check=True, capture_output=True)
    time.sleep(1.0)

    try:
        fail_tenant_name = f"real-tf-fail-{uuid.uuid4().hex[:8]}"
        _, failing_deployment_id = _submit_and_deploy(fail_tenant_name)
        final_fail = _poll_until(failing_deployment_id, {"stable", "failed"}, timeout=90.0)
        if final_fail["execution_state"]["lifecycle_state"] != "failed":
            fail(f"Expected FAILED while Vault is unreachable, got: {final_fail['execution_state']}")
        print(f"PASS: deployment {failing_deployment_id} reached FAILED (Vault unreachable during terraform execution)")

        failed_record = _wait_for_knowledge_record(failing_deployment_id)
        if failed_record is None:
            fail(f"No Knowledge Capture record found for failed deployment {failing_deployment_id}")
        if failed_record["lifecycle_state"] != "failed":
            fail(f"Knowledge Capture record for the failed deployment has unexpected lifecycle_state: {failed_record}")
        print("PASS: Knowledge Capture recorded the FAILED deployment too")

        if _audit_line_count() != lines_before:
            fail("A Terraform execution failure incorrectly wrote an audit log entry -- it is not a Technical Policy denial")
        print("PASS: no audit log entry written for a Terraform execution failure (correctly distinct from a denial)")

        status_resp = httpx.get(f"{PLATFORM_API_URL}/deployments/{failing_deployment_id}", timeout=10.0)
        if status_resp.status_code != 200:
            fail(f"GetDeploymentStatus returned {status_resp.status_code} for the failed deployment: {status_resp.text}")
        print("PASS: failure is observable only via GetDeploymentStatus -- HTTP contract unchanged")
    finally:
        print("Restarting vault container...")
        subprocess.run(["docker", "compose", "start", "vault"], cwd=_VAULT_COMPOSE_DIR, check=True, capture_output=True)
        time.sleep(2.0)

    print("\nReal Terraform Integration (Milestone 6A) checkpoint: PASSED")


if __name__ == "__main__":
    main()
