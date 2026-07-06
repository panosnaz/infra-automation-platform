"""SQLite-backed persistence for DeploymentContext + ExecutionState.

Per Contract #3 §5 (Persistence Boundary), these belong to the Workflow/
Execution store, never to Nautobot (which holds CanonicalIntent only).
Minimum real implementation: one SQLite file, one table, both objects
stored as JSON per deployment_id — mirrors nautobot_store.py's pattern of
storing the whole Pydantic object rather than building relational columns
for every field.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from canonical_intent import DeploymentContext, ExecutionState, LifecycleState

EXECUTION_STORE_PATH = Path(os.environ.get("EXECUTION_STORE_PATH", "/app/data/execution_store.db"))

# Contract #3 §2 (State Ownership Model) — only the transitions this
# milestone implements. DRIFTED/FAILED/RETIRED are deliberately absent;
# adding them is a future milestone's job, not this one's.
_ALLOWED_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.ACCEPTED: {LifecycleState.DEPLOYING},
    LifecycleState.DEPLOYING: {LifecycleState.VALIDATING},
    LifecycleState.VALIDATING: {LifecycleState.STABLE},
}


class ExecutionStoreError(Exception):
    """Raised when a DeploymentContext/ExecutionState cannot be created or read."""


class InvalidTransitionError(ExecutionStoreError):
    """Raised when a requested lifecycle_state transition isn't allowed from the current state."""


class ExecutionStore:
    def __init__(self, path: Path = EXECUTION_STORE_PATH) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deployments (
                    deployment_id TEXT PRIMARY KEY,
                    deployment_context TEXT NOT NULL,
                    execution_state TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def create(self, context: DeploymentContext, state: ExecutionState) -> None:
        if context.deployment_id != state.deployment_id:
            raise ExecutionStoreError("DeploymentContext.deployment_id and ExecutionState.deployment_id must match")
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO deployments (deployment_id, deployment_context, execution_state) VALUES (?, ?, ?)",
                    (str(context.deployment_id), context.model_dump_json(), state.model_dump_json()),
                )
            except sqlite3.IntegrityError as exc:
                raise ExecutionStoreError(f"Deployment {context.deployment_id} already exists") from exc

    def get_context(self, deployment_id: uuid.UUID | str) -> DeploymentContext:
        context_json, _ = self._fetch(deployment_id)
        return DeploymentContext.model_validate_json(context_json)

    def get_state(self, deployment_id: uuid.UUID | str) -> ExecutionState:
        _, state_json = self._fetch(deployment_id)
        return ExecutionState.model_validate_json(state_json)

    def transition(self, deployment_id: uuid.UUID | str, to_state: LifecycleState, **field_updates: object) -> ExecutionState:
        """Move `deployment_id`'s ExecutionState to `to_state`, validating the transition first.

        Only the current->to_state pairs in _ALLOWED_TRANSITIONS are permitted —
        this is what makes an invalid transition (e.g. skipping a step, or
        going backward) a caught error rather than silently-accepted state.
        """
        current = self.get_state(deployment_id)
        allowed = _ALLOWED_TRANSITIONS.get(current.lifecycle_state, set())
        if to_state not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition deployment {deployment_id} from {current.lifecycle_state} to {to_state}"
            )
        updated = current.model_copy(
            update={"lifecycle_state": to_state, "last_updated_at": datetime.now(timezone.utc), **field_updates}
        )
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE deployments SET execution_state = ? WHERE deployment_id = ?",
                (updated.model_dump_json(), str(deployment_id)),
            )
            if cursor.rowcount == 0:
                raise ExecutionStoreError(f"No deployment found for deployment_id={deployment_id}")
        return updated

    def _fetch(self, deployment_id: uuid.UUID | str) -> tuple[str, str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT deployment_context, execution_state FROM deployments WHERE deployment_id = ?",
                (str(deployment_id),),
            ).fetchone()
        if row is None:
            raise ExecutionStoreError(f"No deployment found for deployment_id={deployment_id}")
        return row
