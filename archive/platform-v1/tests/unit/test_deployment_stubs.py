"""Unit tests for the Validation stub — no Docker required.

Milestone 6A retired workflow_stub.py (ACCEPTED->DEPLOYING moved to
terraform_executor.py, per Contract #3 §2) and terraform_stub.py (replaced
by terraform_executor.py — see test_terraform_executor.py).
"""

from __future__ import annotations

import uuid

from app.execution_store import ExecutionStore
from app.validation_stub import simulate_validation
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


def test_validation_stub_owns_deploying_to_validating_entry_transition(tmp_path) -> None:
    """Milestone 6A: Validation, not the Execution Plane, owns DEPLOYING -> VALIDATING (Contract #3 §2),

    including setting deployed_at -- moved here from terraform_stub.py, which
    no longer performs this transition.
    """
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    store.transition(deployment_id, LifecycleState.DEPLOYING)

    simulate_validation(store, deployment_id)

    state = store.get_state(deployment_id)
    assert state.lifecycle_state == LifecycleState.STABLE
    assert state.deployed_at is not None


def test_validation_stub_transitions_validating_to_stable_and_sets_applied_version(tmp_path) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    store.transition(deployment_id, LifecycleState.DEPLOYING)

    simulate_validation(store, deployment_id)

    state = store.get_state(deployment_id)
    assert state.lifecycle_state == LifecycleState.STABLE
    assert state.validated_at is not None
    assert state.applied_version == state.desired_version == 3
