"""Unit tests for the Workflow/Terraform/Validation stubs — no Docker required."""

from __future__ import annotations

import uuid

from app.execution_store import ExecutionStore
from app.terraform_stub import simulate_deployment
from app.validation_stub import simulate_validation
from app.workflow_stub import on_deployment_requested
from canonical_intent import ApprovalState, DeploymentContext, Environment, ExecutionState, LifecycleState


def _new_deployment(store: ExecutionStore) -> uuid.UUID:
    context = DeploymentContext(
        intent_id=uuid.uuid4(),
        engineering_version=3,
        requester="tester",
        entry_point="cli",
        environment=Environment.LAB,
        approval_state=ApprovalState.NONE_REQUIRED,
    )
    state = ExecutionState(deployment_id=context.deployment_id, lifecycle_state=LifecycleState.ACCEPTED, desired_version=3)
    store.create(context, state)
    return context.deployment_id


def test_workflow_stub_transitions_accepted_to_deploying(tmp_path) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)

    on_deployment_requested(store, deployment_id)

    assert store.get_state(deployment_id).lifecycle_state == LifecycleState.DEPLOYING


def test_terraform_stub_transitions_deploying_to_validating(tmp_path) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    store.transition(deployment_id, LifecycleState.DEPLOYING)

    simulate_deployment(store, deployment_id)

    state = store.get_state(deployment_id)
    assert state.lifecycle_state == LifecycleState.VALIDATING
    assert state.deployed_at is not None


def test_validation_stub_transitions_validating_to_stable_and_sets_applied_version(tmp_path) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    store.transition(deployment_id, LifecycleState.DEPLOYING)
    store.transition(deployment_id, LifecycleState.VALIDATING)

    simulate_validation(store, deployment_id)

    state = store.get_state(deployment_id)
    assert state.lifecycle_state == LifecycleState.STABLE
    assert state.validated_at is not None
    assert state.applied_version == state.desired_version == 3
