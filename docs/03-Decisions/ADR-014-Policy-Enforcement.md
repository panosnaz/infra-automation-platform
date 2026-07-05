# ADR-014 — Technical Policy Enforcement (OPA)

**Status:** Accepted

**Date:** 2026-07-04 (rescoped 2026-07-05 — see ADR-015)

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-004 — Platform API as the Unified Platform Interface
- ADR-005 — Workflow Orchestration
- ADR-006 — Platform Control Plane as the Single Orchestration Layer
- ADR-007 — Cisco NetAsCode as the Canonical Engineering Model
- ADR-011 — Event-Driven Automation
- ADR-015 — Deployment Approval as a Distinct Capability from Technical Policy

---

# Context

Policy — naming conventions, environment restrictions, tenant quotas, change windows, production approval requirements, organizational and compliance rules — has been drawn as a first-class architectural layer since the earliest diagrams (`03c-Platform-Control-Plane.md`'s "Policy & Intent Validation" layer, the Technology Architecture capability matrix's "Policy | Open Policy Agent" row). Every other capability drawn at that level of prominence — Validation (ADR-008), Secrets (ADR-012), Observability (ADR-013) — already has a decision record. Policy did not.

In the absence of a decision record, ADR-004 (Platform API) had independently claimed "Policy Enforcement" as one of its own Business Logic responsibilities, creating an unresolved overlap between two components that both appeared to own policy: the Platform API and a separately-diagrammed OPA layer.

This ADR resolves that overlap and gives Policy the same standing as every other cross-cutting capability.

> **Rescoped 2026-07-05:** A Control Plane coherence review found this ADR's original Responsibilities list conflated two different questions — *is this intent technically valid* and *is this specific deployment authorized right now*. The second question was split out into [ADR-015 — Deployment Approval](ADR-015-Deployment-Approval.md). This ADR now covers Technical Policy only: evaluated once, at `SubmitIntent` time, against `CanonicalIntent` alone.

---

# Problem Statement

Who evaluates whether a Canonical Intent is *technically valid and compliant*, as opposed to whether it is merely *well-formed*, or whether a specific deployment of it is *currently authorized*?

Should the Platform API evaluate business/compliance rules inline as part of its own request-handling code, or should policy evaluation be delegated to an independent Policy Engine?

---

# Decision

The platform shall implement Technical Policy Enforcement as an independent capability, using Open Policy Agent (OPA), evaluated as a distinct step in the **Intent Lifecycle** — after Intent Translation produces a Canonical Intent, and before that Canonical Intent is persisted to Nautobot, at `SubmitIntent` time. It runs exactly once per `CanonicalIntent` (per `engineering_version`) and is never re-evaluated per deployment attempt — see ADR-015 for the deployment-scoped question this does not answer.

The Platform API orchestrates the call to the Policy Engine. It does not own policy rules or evaluation logic itself.

---

# Responsibility Boundary

Four questions are asked, in order, by four different owners — the fourth added by [ADR-015](ADR-015-Deployment-Approval.md).

| Question | Owner | Example |
|---|---|---|
| Is this request from an authenticated, authorized principal? | Platform Gateway ([ADR-004](ADR-004-Platform-API.md)) | Invalid token; caller lacks the required role |
| Can this request be understood? | Intent Translation ([ADR-004](ADR-004-Platform-API.md)) | Missing required field; malformed schema |
| Is this intent technically valid and compliant? | **Technical Policy Engine (this ADR)**, at `SubmitIntent` time | Tenant name violates naming convention; organizational compliance rule violated |
| Is this specific deployment authorized right now? | Approval Workflow ([ADR-015](ADR-015-Deployment-Approval.md)), at `RequestDeployment` time | Production change outside an approved window; approval still pending |

Rule of thumb: **Intent Translation validates shape. Technical Policy validates intent-level compliance. Approval Workflow validates deployment-time authorization.** None of the three substitutes for another, and none should absorb another's rules over time.

---

# Responsibilities

The Technical Policy Engine owns:

- Naming convention enforcement
- Environment-admissibility rules (e.g. a construct that is never allowed to target production, independent of *when* it is deployed there)
- Tenant / resource quotas
- Organizational and compliance rules

The Technical Policy Engine does **not**:

- Transform, normalize, or enrich data (that is Intent Translation's job)
- Authenticate or authorize the caller (that is the Platform Gateway's job)
- Determine whether a specific deployment is authorized right now — change windows, production approval sign-off (that is the Approval Workflow's job, [ADR-015](ADR-015-Deployment-Approval.md))
- Persist Canonical Intent to Nautobot
- Publish platform events
- Execute infrastructure changes

OPA evaluates a Canonical Intent and returns an allow/deny decision, optionally with reasons. It never mutates the Canonical Intent it is given.

---

# Architectural Position

```text
Platform Gateway
    ↓
Intent Translation
    ↓
Canonical Intent
    ↓
Technical Policy Evaluation (this ADR)
    ↓
Persist Canonical Intent to Nautobot
    ↓
Publish Event (IntentSubmitted)
```

This diagram is illustrative only — see [Platform Specification 02 — Platform API](../11-Specifications/02-Platform-API-Specification.md) §3 for the authoritative Intent Lifecycle sequence. A `deny` decision from the Technical Policy Engine stops the pipeline before Nautobot is ever written to and before any event is published — a denied request produces no `CanonicalIntent`, no platform state change, and no `IntentSubmitted` event.

---

# Why a Separate Policy Engine Rather Than Inline Rules

Embedding policy rules directly in Platform API code was considered and rejected:

- Policy rules change independently of API code (a new naming convention or quota shouldn't require a Platform API deployment).
- Policy rules need their own review/approval process, distinct from application code review.
- OPA's Rego language is purpose-built for this class of allow/deny decision and is independently testable.
- Keeping policy external prevents the Platform API from re-accumulating the very responsibility sprawl ADR-004 was just refactored to avoid (see ADR-004's Platform Gateway / Intent Translation split).

---

# Implementation Status

Not yet implemented (0%), as of 2026-07-05. No OPA instance, no Rego policies, and no Technical Policy evaluation call exist anywhere in the codebase — the Platform API skeleton (`lab/docker/platform-api/`) currently exposes only `/health`, `/readiness`, and `/version`. This ADR establishes the responsibility boundary in advance of implementation so the Platform API does not have to be refactored later. See [`01-Current-State.md`](../01-Vision/01-Current-State.md) Pending Items.
