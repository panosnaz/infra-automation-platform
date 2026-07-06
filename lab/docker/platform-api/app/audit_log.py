"""Technical Policy denial audit log — Vertical Slice v0.1, Milestone 2.

Per Contract #3 §5 (Persistence Boundary), denied requests never reach
Nautobot — their only durable record is this audit log, owned by the
Platform Gateway (ADR-004). A thin wrapper over jsonl_writer.py's generic
append primitive; carries no logic of its own beyond shaping the record.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from canonical_intent import CanonicalIntent

from .jsonl_writer import append_jsonl
from .technical_policy import PolicyDecision

AUDIT_LOG_PATH = Path(os.environ.get("AUDIT_LOG_PATH", "/app/data/policy_denials.jsonl"))


def log_denial(intent: CanonicalIntent, decision: PolicyDecision) -> None:
    """Record a Technical Policy denial. Failures here must never surface to the caller —

    see app/main.py's submit_intent: this is called from within a try/except
    that logs locally and leaves the 422 response unchanged on failure.
    """
    record: dict[str, Any] = {
        "intent_id": str(intent.intent_id),
        "engineering_version": intent.engineering_version,
        "domain_id": intent.domain_id,
        "owner": intent.owner,
        "reasons": decision.reasons,
        "evaluated_at": decision.evaluated_at,
    }
    append_jsonl(AUDIT_LOG_PATH, record)
