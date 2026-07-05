"""Canonical Intent — Platform Specification Contract #1.

docs/11-Specifications/01-Canonical-Intent-Specification.md is the
authoritative specification. This module is a Python/Pydantic reference
implementation that conforms to it, not the other way around — any future
implementation in another language must conform to that Markdown document.

Three related, distinct objects:

- CanonicalIntent   — immutable desired-state engineering object
- DeploymentContext — mutable request-scoped metadata for one deployment attempt
- ExecutionState    — mutable record of what actually happened for one attempt

A single CanonicalIntent (identified by intent_id + engineering_version) may
be referenced by many DeploymentContext objects over time (retries, repeated
deployments to different environments), each with its own ExecutionState.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Domain Identifier — interim validation until the Domain Provider Registry
# (Platform Specification Tier 3) exists.
#
# domain_id is a plain string on CanonicalIntent, not a closed enum, so that
# adding a domain never requires a schema/type change here — only widening
# this allow-list (and, later, replacing this allow-list check with a live
# registry lookup) changes.
# ---------------------------------------------------------------------------
KNOWN_DOMAINS: frozenset[str] = frozenset({"cisco_aci"})


class Environment(str, Enum):
    LAB = "lab"
    STAGING = "staging"
    PRODUCTION = "production"


class ApprovalState(str, Enum):
    NONE_REQUIRED = "none_required"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class LifecycleState(str, Enum):
    """Execution lifecycle only. CanonicalIntent itself has no lifecycle —
    it is immutable desired state. This state machine belongs to
    ExecutionState, tracking one DeploymentContext's progress.

    This is the EXTERNALLY VISIBLE lifecycle (Platform Execution Model
    Specification, docs/11-Specifications/03-Platform-Execution-Model-Specification.md).
    Internal implementation steps — Intent Translation, Policy Evaluation,
    Nautobot persistence — happen synchronously inside the transition into
    ACCEPTED and are deliberately NOT separate lifecycle states; they are
    implementation detail, not platform contract.

    STABLE is an execution-convergence fact ("applied_version matches
    desired_version, confirmed by validation") and must never be confused
    with ADR-001's "platform-managed" (a provenance fact: was this object's
    desired state authored via forward intent, set once, permanently).
    See the Platform Execution Model Specification for the full contrast.
    """

    ACCEPTED = "accepted"
    DEPLOYING = "deploying"
    VALIDATING = "validating"
    STABLE = "stable"
    DRIFTED = "drifted"
    FAILED = "failed"
    RETIRED = "retired"


class CanonicalIntent(BaseModel):
    """The immutable, domain-agnostic desired-state engineering object.

    Describes WHAT the business wants, in one shape regardless of target
    domain. Any change to desired state produces a NEW CanonicalIntent (a
    new engineering_version) — never a mutation of an existing one.

    Deliberately excludes: approval state, deployment lifecycle, requester
    identity, correlation IDs. Those are request-scoped or execution-scoped
    concerns — see DeploymentContext and ExecutionState below.
    """

    model_config = ConfigDict(frozen=True)

    intent_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Stable identity across every version of this intent's lineage. Never changes across revisions.",
    )
    engineering_version: int = Field(
        ge=1,
        description="Monotonically increasing revision of this intent_id's desired state. 1 is the first submission.",
    )
    previous_version: int | None = Field(
        default=None,
        description="engineering_version this revision supersedes, if any. Enables rollback and lineage tracing independent of deployment history.",
    )

    domain_id: str = Field(
        description="Identifies which Domain Provider's engineering model domain_intent conforms to. Validated against KNOWN_DOMAINS pending the Domain Provider Registry."
    )
    domain_intent: dict[str, Any] = Field(
        description="Domain-specific desired-state content (e.g. Cisco ACI tenants/VRFs/bridge domains). Opaque to everything except that domain's own generator and Domain Provider Specification schema."
    )

    owner: str = Field(
        description="Team or individual accountable for this engineering object on an ongoing basis. Persists across every version — distinct from DeploymentContext.requester, who submitted one specific deployment attempt."
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Business metadata (e.g. cost-center, department). Enduring attributes of the object, not the request.",
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("domain_id")
    @classmethod
    def _validate_domain_id(cls, v: str) -> str:
        if v not in KNOWN_DOMAINS:
            raise ValueError(
                f"Unknown domain_id '{v}'. Known domains (pending Domain Provider Registry): {sorted(KNOWN_DOMAINS)}"
            )
        return v


class DeploymentContext(BaseModel):
    """Request-scoped metadata for one attempt to deploy a CanonicalIntent.

    Mutable/transactional — a new DeploymentContext is created for every
    deployment attempt (including retries) against the same
    (intent_id, engineering_version) pair.
    """

    deployment_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    intent_id: uuid.UUID
    engineering_version: int = Field(ge=1)

    correlation_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Ties together every event/log/trace this deployment attempt produces across the platform (Platform Events Specification, Tier 2).",
    )

    requester: str = Field(
        description="Who or what submitted this specific deployment attempt. May differ from CanonicalIntent.owner (e.g. an admin redeploying on a team's behalf)."
    )
    entry_point: str = Field(
        description="Which entry point this request arrived through, e.g. 'cli', 'jira', 'ai_agent', 'rest'."
    )

    environment: Environment
    approval_state: ApprovalState = ApprovalState.NONE_REQUIRED
    approved_by: str | None = None
    approved_at: datetime | None = None

    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionState(BaseModel):
    """Mutable record of what actually happened for one DeploymentContext.

    Updated in place as the deployment progresses through the pipeline —
    this is the object that changes constantly. CanonicalIntent never does.
    """

    deployment_id: uuid.UUID
    lifecycle_state: LifecycleState = LifecycleState.ACCEPTED

    desired_version: int = Field(
        ge=1,
        description="The engineering_version this execution is converging toward (mirrors DeploymentContext.engineering_version).",
    )
    applied_version: int | None = Field(
        default=None,
        description="The engineering_version last CONFIRMED actually live, set only after successful validation. None if never successfully deployed and validated. Drift is detected by comparing the live infrastructure against the domain_intent of applied_version, not desired_version.",
    )

    policy_decision: str | None = Field(
        default=None, description="'allow' | 'deny' — see the Policy Decision Contract (ADR-014, Tier 1 #3)."
    )
    policy_reasons: list[str] = Field(default_factory=list)

    persisted_to_nautobot_at: datetime | None = None
    deployed_at: datetime | None = None
    validated_at: datetime | None = None

    validation_result_ref: str | None = Field(
        default=None,
        description="Reference to a Validation Result object (Validation Specification, Tier 1 #4).",
    )

    rollback_of: uuid.UUID | None = Field(
        default=None, description="deployment_id this deployment is rolling back, if applicable."
    )

    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
