"""Unit tests for the Execution Store — no Docker required.

Covers lifecycle transitions, persistence, invalid transitions, and a
missing DeploymentContext, using a temporary SQLite file per test.
"""

from __future__ import annotations

import uuid

import pytest
from app.execution_store import ExecutionStore, ExecutionStoreError, InvalidTransitionError
from canonical_intent import ApprovalState, DeploymentContext, Environment, ExecutionState, LifecycleState


@pytest.fixture
def store(tmp_path):
    return ExecutionStore(path=tmp_path / "execution_store.db")


def _new_deployment() -> tuple[DeploymentContext, ExecutionState]:
    context = DeploymentContext(
        intent_id=uuid.uuid4(),
        engineering_version=1,
        requester="tester",
        entry_point="cli",
        environment=Environment.LAB,
        approval_state=ApprovalState.NONE_REQUIRED,
    )
    state = ExecutionState(
        deployment_id=context.deployment_id,
        lifecycle_state=LifecycleState.ACCEPTED,
        desired_version=1,
    )
    return context, state


def test_create_and_get_roundtrip(store: ExecutionStore) -> None:
    context, state = _new_deployment()
    store.create(context, state)

    fetched_context = store.get_context(context.deployment_id)
    fetched_state = store.get_state(context.deployment_id)

    assert fetched_context.deployment_id == context.deployment_id
    assert fetched_context.intent_id == context.intent_id
    assert fetched_state.lifecycle_state == LifecycleState.ACCEPTED
    assert fetched_state.desired_version == 1
    assert fetched_state.applied_version is None


def test_full_lifecycle_transition_sequence(store: ExecutionStore) -> None:
    context, state = _new_deployment()
    store.create(context, state)

    deploying = store.transition(context.deployment_id, LifecycleState.DEPLOYING)
    assert deploying.lifecycle_state == LifecycleState.DEPLOYING

    validating = store.transition(context.deployment_id, LifecycleState.VALIDATING, deployed_at=None)
    assert validating.lifecycle_state == LifecycleState.VALIDATING

    stable = store.transition(context.deployment_id, LifecycleState.STABLE, applied_version=1)
    assert stable.lifecycle_state == LifecycleState.STABLE
    assert stable.applied_version == 1

    # Confirm every transition was actually persisted, not just returned.
    assert store.get_state(context.deployment_id).lifecycle_state == LifecycleState.STABLE


def test_invalid_transition_is_rejected(store: ExecutionStore) -> None:
    context, state = _new_deployment()
    store.create(context, state)

    with pytest.raises(InvalidTransitionError):
        store.transition(context.deployment_id, LifecycleState.STABLE)  # skips DEPLOYING/VALIDATING


def test_backward_transition_is_rejected(store: ExecutionStore) -> None:
    context, state = _new_deployment()
    store.create(context, state)
    store.transition(context.deployment_id, LifecycleState.DEPLOYING)

    with pytest.raises(InvalidTransitionError):
        store.transition(context.deployment_id, LifecycleState.ACCEPTED)


def test_missing_deployment_context_raises(store: ExecutionStore) -> None:
    with pytest.raises(ExecutionStoreError):
        store.get_context(uuid.uuid4())

    with pytest.raises(ExecutionStoreError):
        store.get_state(uuid.uuid4())

    with pytest.raises(ExecutionStoreError):
        store.transition(uuid.uuid4(), LifecycleState.DEPLOYING)


def test_duplicate_create_is_rejected(store: ExecutionStore) -> None:
    context, state = _new_deployment()
    store.create(context, state)

    with pytest.raises(ExecutionStoreError):
        store.create(context, state)
