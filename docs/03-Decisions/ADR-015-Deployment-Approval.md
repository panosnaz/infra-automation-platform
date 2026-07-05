# ADR-015 — Deployment Approval as a Distinct Capability from Technical Policy

**Status:** Accepted

**Date:** 2026-07-05

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-004 — Platform API as the Unified Platform Interface
- ADR-011 — Event-Driven Automation
- ADR-014 — Technical Policy Enforcement (OPA)

---

# Context

A Control Plane coherence review of Platform Specifications 01-03 (Canonical Intent, Platform API, Platform Execution Model) found that ADR-014's Policy Engine was answering two different questions under one name:

1. *Is this intent technically valid and compliant* — naming conventions, schema-level rules, organizational/compliance constraints. This question can be answered the moment a `CanonicalIntent` exists, independent of whether, when, or by whom it will ever be deployed.
2. *Is this specific deployment authorized right now* — production approval requirements, change windows, who is a valid approver. This question cannot be answered until a deployment is actually requested, because it depends on `DeploymentContext` fields (`environment`, `approval_state`, `requester`) that don't exist at intent-authoring time.

Collapsing both into a single "Policy Evaluation" step (as ADR-014 originally did, and as [Platform Specification 02](../11-Specifications/02-Platform-API-Specification.md) §3 originally drew it) produced a real defect: `RequestDeployment` ran the entire evaluation — including approval-requirement checks — synchronously in one call, with `ApproveDeployment`/`DenyDeployment` (already defined as API operations) having no window in which to ever be invoked. A production deployment requiring human approval could not actually flow through the pipeline as specified.

# Problem Statement

Should intent-level compliance and deployment-level authorization be evaluated by the same capability, at the same time, or are they separate concerns with separate owners, separate inputs, and separate timing?

# Decision

Deployment Approval is a distinct capability from Technical Policy (ADR-014), evaluated at a different time, against different inputs, by a different owner:

| | Technical Policy (ADR-014) | Deployment Approval (this ADR) |
|---|---|---|
| Question | Is this intent technically valid and compliant? | Is this specific deployment authorized right now? |
| Runs at | `SubmitIntent` (Intent Lifecycle) | `RequestDeployment` (Deployment Lifecycle) |
| Evaluates | `CanonicalIntent` alone | `DeploymentContext` (`environment`, `approval_state`, `requester`) |
| Outcome | allow / deny, gates whether `CanonicalIntent` is persisted at all | authorized / pending / denied, gates `ExecutionState.lifecycle_state` |
| An intent can... | exist for weeks or months with zero deployments, fully technically valid the entire time | be deployed, redeployed, and rolled back many times, each attempt independently authorized |

An intent's technical validity never expires and is never re-checked per deployment attempt. Its deployment authorization is evaluated fresh every time, because "is this allowed right now" is a function of time, environment, and human sign-off — none of which are properties of the intent itself.

---

# Responsibilities

The Approval Workflow owns:

- Determining whether a given `DeploymentContext.environment` requires human approval before deployment (e.g. production does, lab does not)
- Change window enforcement (is this a permitted time to deploy to this environment)
- Approval routing — who is a valid approver for a given environment/tenant (deferred detail — see Open Items)
- Recording `approval_state` transitions (`pending` → `approved` / `denied`) and `approved_by`/`approved_at` (Contract #1)

The Approval Workflow does **not**:

- Validate `CanonicalIntent` content, shape, or naming (Technical Policy's job, ADR-014)
- Transform or enrich `CanonicalIntent`/`DeploymentContext`
- Execute infrastructure changes
- Decide whether the underlying intent is technically sound — by the time a deployment is requested, Technical Policy has already answered that question once, permanently, at `SubmitIntent` time

---

# Architectural Position

```text
RequestDeployment
    │
    ▼
Create DeploymentContext + ExecutionState
    │
    ▼
Approval Workflow (this ADR) evaluates DeploymentContext.approval_state
    │
    ├── none_required, or already approved ──► lifecycle_state = ACCEPTED
    │                                                │
    │                                                ▼
    │                                     Publish Event (DeploymentRequested)
    │
    ├── pending (approval required, not yet given) ──► lifecycle_state = PENDING_APPROVAL
    │                                                        │
    │                                                        ▼
    │                                    (later) ApproveDeployment / DenyDeployment
    │                                          │                          │
    │                                     approved                     denied
    │                                          │                          │
    │                                          ▼                          ▼
    │                                lifecycle_state = ACCEPTED   lifecycle_state = FAILED
    │                                          │
    │                                          ▼
    │                               Publish Event (DeploymentRequested)
    │
    └── outright denial (e.g. quota exceeded, environment restriction) ──► lifecycle_state = FAILED
```

See [Platform Specification 02 — Platform API](../11-Specifications/02-Platform-API-Specification.md) §3 for the authoritative Deployment Lifecycle sequence this diagram summarizes, and [Platform Specification 03 — Platform Execution Model](../11-Specifications/03-Platform-Execution-Model-Specification.md) §§1-2 for the full `PENDING_APPROVAL` state definition and ownership.

---

# Why a Separate Capability Rather Than Extending Technical Policy

- **Different lifetimes.** Technical Policy's decision is permanent once an intent is persisted. Approval is re-evaluated per deployment attempt — the same intent can be deployed to lab (no approval) and later promoted to production (approval required) without ever being re-validated technically.
- **Different inputs.** Technical Policy only ever needs `CanonicalIntent`. Approval fundamentally needs `DeploymentContext` fields that don't exist until a deployment is requested — conflating them forced Policy Evaluation to run at the wrong time relative to `DeploymentContext`'s creation.
- **Resolves a real sequencing defect.** Without this split, there was no resting state between "`DeploymentContext` created" and "policy already evaluated," so `ApproveDeployment`/`DenyDeployment` — already-defined operations — had no valid moment to be called. `PENDING_APPROVAL` (Contract #3) only becomes representable once Approval is its own phase with its own asynchronous resolution path.
- **Matches OPA's own strengths differently.** Technical Policy (ADR-014) is a good fit for Rego's declarative, stateless allow/deny evaluation. Approval routing and change-window enforcement are stateful, human-in-the-loop, and time-dependent — a different implementation shape than Technical Policy's Rego rules is expected here.

---

# Open Items

- The Deployment Approval Contract (a future Platform Specification, alongside a Technical Policy Decision Contract for ADR-014) — this ADR establishes the responsibility boundary and timing, not the request/response shape of an approval decision or the approver-routing data model.
- Where `DeploymentContext`/`ExecutionState`, including `approval_state`/`PENDING_APPROVAL`, are actually persisted — see [Platform Specification 03](../11-Specifications/03-Platform-Execution-Model-Specification.md)'s Persistence Boundary section (Workflow/Execution domain, not Nautobot).

---

# Implementation Status

Not yet implemented (0%), as of 2026-07-05. No approval routing, change-window enforcement, or `PENDING_APPROVAL` handling exists anywhere in the codebase. This ADR establishes the responsibility boundary in advance of implementation, consistent with how ADR-014 was recorded before its own implementation began.
