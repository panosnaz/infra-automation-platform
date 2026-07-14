"""Approval Workflow — ADR-015 (Deployment Approval as a Distinct Capability
from Technical Policy).

Determines whether a specific deployment attempt is authorized right now.
Unlike Technical Policy (ADR-014), this is plain Python business logic, not
an external engine — ADR-015 explicitly expects a different implementation
shape here (stateful, human-in-the-loop, time-dependent) than Technical
Policy's stateless Rego rules.

Change window enforcement and approver routing are ADR-015's own named
Open Items, not implemented here — this is deliberately the smallest rule
that makes PENDING_APPROVAL / ApproveDeployment / DenyDeployment meaningful.
"""

from __future__ import annotations

from canonical_intent import DeploymentContext, Environment


def approval_required(context: DeploymentContext) -> bool:
    """Only production requires human approval — the exact example ADR-015 itself uses."""
    return context.environment == Environment.PRODUCTION
