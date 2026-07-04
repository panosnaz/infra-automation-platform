# ADR-014 — Policy Enforcement (OPA)

**Status:** Accepted

**Date:** 2026-07-04

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-004 — Platform API as the Unified Platform Interface
- ADR-005 — Workflow Orchestration
- ADR-006 — Platform Control Plane as the Single Orchestration Layer
- ADR-007 — Cisco NetAsCode as the Canonical Engineering Model
- ADR-011 — Event-Driven Automation

---

# Context

Policy — naming conventions, environment restrictions, tenant quotas, change windows, production approval requirements, organizational and compliance rules — has been drawn as a first-class architectural layer since the earliest diagrams (`03c-Platform-Control-Plane.md`'s "Policy & Intent Validation" layer, the Technology Architecture capability matrix's "Policy | Open Policy Agent" row). Every other capability drawn at that level of prominence — Validation (ADR-008), Secrets (ADR-012), Observability (ADR-013) — already has a decision record. Policy did not.

In the absence of a decision record, ADR-004 (Platform API) had independently claimed "Policy Enforcement" as one of its own Business Logic responsibilities, creating an unresolved overlap between two components that both appeared to own policy: the Platform API and a separately-diagrammed OPA layer.

This ADR resolves that overlap and gives Policy the same standing as every other cross-cutting capability.

---

# Problem Statement

Who evaluates whether a Canonical Intent is *allowed*, as opposed to whether it is merely *well-formed*?

Should the Platform API evaluate business/compliance rules inline as part of its own request-handling code, or should policy evaluation be delegated to an independent Policy Engine?

---

# Decision

The platform shall implement Policy Enforcement as an independent capability, using Open Policy Agent (OPA), evaluated as a distinct step in the request pipeline — after Intent Translation produces a Canonical Intent, and before that Canonical Intent is persisted to Nautobot.

The Platform API orchestrates the call to the Policy Engine. It does not own policy rules or evaluation logic itself.

---

# Responsibility Boundary

Three questions are asked, in order, by three different owners. This is the resolution to the ambiguity between ADR-004 and the Policy layer shown in `03c-Platform-Control-Plane.md`.

| Question | Owner | Example |
|---|---|---|
| Is this request from an authenticated, authorized principal? | Platform Gateway ([ADR-004](ADR-004-Platform-API.md)) | Invalid token; caller lacks the required role |
| Can this request be understood? | Intent Translation ([ADR-004](ADR-004-Platform-API.md)) | Missing required field; malformed schema |
| Should this request be allowed? | **Policy Engine (this ADR)** | Tenant name violates naming convention; production change outside an approved window; tenant quota exceeded |

Rule of thumb: **Intent Translation validates shape. Policy validates permission.** Neither substitutes for the other, and neither should absorb the other's rules over time.

---

# Responsibilities

The Policy Engine owns:

- Naming convention enforcement
- Environment restrictions (e.g. production vs. lab constraints)
- Tenant / resource quotas
- Change window enforcement
- Production approval requirements
- Organizational and compliance rules

The Policy Engine does **not**:

- Transform, normalize, or enrich data (that is Intent Translation's job)
- Authenticate or authorize the caller (that is the Platform Gateway's job)
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
Policy Evaluation (OPA)
    ↓
Persist to Nautobot
    ↓
Publish Event (IntentReceived)
```

A `deny` decision from the Policy Engine stops the pipeline before Nautobot is ever written to and before any event is published — a denied request produces no platform state change and no `IntentReceived` event.

---

# Why a Separate Policy Engine Rather Than Inline Rules

Embedding policy rules directly in Platform API code was considered and rejected:

- Policy rules change independently of API code (a new naming convention or quota shouldn't require a Platform API deployment).
- Policy rules need their own review/approval process, distinct from application code review.
- OPA's Rego language is purpose-built for this class of allow/deny decision and is independently testable.
- Keeping policy external prevents the Platform API from re-accumulating the very responsibility sprawl ADR-004 was just refactored to avoid (see ADR-004's Platform Gateway / Intent Translation split).

---

# Implementation Status

Not yet implemented (0%), as of 2026-07-04. No OPA instance, no Rego policies, and no policy-evaluation call exist anywhere in the codebase — the Platform API skeleton (`lab/docker/platform-api/`) currently exposes only `/health`, `/readiness`, and `/version`. This ADR establishes the responsibility boundary in advance of implementation so the Platform API does not have to be refactored later. See [`01-Current-State.md`](../01-Vision/01-Current-State.md) Pending Items.
