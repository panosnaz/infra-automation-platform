#!/usr/bin/env python3
"""Knowledge Capture smoke test — Vertical Slice v0.1, Milestone 5.

Proves the M5 checkpoint: on reaching STABLE (or FAILED), a durable JSONL
record is appended containing CanonicalIntent + DeploymentContext +
ExecutionState, and that record's content matches what Nautobot and SQLite
independently hold — i.e. Knowledge Capture is a read-only reflection of the
other two stores (Contract #3 §5), not a fourth independent source of truth.

Usage:
    export NAUTOBOT_TOKEN=<nautobot-superuser-api-token>
    python3 tests/integration/knowledge_capture_smoke_test.py

Requires: the platform-api + opa stack already running
(lab/docker/platform-api).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")

_COMPOSE_DIR = Path(__file__).resolve().parents[2] / "lab" / "docker" / "platform-api"
_KNOWLEDGE_LOG_PATH = _COMPOSE_DIR / "data" / "knowledge" / "deployments.jsonl"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def _knowledge_line_count() -> int:
    if not _KNOWLEDGE_LOG_PATH.exists():
        return 0
    return sum(1 for _ in _KNOWLEDGE_LOG_PATH.open("r", encoding="utf-8"))


def _last_knowledge_record() -> dict:
    return json.loads(_KNOWLEDGE_LOG_PATH.read_text(encoding="utf-8").splitlines()[-1])


def main() -> None:
    # 1. STABLE path — submit an intent, deploy it to STABLE (lab, no approval).
    lines_before = _knowledge_line_count()

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

    deploy_resp = httpx.post(
        f"{PLATFORM_API_URL}/deployments",
        json={
            "intent_id": intent["intent_id"],
            "engineering_version": intent["engineering_version"],
            "requester": "knowledge-capture-smoke-test",
            "entry_point": "cli",
        },
        timeout=10.0,
    )
    if deploy_resp.status_code != 201:
        fail(f"RequestDeployment returned {deploy_resp.status_code}: {deploy_resp.text}")
    deployment = deploy_resp.json()
    deployment_id = deployment["deployment_context"]["deployment_id"]
    correlation_id = deployment["deployment_context"]["correlation_id"]

    deadline = time.monotonic() + 10.0
    final = None
    while time.monotonic() < deadline:
        status_resp = httpx.get(f"{PLATFORM_API_URL}/deployments/{deployment_id}", timeout=10.0)
        final = status_resp.json()
        if final["execution_state"]["lifecycle_state"] == "stable":
            break
        time.sleep(0.2)
    else:
        fail(f"Deployment did not reach STABLE within 10s; last observed: {final}")
    print(f"PASS: deployment {deployment_id} reached STABLE")

    # Give the BackgroundTask a moment to run after STABLE was persisted.
    deadline = time.monotonic() + 5.0
    while _knowledge_line_count() == lines_before and time.monotonic() < deadline:
        time.sleep(0.2)

    lines_after = _knowledge_line_count()
    if lines_after != lines_before + 1:
        fail(f"Expected exactly one new knowledge record, went from {lines_before} to {lines_after} lines")
    record = _last_knowledge_record()
    print("PASS: exactly one new knowledge capture record written for the STABLE deployment")

    # 2. Record content matches Nautobot (CanonicalIntent) and SQLite (DeploymentContext/ExecutionState).
    if record["deployment_id"] != deployment_id:
        fail(f"Record deployment_id mismatch: {record['deployment_id']} != {deployment_id}")
    if record["lifecycle_state"] != "stable":
        fail(f"Record lifecycle_state mismatch: {record['lifecycle_state']}")
    if record["canonical_intent"]["intent_id"] != intent["intent_id"]:
        fail(f"Record canonical_intent does not match Nautobot's: {record['canonical_intent']}")
    if record["canonical_intent"]["engineering_version"] != intent["engineering_version"]:
        fail("Record canonical_intent.engineering_version does not match Nautobot's")
    if record["deployment_context"]["deployment_id"] != deployment_id:
        fail("Record deployment_context does not match SQLite's DeploymentContext")
    if record["deployment_context"]["correlation_id"] != correlation_id:
        fail("Record deployment_context.correlation_id does not match SQLite's DeploymentContext")
    if record["execution_state"]["lifecycle_state"] != final["execution_state"]["lifecycle_state"]:
        fail("Record execution_state does not match SQLite's ExecutionState")
    if record["execution_state"]["applied_version"] != final["execution_state"]["applied_version"]:
        fail("Record execution_state.applied_version does not match SQLite's ExecutionState")
    print("PASS: knowledge record's CanonicalIntent/DeploymentContext/ExecutionState match Nautobot and SQLite exactly")

    # 3. FAILED path — a denied production deployment is captured too.
    lines_before_denied = _knowledge_line_count()

    submit_resp2 = httpx.post(
        f"{PLATFORM_API_URL}/intents",
        json={
            "domain_id": "cisco_aci",
            "owner": "platform-engineering",
            "domain_intent": {"apic": {"tenants": [{"name": "web-tenant", "vrfs": [], "bridge_domains": []}]}},
        },
        timeout=10.0,
    )
    intent2 = submit_resp2.json()
    deploy_resp2 = httpx.post(
        f"{PLATFORM_API_URL}/deployments",
        json={
            "intent_id": intent2["intent_id"],
            "engineering_version": intent2["engineering_version"],
            "requester": "knowledge-capture-smoke-test",
            "entry_point": "cli",
            "environment": "production",
        },
        timeout=10.0,
    )
    deny_deployment_id = deploy_resp2.json()["deployment_context"]["deployment_id"]

    deny_resp = httpx.post(
        f"{PLATFORM_API_URL}/deployments/{deny_deployment_id}/deny", json={"approved_by": "platform-admin"}, timeout=10.0
    )
    if deny_resp.status_code != 200:
        fail(f"DenyDeployment returned {deny_resp.status_code}: {deny_resp.text}")

    lines_after_denied = _knowledge_line_count()
    if lines_after_denied != lines_before_denied + 1:
        fail(f"Expected exactly one new knowledge record for the denied deployment, went from {lines_before_denied} to {lines_after_denied} lines")
    denied_record = _last_knowledge_record()
    if denied_record["lifecycle_state"] != "failed":
        fail(f"Expected the captured record's lifecycle_state to be failed, got: {denied_record['lifecycle_state']}")
    if denied_record["deployment_id"] != deny_deployment_id:
        fail(f"Denied record deployment_id mismatch: {denied_record['deployment_id']} != {deny_deployment_id}")
    print("PASS: denied (FAILED) deployment is also captured, with lifecycle_state=failed")

    print("\nKnowledge Capture (Milestone 5) checkpoint: PASSED")


if __name__ == "__main__":
    main()
