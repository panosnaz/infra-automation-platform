"""Validation stub — Vertical Slice v0.1, Milestone 3.

Simulates "validation successful" only — no real pyATS invocation. Real
validation already works end-to-end (Phase 5). Transitions VALIDATING ->
STABLE, and — per Contract #3 §4 — sets applied_version = desired_version,
the point at which the platform records the deployment as confirmed live.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from canonical_intent import LifecycleState

from .execution_store import ExecutionStore


def simulate_validation(store: ExecutionStore, deployment_id: uuid.UUID) -> None:
    state = store.get_state(deployment_id)
    store.transition(
        deployment_id,
        LifecycleState.STABLE,
        validated_at=datetime.now(timezone.utc),
        applied_version=state.desired_version,
    )
