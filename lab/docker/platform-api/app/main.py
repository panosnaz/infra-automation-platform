"""Platform API — Vertical Slice v0.1.

Per ADR-004 (Platform API as the Unified Platform Interface), this service is
the single entry point for all platform consumers.

Milestone 3 (docs/05-Operations/14-Vertical-Slice-v0.1-Roadmap.md) scope:
the Deployment Lifecycle — RequestDeployment creates DeploymentContext +
ExecutionState in the Execution Store (Platform Specification 03 §5), then
returns once ACCEPTED is reached. DEPLOYING -> VALIDATING -> STABLE run
afterward via a FastAPI BackgroundTask standing in for the Workflow Engine
reacting to DeploymentRequested (ADR-011's event bus remains deferred; this
is the mocked reaction, not a new messaging abstraction) — this is what
makes RequestDeployment's response synchronous at ACCEPTED while the rest
of the lifecycle is asynchronous, exactly as Contract #2 §3 specifies.
Business Approval (ADR-015) is not implemented — every deployment is lab
environment, approval_state=none_required, reaching ACCEPTED directly
without ever resting at PENDING_APPROVAL.

Explicitly NOT implemented yet (future milestones, tracked in the roadmap
above):
  - Business Approval (ADR-015) / PENDING_APPROVAL
  - DRIFTED / FAILED / RETIRED lifecycle states
  - Knowledge Capture — Milestone 5
  - Authentication / authorization (RBAC), rate limiting, idempotency keys
  - Materializing domain_intent into Nautobot Tenant/VRF/BridgeDomain/Prefix
    objects (a real gap surfaced while implementing Milestone 1 — SubmitIntent
    requires a matching Tenant to already exist; see app/nautobot_store.py)
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field, ValidationError

from canonical_intent import ApprovalState, CanonicalIntent, DeploymentContext, Environment, ExecutionState, LifecycleState

from .audit_log import log_denial
from .execution_store import ExecutionStore, ExecutionStoreError
from .nautobot_store import NautobotIntentStore, NautobotStoreError
from .technical_policy import TechnicalPolicyClient, TechnicalPolicyUnavailableError
from .terraform_stub import simulate_deployment
from .validation_stub import simulate_validation
from .workflow_stub import on_deployment_requested

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://host.docker.internal:8200")
NAUTOBOT_URL = os.environ.get("NAUTOBOT_URL", "http://host.docker.internal:8080")
NAUTOBOT_TOKEN = os.environ.get("NAUTOBOT_TOKEN")

_HTTP_TIMEOUT = 3.0

app = FastAPI(
    title="Platform API",
    description="Network Platform Engineering Platform — unified platform interface.",
    version="0.1.0",
)


class DependencyStatus(BaseModel):
    name: str
    reachable: bool
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    dependencies: list[DependencyStatus]


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe. No external dependencies — always returns 200 if the process is up."""
    return {"status": "ok"}


@app.get("/version", tags=["meta"])
def version() -> dict[str, str]:
    """Report service identity and implementation phase."""
    return {
        "service": "platform-api",
        "version": app.version,
        "phase": "vertical-slice-v0.1-milestone-2 — Intent Lifecycle + Technical Policy, no Deployment yet",
    }


@app.get("/readiness", response_model=ReadinessResponse, tags=["meta"])
def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe. Checks connectivity to Vault and Nautobot.

    A dependency is considered "reachable" if it returns any HTTP response,
    including 4xx/5xx — this checks network reachability, not authentication
    or authorization state.
    """
    dependencies = [
        _check_http("vault", f"{VAULT_ADDR.rstrip('/')}/v1/sys/health"),
        _check_http("nautobot", NAUTOBOT_URL.rstrip("/")),
    ]

    all_reachable = all(dep.reachable for dep in dependencies)
    response.status_code = status.HTTP_200_OK if all_reachable else status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if all_reachable else "degraded",
        dependencies=dependencies,
    )


def _check_http(name: str, url: str) -> DependencyStatus:
    try:
        resp = httpx.get(url, timeout=_HTTP_TIMEOUT)
        return DependencyStatus(name=name, reachable=True, detail=f"HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        return DependencyStatus(name=name, reachable=False, detail=str(exc))


# ---------------------------------------------------------------------------
# Intent Lifecycle — SubmitIntent / GetIntent, with Technical Policy (M2).
# See Contract #2 §3 (Intent Lifecycle) for the full sequence.
# ---------------------------------------------------------------------------

_intent_store: NautobotIntentStore | None = None


def get_intent_store() -> NautobotIntentStore:
    global _intent_store
    if _intent_store is None:
        if not NAUTOBOT_TOKEN:
            raise HTTPException(
                status_code=500,
                detail="NAUTOBOT_TOKEN is not configured on the Platform API.",
            )
        _intent_store = NautobotIntentStore(base_url=NAUTOBOT_URL, token=NAUTOBOT_TOKEN)
    return _intent_store


_policy_client: TechnicalPolicyClient | None = None


def get_policy_client() -> TechnicalPolicyClient:
    global _policy_client
    if _policy_client is None:
        _policy_client = TechnicalPolicyClient()
    return _policy_client

class SubmitIntentRequest(BaseModel):
    domain_id: str
    domain_intent: dict[str, Any]
    owner: str
    tags: dict[str, str] = Field(default_factory=dict)


_ACI_TENANT_PREFIX = "ACI:"  # matches platform/python/generator/transformer.py


def _aci_tenant_name(domain_intent: dict[str, Any]) -> str:
    """Resolve the Nautobot Tenant name a cisco_aci domain_intent anchors to.

    Domain-specific knowledge deliberately lives here, at the domain-aware
    API boundary — not inside NautobotIntentStore, which must stay
    domain-agnostic per Contract #1's opacity rule for domain_intent (found
    during the Milestone 1 Architecture Validation Review, 2026-07-05).

    Milestone 1 scope: exactly one domain (cisco_aci), exactly one tenant
    per CanonicalIntent. CanonicalIntent's own domain_id validation
    already guarantees this function is only ever called for cisco_aci
    (KNOWN_DOMAINS); no dispatch-by-domain mechanism exists yet, and one
    is not introduced speculatively — a second domain is what would
    justify it.
    """
    try:
        tenants = domain_intent["apic"]["tenants"]
        return f"{_ACI_TENANT_PREFIX}{tenants[0]['name']}"
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract a tenant name from domain_intent (cisco_aci shape expected): {exc}",
        ) from exc


@app.post("/intents", response_model=CanonicalIntent, status_code=status.HTTP_201_CREATED, tags=["intent"])
def submit_intent(request: SubmitIntentRequest) -> CanonicalIntent:
    """SubmitIntent (Contract #2 §5) — Milestone 1 scope.

    Intent Translation + Nautobot persistence only. Technical Policy
    (ADR-014) is not wired in yet (Milestone 2). Every call is treated as a
    first submission (engineering_version=1) — revision/lineage resolution
    is out of scope for Milestone 1.
    """
    try:
        intent = CanonicalIntent(
            engineering_version=1,
            domain_id=request.domain_id,
            domain_intent=request.domain_intent,
            owner=request.owner,
            tags=request.tags,
        )
    except ValidationError as exc:
        # include_context=False: a custom field_validator's raised ValueError
        # (e.g. CanonicalIntent's domain_id check) is otherwise embedded in
        # errors()['ctx']['error'] as a raw exception object, which is not
        # JSON-serializable and turns this 422 into an unhandled 500 instead.
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_context=False, include_url=False),
        ) from exc

    try:
        decision = get_policy_client().evaluate(intent)
    except TechnicalPolicyUnavailableError as exc:
        # Fail closed: OPA unreachable, timed out, or returned a missing/
        # malformed decision are all treated identically (ADR-014 Appendix A).
        # No persistence, no audit record — nothing was actually evaluated.
        raise HTTPException(
            status_code=502,
            detail={"error_code": "TECHNICAL_POLICY_UNAVAILABLE", "detail": str(exc)},
        ) from exc

    if not decision.allow:
        try:
            log_denial(intent, decision)
        except Exception:  # noqa: BLE001 - audit failures must never change the response
            print(f"WARNING: failed to write audit record for denied intent {intent.intent_id}")
        raise HTTPException(
            status_code=422,
            detail={"error_code": "TECHNICAL_POLICY_DENIED", "policy_reasons": decision.reasons},
        )

    tenant_name = _aci_tenant_name(intent.domain_intent)
    try:
        get_intent_store().save(intent, tenant_name=tenant_name)
    except NautobotStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return intent


@app.get("/intents/{intent_id}/{engineering_version}", response_model=CanonicalIntent, tags=["intent"])
def get_intent(intent_id: str, engineering_version: int) -> CanonicalIntent:
    """GetIntent (Contract #2 §5) — reads the CanonicalIntent back from Nautobot.

    Deliberately holds nothing in the Platform API process itself — proving
    Nautobot, not process memory, is the Source of Truth for CanonicalIntent
    (ADR-001 / Contract #3 §5) is the actual point of Milestone 1.
    """
    try:
        return get_intent_store().get(intent_id, engineering_version)
    except NautobotStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Deployment Lifecycle (Milestone 3) — RequestDeployment / GetDeployment.
# See Contract #2 §3 (Deployment Lifecycle) and Contract #3 (lifecycle,
# ownership, event timing) for the full sequence this implements.
# ---------------------------------------------------------------------------

_execution_store: ExecutionStore | None = None


def get_execution_store() -> ExecutionStore:
    global _execution_store
    if _execution_store is None:
        _execution_store = ExecutionStore()
    return _execution_store


class RequestDeploymentRequest(BaseModel):
    intent_id: uuid.UUID
    engineering_version: int
    requester: str
    entry_point: str
    environment: Environment = Environment.LAB


class DeploymentResponse(BaseModel):
    deployment_context: DeploymentContext
    execution_state: ExecutionState


def _run_deployment_pipeline(store: ExecutionStore, deployment_id: uuid.UUID) -> None:
    """The mocked DeploymentRequested reaction chain: Workflow -> Terraform -> Validation.

    Runs as a FastAPI BackgroundTask, scheduled only after RequestDeployment's
    response has already been sent — this is what makes ACCEPTED synchronous
    while DEPLOYING/VALIDATING/STABLE are asynchronous (Contract #2 §3,
    Contract #3 §3), without building a real event bus (ADR-011, still
    deferred). Each stub owns exactly one transition, per Contract #3 §2.
    """
    on_deployment_requested(store, deployment_id)
    simulate_deployment(store, deployment_id)
    simulate_validation(store, deployment_id)


@app.post("/deployments", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED, tags=["deployment"])
def request_deployment(request: RequestDeploymentRequest, background_tasks: BackgroundTasks) -> DeploymentResponse:
    """RequestDeployment (Contract #2 §5) — Milestone 3 scope.

    Consumes an existing CanonicalIntent (never mutates it), creates
    DeploymentContext + ExecutionState, persists both to the Execution
    Store, and returns once ACCEPTED is reached — matching Contract #2 §3
    exactly; the rest of the lifecycle happens after the response returns.

    Business Approval (ADR-015) is not implemented in this milestone:
    approval_state is always none_required, so ACCEPTED is always reached
    directly, never resting at PENDING_APPROVAL. This is a deliberate
    Milestone 3 scope boundary, not a claim that production/approval-
    required environments are supported yet.
    """
    try:
        intent = get_intent_store().get(str(request.intent_id), request.engineering_version)
    except NautobotStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    context = DeploymentContext(
        intent_id=intent.intent_id,
        engineering_version=intent.engineering_version,
        requester=request.requester,
        entry_point=request.entry_point,
        environment=request.environment,
        approval_state=ApprovalState.NONE_REQUIRED,
    )
    state = ExecutionState(
        deployment_id=context.deployment_id,
        lifecycle_state=LifecycleState.ACCEPTED,
        desired_version=intent.engineering_version,
        approval_decision="not_required",
        persisted_at=datetime.now(timezone.utc),
    )

    store = get_execution_store()
    store.create(context, state)

    background_tasks.add_task(_run_deployment_pipeline, store, context.deployment_id)

    return DeploymentResponse(deployment_context=context, execution_state=state)


@app.get("/deployments/{deployment_id}", response_model=DeploymentResponse, tags=["deployment"])
def get_deployment(deployment_id: uuid.UUID) -> DeploymentResponse:
    """GetDeploymentStatus (Contract #2 §5) — the composite Deployment resource

    (DeploymentContext + ExecutionState, per Contract #2 §4's "composed view"
    definition) for one deployment attempt, read from the Execution Store.
    """
    store = get_execution_store()
    try:
        context = store.get_context(deployment_id)
        state = store.get_state(deployment_id)
    except ExecutionStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeploymentResponse(deployment_context=context, execution_state=state)
