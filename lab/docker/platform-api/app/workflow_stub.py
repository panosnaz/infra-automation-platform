"""Workflow Engine stub — Vertical Slice v0.1, Milestone 3.

Real responsibility (ADR-005/ADR-011): react to `DeploymentRequested` and
sequence execution tasks. This stub does exactly one thing: transition
ACCEPTED -> DEPLOYING. No orchestration logic, no business decisions —
matches ADR-004's "Workflow Engine owns no business logic" rule, trivially
satisfied since there is none here, only a state transition.

Event publication (`DeploymentRequested`) remains mocked per ADR-011 — this
function IS the mocked reaction, called directly rather than through a real
event bus (see docs/05-Operations/14-Vertical-Slice-v0.1-Roadmap.md).
"""

from __future__ import annotations

import uuid

from canonical_intent import LifecycleState

from .execution_store import ExecutionStore


def on_deployment_requested(store: ExecutionStore, deployment_id: uuid.UUID) -> None:
    store.transition(deployment_id, LifecycleState.DEPLOYING)
