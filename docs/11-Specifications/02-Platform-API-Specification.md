---
title: "Platform Specification 02 — Platform API"
description: "Contract #2 from the Platform Specification Roadmap: the Platform API as a capability, independent of any REST/OpenAPI implementation"
---

# Platform Specification 02 — Platform API

**Status:** Accepted

**Date:** 2026-07-04

**Decision Makers:** Platform Engineering Team

**Type:** Platform Specification (not an ADR — this is a contract implementing decisions already made in [ADR-004](../03-Decisions/ADR-004-Platform-API.md), [ADR-014](../03-Decisions/ADR-014-Policy-Enforcement.md), [ADR-010](../03-Decisions/ADR-010-AI-Engineering-Assistant.md), and [Platform Specification 01 — Canonical Intent](01-Canonical-Intent-Specification.md))

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
- Invoking Policy Evaluation (ADR-014) and acting on its allow/deny decision
- Persisting approved Canonical Intent to Nautobot
- Publishing platform events (`IntentReceived`, etc. — Platform Events Specification, not yet drafted)

The Platform API does **not** own:

- Infrastructure execution (Terraform/Ansible — ADR-002/003)
- Policy rule evaluation logic itself (OPA — ADR-014)
- Workflow sequencing across multiple tasks (Workflow Engine — ADR-005)
- Validation execution (pyATS/Catfish — ADR-008)

The Platform API is an **orchestrating front door**, not an execution engine. Every write it accepts results in, at most, one Nautobot write and one published event — it never calls Terraform, Ansible, or pyATS directly.

---

# 2. Entry Points

Per ADR-010's "many entry points, one execution path" principle, the Platform API is transport-agnostic at the capability level. REST is the first entry point; CLI, Jira, ServiceNow, Git, and AI Agents are future entry points that must produce the *same* internal request shape.

An entry point's only job is translating its native format (a Jira ticket transition, a CLI flag set, an AI agent's structured tool call) into a call against the Operations defined in Section 5. The Platform API itself does not know or special-case which entry point originated a request beyond recording it — `DeploymentContext.entry_point` (Contract #1) already carries this as a plain string (`"cli"`, `"jira"`, `"ai_agent"`, `"rest"`), not as a different code path per entry point.

**Consequence for implementation:** business logic must never be written "for the REST API" — it is written once, for the Operations, and every entry point (present or future) calls the same Operations.

---

# 3. Request Lifecycle

Two distinct phases exist, with different synchrony guarantees. **The full lifecycle state machine, state ownership, and event-timing rules this section relies on are formalized in [Platform Specification 03 — Platform Execution Model](03-Platform-Execution-Model-Specification.md).** This section describes the request-handling flow; that document is authoritative for the state semantics.

## Phase A — Submission (synchronous from the caller's perspective)

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
Canonical Intent             (Platform Specification 01)
    │
    ▼
Policy Evaluation (OPA)      (ADR-014)
    │
    ├── deny ──────────────► Response: 4xx with policy_reasons — pipeline stops here.
    │                         No Nautobot write. No event published.
    │
    └── allow
         │
         ▼
    Persist to Nautobot           (ExecutionState.lifecycle_state -> ACCEPTED)
         │
         ▼
    Publish Event (IntentReceived)
         │
         ▼
    Response: 201/202 with CanonicalIntent + DeploymentContext (deployment_id, correlation_id)
```

Submission is synchronous end-to-end: the caller receives a response only after Policy Evaluation and (if allowed) the Nautobot write and event publication complete. This keeps the contract simple — callers never have to poll to find out whether their submission was even accepted.

## Phase B — Execution (asynchronous)

Actual infrastructure deployment (Terraform/Ansible execution, triggered by whatever subscribes to `IntentReceived`) happens **after** the submission response has already been returned. The caller tracks progress via `ExecutionState` (Contract #1), retrieved through the `GetDeploymentStatus` operation (Section 5) — by polling today, by webhook/event subscription once the Platform Events Specification and a notification mechanism exist.

**This means:** a `201`/`202` response from submission means *"your request was validated, allowed, and recorded"* — it does not mean *"your infrastructure now exists."* This distinction must be explicit in every client integration.

---

# 4. API Resources

Resource-oriented, not verb-oriented — these are the nouns the Platform API exposes, independent of HTTP/REST specifics.

| Resource | Backed by (Contract #1) | Description |
|---|---|---|
| **Intent** | `CanonicalIntent` | A specific, immutable revision of desired engineering state. |
| **Deployment** | `DeploymentContext` + `ExecutionState` (composed view) | One attempt to realize an Intent — request metadata plus current execution status. |
| **Domain** | `KNOWN_DOMAINS` (interim) / future Domain Provider Registry | Read-only: which domain providers exist and what they accept as `domain_intent`. |
| **Approval** | `DeploymentContext.approval_state` transition | The act of approving or denying a pending Deployment. |

Deliberately **not** a resource: `Policy`. Policy is evaluated as a side effect of creating a Deployment (Section 5); it is not something a client creates, reads, or lists independently through this API. (OPA may expose its own management API — that is out of scope for the Platform API.)

---

# 5. Operations

| Operation | Resource | Effect |
|---|---|---|
| `SubmitIntent` | Intent | Creates a new `CanonicalIntent` (new `intent_id` if first submission, new `engineering_version` if revising an existing `intent_id`). Does **not** trigger Policy Evaluation or deployment by itself — see `RequestDeployment`. |
| `GetIntent` | Intent | Retrieves a specific `(intent_id, engineering_version)`. |
| `ListIntents` | Intent | Lists intents, filterable by `owner`, `domain_id`, `tags`. |
| `GetIntentLineage` | Intent | Retrieves the `previous_version` chain for an `intent_id` — the full revision history. |
| `RequestDeployment` | Deployment | Creates a `DeploymentContext` against an existing `(intent_id, engineering_version)`; runs the full Request Lifecycle (Section 3) including Policy Evaluation. |
| `GetDeploymentStatus` | Deployment | Retrieves current `ExecutionState` for a `deployment_id`. |
| `ListDeployments` | Deployment | Lists deployments, filterable by `intent_id`, `environment`, `lifecycle_state`. |
| `RequestRollback` | Deployment | Creates a new `DeploymentContext` with `rollback_of` set, targeting a previous `engineering_version` of the same `intent_id`. |
| `ApproveDeployment` / `DenyDeployment` | Approval | Transitions `DeploymentContext.approval_state` from `pending`. Only meaningful before `RequestDeployment`'s Policy Evaluation has run, or as a gate Policy Evaluation itself checks (see ADR-014 — "production approval requirements"). |
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
| `error_code` | Extension | Stable, platform-specific code (e.g. `SCHEMA_VALIDATION_FAILED`, `POLICY_DENIED`, `UNKNOWN_DOMAIN`, `INTENT_NOT_FOUND`). |
| `validation_errors` | Extension, present only for schema failures | List of field-level errors from Intent Translation's schema validation step. |
| `policy_reasons` | Extension, present only for `POLICY_DENIED` | Directly reuses `ExecutionState.policy_reasons` (Contract #1) — the same data the caller could retrieve via `GetDeploymentStatus`, surfaced immediately in the denial response instead. |

A `POLICY_DENIED` error is not a server error (never 5xx) — it is a correctly-functioning platform declining a request, always 4xx (409 Conflict is recommended for the eventual REST binding, though this specification does not mandate a specific HTTP status; it mandates the `error_code` and `policy_reasons` fields exist regardless of transport).

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
| `RequestDeployment` (production `environment`) | Network Engineer + satisfies `approval_state` per ADR-014 |
| `ApproveDeployment` / `DenyDeployment` | Platform Administrator (or a delegated approver role, not yet named) |
| `RequestRollback` | Network Engineer or above |

- AI Agents (ADR-010) authenticate as an **AI Service Account** role — never with elevated privilege relative to an equivalent human-submitted request. An AI Agent calling `SubmitIntent` is authorized exactly as a Network Engineer would be for the same Operation; ADR-010's "AI never bypasses governance" principle is enforced here by *not giving AI Agents a distinct, more permissive role*.

---

# 12. Relationship to Canonical Intent

The Platform API's entire purpose, restated precisely: it is the only component authorized to *produce* a `CanonicalIntent` (via `SubmitIntent`) or a `DeploymentContext` (via `RequestDeployment`) that Nautobot will accept and the rest of the platform will act on. Every Operation in Section 5 either creates, reads, or transitions one of Contract #1's three objects — there is no Platform API behavior that exists outside that model. This is intentional: it is what keeps the Platform API from re-accumulating scope beyond what ADR-004's Platform Gateway/Intent Translation split already bounds it to.

---

# What This Contract Does Not Yet Define

- The actual OpenAPI document / FastAPI route implementation — to be derived from this specification once it is accepted, not designed in parallel with it.
- The Policy Decision Contract (Tier 1 #3) — referenced here (Section 3, 7) but not yet specified in its own right.
- The Platform Events Specification (Tier 2) — `IntentReceived` and other event payloads are referenced but not yet schematized.
- The exact idempotency key transport mechanism (header name, TTL) — a transport-binding detail deferred to the OpenAPI derivation.
- The final RBAC role-to-operation table in Section 11 — indicative only, pending actual identity provider integration.
