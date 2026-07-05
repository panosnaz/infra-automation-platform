---
title: "Platform Specification 02 — Platform API"
description: "Contract #2 from the Platform Specification Roadmap: the Platform API as a capability, independent of any REST/OpenAPI implementation"
---

# Platform Specification 02 — Platform API

**Status:** Accepted

**Date:** 2026-07-04

**Decision Makers:** Platform Engineering Team

**Type:** Platform Specification (not an ADR — this is a contract implementing decisions already made in [ADR-004](../03-Decisions/ADR-004-Platform-API.md), [ADR-014](../03-Decisions/ADR-014-Policy-Enforcement.md), [ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md), [ADR-010](../03-Decisions/ADR-010-AI-Engineering-Assistant.md), and [Platform Specification 01 — Canonical Intent](01-Canonical-Intent-Specification.md))

**This document is the authoritative specification.** It defines the Platform API as a capability — its resources, operations, and contracts — independent of any specific transport. A FastAPI/OpenAPI implementation is a *generated artifact* derived from this specification, not the primary design document. Any future implementation (a different language, a gRPC transport, a GraphQL layer) must conform to this document.

---

# Purpose

ADR-004 established that the Platform API is the single entry point for all platform interactions, and (as refined during the 2026-07-04 Architecture Design Review) split its responsibilities into **Platform Gateway** (transport/API concerns) and **Intent Translation** (building Canonical Intent). This document is the capability specification that sits between that architectural decision and an actual REST implementation — it answers the twelve questions a real implementation cannot avoid answering, before any endpoint is coded.

---

# 1. Platform Responsibilities

The Platform API owns:

- Accepting requests from any entry point and producing a [Canonical Intent](01-Canonical-Intent-Specification.md) or a [Deployment](#4-api-resources) action against one
- Authentication, authorization, rate limiting, audit logging (Platform Gateway, per ADR-004)
- Parsing, normalizing, and schema-validating requests into Canonical Intent (Intent Translation, per ADR-004)
- Invoking **Technical Policy** ([ADR-014](../03-Decisions/ADR-014-Policy-Enforcement.md)) at `SubmitIntent` time and acting on its allow/deny decision
- Persisting an approved Canonical Intent to Nautobot
- Invoking the **Approval Workflow** ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)) at `RequestDeployment` time and acting on its authorized/pending/denied outcome
- Publishing platform events (`IntentSubmitted`, `DeploymentRequested` — Platform Events Specification, not yet drafted)

The Platform API does **not** own:

- Infrastructure execution (Terraform/Ansible — ADR-002/003)
- Technical Policy rule evaluation logic itself (OPA — ADR-014)
- Approval routing or change-window logic itself (ADR-015)
- Workflow sequencing across multiple tasks (Workflow Engine — ADR-005)
- Validation execution (pyATS/Catfish — ADR-008)

The Platform API is an **orchestrating front door**, not an execution engine. `SubmitIntent` results in, at most, one Nautobot write and one published event; `RequestDeployment` results in, at most, one Deployment-Lifecycle record write (Workflow/Execution store — see [Platform Specification 03](03-Platform-Execution-Model-Specification.md), Persistence Boundary) and one published event. It never calls Terraform, Ansible, or pyATS directly.

**Two independent lifecycles, not one.** Technical Policy (intent-level compliance) and the Approval Workflow (deployment-time authorization) answer different questions, at different times, against different inputs — see ADR-014/ADR-015 for the full rationale. This is why Section 3 below defines two separate lifecycles rather than one combined request flow.

---

# 2. Entry Points

Per ADR-010's "many entry points, one execution path" principle, the Platform API is transport-agnostic at the capability level. REST is the first entry point; CLI, Jira, ServiceNow, Git, and AI Agents are future entry points that must produce the *same* internal request shape.

An entry point's only job is translating its native format (a Jira ticket transition, a CLI flag set, an AI agent's structured tool call) into a call against the Operations defined in Section 5. The Platform API itself does not know or special-case which entry point originated a request beyond recording it — `DeploymentContext.entry_point` (Contract #1) already carries this as a plain string (`"cli"`, `"jira"`, `"ai_agent"`, `"rest"`), not as a different code path per entry point.

**Consequence for implementation:** business logic must never be written "for the REST API" — it is written once, for the Operations, and every entry point (present or future) calls the same Operations.

---

# 3. Request Lifecycle

Two **independent** lifecycles exist — not two phases of one flow. An Intent may exist for weeks or months with zero deployments against it; a single Intent may be deployed, redeployed, and rolled back many times, each a fully separate pass through the Deployment Lifecycle. **The full state machine, state ownership, and event-timing rules both lifecycles rely on are formalized in [Platform Specification 03 — Platform Execution Model](03-Platform-Execution-Model-Specification.md).** This section describes the request-handling flow; that document is authoritative for the state semantics.

## Intent Lifecycle — `SubmitIntent` (synchronous, no `ExecutionState` involved)

```text
Entry Point
    │
    ▼
Platform Gateway            (authn, authz, rate limit, audit log, parse)
    │
    ▼
Intent Translation           (normalize, resolve references, apply defaults, validate schema)
    │
    ▼
Canonical Intent              (Platform Specification 01)
    │
    ▼
Technical Policy (ADR-014)   ── evaluates CanonicalIntent alone; no DeploymentContext exists yet
    │
    ├── deny ──────────────► Response: 4xx with policy_reasons — pipeline stops here.
    │                         No CanonicalIntent is persisted. Audit log entry only.
    │
    └── allow
         │
         ▼
    Persist Canonical Intent to Nautobot
         │
         ▼
    Publish Event (IntentSubmitted)
         │
         ▼
    Response: 201 with CanonicalIntent (intent_id, engineering_version)
```

This is the *entire* lifecycle for an Intent that is never deployed. No `DeploymentContext` or `ExecutionState` is created here — those belong exclusively to the Deployment Lifecycle below. Technical Policy runs exactly once per `CanonicalIntent` revision and is never re-evaluated on a later deployment attempt against the same `engineering_version`.

## Deployment Lifecycle — `RequestDeployment` (synchronous acceptance, asynchronous execution)

```text
RequestDeployment(intent_id, engineering_version, environment, ...)
    │
    ▼
Create DeploymentContext + ExecutionState
    │
    ▼
Approval Workflow (ADR-015) evaluates DeploymentContext.approval_state
    │
    ├── none_required, or already approved ──► lifecycle_state = ACCEPTED
    │                                                │
    │                                                ▼
    │                                     Publish Event (DeploymentRequested)
    │                                                │
    │                                                ▼
    │                              Response: 201 with DeploymentContext + ExecutionState (ACCEPTED)
    │
    ├── pending (approval required, not yet given) ──► lifecycle_state = PENDING_APPROVAL
    │                                                        │
    │                                                        ▼
    │                              Response: 202 with DeploymentContext + ExecutionState (PENDING_APPROVAL)
    │                                                        │
    │                                                        ▼
    │                              (later, a separate call) ApproveDeployment / DenyDeployment
    │                                          │                              │
    │                                     approved                          denied
    │                                          │                              │
    │                                          ▼                              ▼
    │                              lifecycle_state = ACCEPTED       lifecycle_state = FAILED
    │                                          │
    │                                          ▼
    │                              Publish Event (DeploymentRequested)
    │
    └── outright denial (e.g. quota exceeded, environment restriction) ──► lifecycle_state = FAILED
                                                                                 │
                                                                                 ▼
                                                                    Response: 4xx with approval_reasons
```

`PENDING_APPROVAL` is the resting state that makes `ApproveDeployment`/`DenyDeployment` (Section 5) actually callable — without it, there is no window between "`DeploymentContext` created" and "authorization decided" for a human to act in. `DeploymentRequested` — the event the Workflow Engine subscribes to (ADR-011) — is published only once `ACCEPTED` is reached, whether that happens immediately (no approval required) or later, after a `PENDING_APPROVAL` rest is resolved.

Actual infrastructure deployment (Terraform/Ansible execution, triggered by whatever subscribes to `DeploymentRequested`) happens **after** `ACCEPTED` — tracked via `ExecutionState` (Contract #1), retrieved through `GetDeploymentStatus` (Section 5), exactly as described in [Platform Specification 03](03-Platform-Execution-Model-Specification.md).

**This means:** a `201` response from `RequestDeployment` means *"this deployment attempt was authorized and recorded"* — it does not mean *"your infrastructure now exists."* A `202` means *"recorded, awaiting approval."* This distinction must be explicit in every client integration.

---

# 4. API Resources

Resource-oriented, not verb-oriented — these are the nouns the Platform API exposes, independent of HTTP/REST specifics.

| Resource | Backed by (Contract #1) | Description |
|---|---|---|
| **Intent** | `CanonicalIntent` | A specific, immutable revision of desired engineering state. |
| **Deployment** | `DeploymentContext` + `ExecutionState` (composed view) | One attempt to realize an Intent — request metadata plus current execution status. |
| **Domain** | `KNOWN_DOMAINS` (interim) / future Domain Provider Registry | Read-only: which domain providers exist and what they accept as `domain_intent`. |
| **Approval** | `DeploymentContext.approval_state` transition | The act of approving or denying a pending Deployment. |

Deliberately **not** a resource: `Policy`. Both Technical Policy (ADR-014) and the Approval Workflow (ADR-015) are evaluated as side effects of `SubmitIntent`/`RequestDeployment` respectively (Section 5); neither is something a client creates, reads, or lists independently through this API. (OPA may expose its own management API — that is out of scope for the Platform API.)

---

# 5. Operations

| Operation | Resource | Effect |
|---|---|---|
| `SubmitIntent` | Intent | Creates a new `CanonicalIntent` (new `intent_id` if first submission, new `engineering_version` if revising an existing `intent_id`). Runs **Technical Policy** ([ADR-014](../03-Decisions/ADR-014-Policy-Enforcement.md)) synchronously. Does **not** create a `DeploymentContext`/`ExecutionState`, invoke the Approval Workflow, or trigger deployment — see `RequestDeployment`. |
| `GetIntent` | Intent | Retrieves a specific `(intent_id, engineering_version)`. |
| `ListIntents` | Intent | Lists intents, filterable by `owner`, `domain_id`, `tags`. |
| `GetIntentLineage` | Intent | Retrieves the `previous_version` chain for an `intent_id` — the full revision history. |
| `RequestDeployment` | Deployment | Creates a `DeploymentContext` + `ExecutionState` against an existing `(intent_id, engineering_version)`; runs the Deployment Lifecycle (Section 3) including the **Approval Workflow** ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)). Resolves immediately to `ACCEPTED`/`FAILED`, or rests at `PENDING_APPROVAL` until `ApproveDeployment`/`DenyDeployment` is called. |
| `GetDeploymentStatus` | Deployment | Retrieves current `ExecutionState` for a `deployment_id`. |
| `ListDeployments` | Deployment | Lists deployments, filterable by `intent_id`, `environment`, `lifecycle_state`. |
| `RequestRollback` | Deployment | Creates a new `DeploymentContext` with `rollback_of` set, targeting a previous `engineering_version` of the same `intent_id`. Goes through the same Approval Workflow as any other `RequestDeployment`. |
| `ApproveDeployment` / `DenyDeployment` | Approval | Resolves a `PENDING_APPROVAL` `ExecutionState` — the precise, unambiguous trigger point the Approval Workflow ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)) creates: transitions `DeploymentContext.approval_state` from `pending` to `approved`/`denied`, and `ExecutionState.lifecycle_state` from `PENDING_APPROVAL` to `ACCEPTED`/`FAILED`. Calling this against a `DeploymentContext` not currently in `PENDING_APPROVAL` is a no-op error — there is nothing to resolve. |
| `ListDomains` | Domain | Lists currently known `domain_id` values and, once it exists, the Domain Provider Specification version each conforms to. |
| `GetHealth` / `GetReadiness` / `GetVersion` | — (meta, not a Contract #1 resource) | Already implemented today in the Platform API skeleton (`lab/docker/platform-api/app/main.py`) — unaffected by this specification. |

---

# 6. Request/Response Contracts

- Every write Operation (`SubmitIntent`, `RequestDeployment`, `ApproveDeployment`, `RequestRollback`) returns the resulting resource representation — the `CanonicalIntent` or `DeploymentContext`/`ExecutionState` composite — never a bare acknowledgement.
- Every read Operation returns the resource representation or a not-found error (Section 7).
- Request and response bodies for Intent/Deployment operations **are** the Contract #1 objects, transported as-is (`CanonicalIntent`, `DeploymentContext`, `ExecutionState` JSON), not re-wrapped in a bespoke API-specific shape. Any transport envelope (pagination cursors for `List*`, etc.) wraps these objects rather than replacing their fields.

---

# 7. Error Model

All errors follow [RFC 7807 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc7807) as the base shape, with platform-specific extensions:

| Field | Source | Notes |
|---|---|---|
| `type`, `title`, `status`, `detail`, `instance` | RFC 7807 base | Standard fields. |
| `correlation_id` | Extension | Always present — see Section 10. |
| `error_code` | Extension | Stable, platform-specific code (e.g. `SCHEMA_VALIDATION_FAILED`, `TECHNICAL_POLICY_DENIED`, `DEPLOYMENT_DENIED`, `UNKNOWN_DOMAIN`, `INTENT_NOT_FOUND`). |
| `validation_errors` | Extension, present only for schema failures | List of field-level errors from Intent Translation's schema validation step. |
| `policy_reasons` | Extension, present only for `TECHNICAL_POLICY_DENIED` | The Technical Policy Engine's ([ADR-014](../03-Decisions/ADR-014-Policy-Enforcement.md)) reasons for denying a `SubmitIntent` call. Never present alongside `DEPLOYMENT_DENIED` — the two error codes are mutually exclusive because they come from different phases of different lifecycles. |
| `approval_reasons` | Extension, present only for `DEPLOYMENT_DENIED` | Directly reuses `ExecutionState.approval_reasons` (Contract #1) — the Approval Workflow's ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)) reasons for an outright `RequestDeployment` denial. The same data the caller could retrieve via `GetDeploymentStatus`, surfaced immediately in the denial response instead. Not returned for a `PENDING_APPROVAL` response — that is a `202`, not an error. |

Neither `TECHNICAL_POLICY_DENIED` nor `DEPLOYMENT_DENIED` is a server error (never 5xx) — both are a correctly-functioning platform declining a request, always 4xx (409 Conflict is recommended for the eventual REST binding, though this specification does not mandate a specific HTTP status; it mandates the `error_code` and reasons field exist regardless of transport).

---

# 8. Versioning Strategy

Two independent versioning axes exist and must never be conflated:

1. **API versioning** — the Platform API's own interface changing over time (an Operation's shape changes, a field is removed). This is a Platform Gateway responsibility (ADR-004). Path-based versioning (e.g. a `v1` prefix in the eventual REST binding) is recommended for explicitness, but the mechanism is a transport concern deferred to the OpenAPI derivation step.
2. **`engineering_version`** — Contract #1's per-intent revision number. This has nothing to do with API versioning; it exists whether the Platform API is on its first interface version or its tenth.

Implementations must never use the same version number or scheme for both.

---

# 9. Idempotency

`SubmitIntent` and `RequestDeployment` (the two Operations that create new resources) must accept an idempotency key from the caller. If a request is retried with the same idempotency key (e.g. after a client-side network timeout where the caller cannot tell whether the original request succeeded), the Platform API must return the **original** result rather than creating a duplicate `CanonicalIntent` or `DeploymentContext`.

This is distinct from `engineering_version` incrementing: an idempotency key protects against *accidental duplicate submission of the same request*; a new `engineering_version` represents *genuinely new desired state*, submitted deliberately. Clients must not conflate "retry my last request" with "submit a revision" — these are different Operations with different keys.

The idempotency key's scope is caller-supplied; if a caller cannot supply one, the Platform API is not required to synthesize a substitute — an un-keyed request has no idempotency guarantee, matching common REST API conventions.

---

# 10. Correlation IDs

`DeploymentContext.correlation_id` (Contract #1) is the join key across every log, event, and trace a single deployment attempt produces.

- A caller **may** supply a correlation ID (so an external system's own tracing ID, e.g. a Jira ticket key, threads through the platform); otherwise the Platform API generates one.
- The correlation ID is echoed in every response for that deployment, including every Error Model response (Section 7).
- The correlation ID does **not** identify the Intent — only the deployment attempt. Two different `RequestDeployment` calls against the same `CanonicalIntent` have two different correlation IDs.

---

# 11. Authentication and Authorization

Ownership: **Platform Gateway** (ADR-004). This specification defines the requirement, not the technology (per the Security Architecture document's existing technology independence — OAuth2/OIDC/Entra ID are candidates, not decisions made here).

- Every request must present a verifiable identity. Unauthenticated requests never reach Intent Translation.
- Authorization is role-based, using the roles already named in `10-Platform-Security-Architecture.md` (Platform Administrator, Network Architect, Network Engineer, Operations Engineer, Read-Only User, AI Service Account, CI/CD Service Account).
- Indicative minimum-role mapping (to be refined when RBAC is actually implemented — this specification establishes the principle, not the final table):

| Operation | Indicative minimum role |
|---|---|
| `GetIntent`, `ListIntents`, `GetDeploymentStatus`, `ListDeployments`, `ListDomains` | Read-Only User |
| `SubmitIntent`, `RequestDeployment` (non-production) | Network Engineer |
| `RequestDeployment` (production `environment`) | Network Engineer + satisfies `approval_state` per ADR-015 |
| `ApproveDeployment` / `DenyDeployment` | Platform Administrator (or a delegated approver role, not yet named) |
| `RequestRollback` | Network Engineer or above |

- AI Agents (ADR-010) authenticate as an **AI Service Account** role — never with elevated privilege relative to an equivalent human-submitted request. An AI Agent calling `SubmitIntent` is authorized exactly as a Network Engineer would be for the same Operation; ADR-010's "AI never bypasses governance" principle is enforced here by *not giving AI Agents a distinct, more permissive role*.

---

# 12. Relationship to Canonical Intent

The Platform API's entire purpose, restated precisely: it is the only component authorized to *produce* a `CanonicalIntent` (via `SubmitIntent`, persisted to Nautobot) or a `DeploymentContext`/`ExecutionState` (via `RequestDeployment`, persisted to the Workflow/Execution store — see [Platform Specification 03](03-Platform-Execution-Model-Specification.md), Persistence Boundary) that the rest of the platform will act on. Every Operation in Section 5 either creates, reads, or transitions one of Contract #1's three objects — there is no Platform API behavior that exists outside that model. This is intentional: it is what keeps the Platform API from re-accumulating scope beyond what ADR-004's Platform Gateway/Intent Translation split, and ADR-014/ADR-015's Technical Policy/Approval Workflow split, already bound it to.

---

# What This Contract Does Not Yet Define

- The actual OpenAPI document / FastAPI route implementation — to be derived from this specification once it is accepted, not designed in parallel with it.
- The Technical Policy Decision Contract (ADR-014) and the Deployment Approval Contract (ADR-015) — both referenced here (Section 3, 7) but not yet specified in their own right. These replace what was previously anticipated as a single "Policy Decision Contract."
- The Platform Events Specification (Tier 2) — `IntentSubmitted`, `DeploymentRequested`, and other event payloads are referenced but not yet schematized.
- The exact idempotency key transport mechanism (header name, TTL) — a transport-binding detail deferred to the OpenAPI derivation.
- The final RBAC role-to-operation table in Section 11 — indicative only, pending actual identity provider integration.
- The Workflow/Execution store that holds `DeploymentContext`/`ExecutionState` — named as distinct from Nautobot ([Platform Specification 03](03-Platform-Execution-Model-Specification.md), Persistence Boundary), but no specific technology or schema is chosen yet.
