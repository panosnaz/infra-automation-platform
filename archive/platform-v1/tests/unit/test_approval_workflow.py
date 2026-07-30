"""Unit tests for the Approval Workflow (ADR-015) — no Docker required."""

from __future__ import annotations

import uuid

from app.approval_workflow import approval_required
from canonical_intent import ApprovalState, DeploymentContext, Environment


def _context(environment: Environment) -> DeploymentContext:
    return DeploymentContext(
        intent_id=uuid.uuid4(),
        engineering_version=1,
        requester="tester",
        entry_point="cli",
        environment=environment,
        approval_state=ApprovalState.NONE_REQUIRED,
    )


def test_production_requires_approval() -> None:
    assert approval_required(_context(Environment.PRODUCTION)) is True


def test_lab_does_not_require_approval() -> None:
    assert approval_required(_context(Environment.LAB)) is False


def test_staging_does_not_require_approval() -> None:
    assert approval_required(_context(Environment.STAGING)) is False
