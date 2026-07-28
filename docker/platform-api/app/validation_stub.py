"""Validation stub — Vertical Slice v0.1, Milestone 3 (extended Milestone 6A).

Simulates "validation successful" only — no real pyATS invocation. Real
validation already works end-to-end (Phase 5). Owns its own entry
transition, DEPLOYING -> VALIDATING (Contract #3 §2 — Validation, not the
Execution Plane, owns this transition; corrected during Milestone 6A, Real
Terraform Integration, when terraform_executor.py stopped performing it),
setting deployed_at at that point (also moved here from terraform_stub.py,
since it marks the moment deployment work is confirmed complete and
validation begins) — then VALIDATING -> STABLE, and — per Contract #3 §4 —
sets applied_version = desired_version, the point at which the platform
records the deployment as confirmed live.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from canonical_intent import LifecycleState

from .execution_store import ExecutionStore


def simulate_validation(store: ExecutionStore, deployment_id: uuid.UUID) -> None:
    store.transition(deployment_id, LifecycleState.VALIDATING, deployed_at=datetime.now(timezone.utc))
    state = store.get_state(deployment_id)
    store.transition(
        deployment_id,
        LifecycleState.STABLE,
        validated_at=datetime.now(timezone.utc),
        applied_version=state.desired_version,
    )
