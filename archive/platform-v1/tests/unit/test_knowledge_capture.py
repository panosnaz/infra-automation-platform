"""Unit tests for Knowledge Capture — no Docker required.

Uses a minimal fake intent store (satisfying only `.get()`) instead of a
real NautobotIntentStore, matching the zero-Docker discipline of the rest
of tests/unit/.
"""

from __future__ import annotations

import json
import uuid

from app.execution_store import ExecutionStore
from app.knowledge_capture import capture_deployment_outcome
from canonical_intent import ApprovalState, CanonicalIntent, DeploymentContext, Environment, ExecutionState, LifecycleState


class _FakeIntentStore:
    def __init__(self, intent: CanonicalIntent) -> None:
        self._intent = intent

    def get(self, intent_id: str, engineering_version: int) -> CanonicalIntent:
        assert intent_id == str(self._intent.intent_id)
        assert engineering_version == self._intent.engineering_version
        return self._intent


def _new_deployment(store: ExecutionStore, intent: CanonicalIntent) -> uuid.UUID:
    context = DeploymentContext(
        intent_id=intent.intent_id,
        engineering_version=intent.engineering_version,
        requester="tester",
        entry_point="cli",
        environment=Environment.LAB,
        approval_state=ApprovalState.NONE_REQUIRED,
    )
    state = ExecutionState(deployment_id=context.deployment_id, lifecycle_state=LifecycleState.ACCEPTED, desired_version=intent.engineering_version)
    store.create(context, state)
    return context.deployment_id


def test_capture_writes_one_line_with_intent_context_and_state(tmp_path) -> None:
    intent = CanonicalIntent(
        engineering_version=1,
        domain_id="cisco_aci",
        owner="platform-engineering",
        domain_intent={"apic": {"tenants": [{"name": "web-tenant", "vrfs": [], "bridge_domains": []}]}},
    )
    execution_store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(execution_store, intent)
    execution_store.transition(deployment_id, LifecycleState.DEPLOYING)
    execution_store.transition(deployment_id, LifecycleState.VALIDATING)
    execution_store.transition(deployment_id, LifecycleState.STABLE, applied_version=intent.engineering_version)

    knowledge_path = tmp_path / "knowledge" / "deployments.jsonl"
    intent_store = _FakeIntentStore(intent)
    import app.knowledge_capture as kc_module

    kc_module.KNOWLEDGE_CAPTURE_PATH = knowledge_path

    capture_deployment_outcome(intent_store, execution_store, deployment_id)

    lines = knowledge_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["deployment_id"] == str(deployment_id)
    assert record["lifecycle_state"] == "stable"
    assert record["canonical_intent"]["intent_id"] == str(intent.intent_id)
    assert record["deployment_context"]["deployment_id"] == str(deployment_id)
    assert record["deployment_context"]["correlation_id"] is not None
    assert record["execution_state"]["lifecycle_state"] == "stable"


def test_capture_appends_without_mutating_either_store(tmp_path) -> None:
    intent = CanonicalIntent(
        engineering_version=1,
        domain_id="cisco_aci",
        owner="platform-engineering",
        domain_intent={"apic": {"tenants": [{"name": "web-tenant", "vrfs": [], "bridge_domains": []}]}},
    )
    execution_store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(execution_store, intent)

    knowledge_path = tmp_path / "knowledge" / "deployments.jsonl"
    import app.knowledge_capture as kc_module

    kc_module.KNOWLEDGE_CAPTURE_PATH = knowledge_path

    before_state = execution_store.get_state(deployment_id)
    before_context = execution_store.get_context(deployment_id)

    capture_deployment_outcome(_FakeIntentStore(intent), execution_store, deployment_id)

    assert execution_store.get_state(deployment_id) == before_state
    assert execution_store.get_context(deployment_id) == before_context


def test_capture_appends_one_line_per_call(tmp_path) -> None:
    intent = CanonicalIntent(
        engineering_version=1,
        domain_id="cisco_aci",
        owner="platform-engineering",
        domain_intent={"apic": {"tenants": [{"name": "web-tenant", "vrfs": [], "bridge_domains": []}]}},
    )
    execution_store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(execution_store, intent)

    knowledge_path = tmp_path / "knowledge" / "deployments.jsonl"
    import app.knowledge_capture as kc_module

    kc_module.KNOWLEDGE_CAPTURE_PATH = knowledge_path

    capture_deployment_outcome(_FakeIntentStore(intent), execution_store, deployment_id)
    capture_deployment_outcome(_FakeIntentStore(intent), execution_store, deployment_id)

    lines = knowledge_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
