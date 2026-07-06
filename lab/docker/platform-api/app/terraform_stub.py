"""Terraform stub — Vertical Slice v0.1, Milestone 3.

Simulates "deployment completed successfully" only — no real Terraform
invocation. Real Terraform already works end-to-end (Phase 3); re-exercising
it is not this milestone's purpose (see docs/05-Operations/
14-Vertical-Slice-v0.1-Roadmap.md). Transitions DEPLOYING -> VALIDATING.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from canonical_intent import LifecycleState

from .execution_store import ExecutionStore


def simulate_deployment(store: ExecutionStore, deployment_id: uuid.UUID) -> None:
    store.transition(deployment_id, LifecycleState.VALIDATING, deployed_at=datetime.now(timezone.utc))
