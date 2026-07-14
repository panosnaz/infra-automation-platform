"""Knowledge Capture — Vertical Slice v0.1, Milestone 5.

Per ADR-009 (Knowledge Layer) and docs/05-Operations/
14-Vertical-Slice-v0.1-Roadmap.md (M5), this is the minimum real proof that
a durable, structured engineering record is produced for every completed
deployment attempt: one JSON Lines record containing the CanonicalIntent,
DeploymentContext, and final ExecutionState together. Including
DeploymentContext gives `correlation_id` its first real consumer.

Read-only with respect to the Intent Store (Nautobot) and the Execution
Store (SQLite) — this module only calls their existing get_*() methods and
never writes to either. Its own JSONL file is the only thing it writes,
mirroring audit_log.py's use of jsonl_writer.py's generic append primitive.

Explicitly not built here (Vertical Slice v0.1 scope, ADR-009's own listed
Future Considerations): semantic search, vector storage, Obsidian
integration, or any AI retrieval surface. This module only proves the
record can be captured at all.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .execution_store import ExecutionStore
from .jsonl_writer import append_jsonl
from .nautobot_store import NautobotIntentStore

KNOWLEDGE_CAPTURE_PATH = Path(os.environ.get("KNOWLEDGE_CAPTURE_PATH", "/app/data/knowledge/deployments.jsonl"))


def capture_deployment_outcome(
    intent_store: NautobotIntentStore, execution_store: ExecutionStore, deployment_id: uuid.UUID
) -> None:
    """Append one record for a completed (STABLE or FAILED) deployment attempt.

    Reads DeploymentContext + ExecutionState from the Execution Store and
    the matching CanonicalIntent from the Intent Store — never writes to
    either. Failures here must never surface to the caller; see app/main.py's
    call sites, both wrapped in a try/except that logs locally.
    """
    context = execution_store.get_context(deployment_id)
    state = execution_store.get_state(deployment_id)
    intent = intent_store.get(str(context.intent_id), context.engineering_version)

    record: dict[str, Any] = {
        "deployment_id": str(deployment_id),
        "lifecycle_state": state.lifecycle_state.value,
        "captured_at": datetime.now(timezone.utc),
        "canonical_intent": intent.model_dump(mode="json"),
        "deployment_context": context.model_dump(mode="json"),
        "execution_state": state.model_dump(mode="json"),
    }
    append_jsonl(KNOWLEDGE_CAPTURE_PATH, record)
