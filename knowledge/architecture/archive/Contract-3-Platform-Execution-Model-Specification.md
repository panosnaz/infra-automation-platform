---
title: "Platform Specification 03 — Platform Execution Model"
description: "Contract #3: the system-wide lifecycle, state ownership, and event timing models every other contract depends on"
type: architecture
domain: platform
status: historical
tags: [contract]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# Platform Specification 03 — Platform Execution Model

**Status:** Accepted

**Date:** 2026-07-05

**Decision Makers:** Platform Engineering Team

**Type:** Platform Specification (not an ADR — this formalizes and elevates a principle already implied by [ADR-011](../03-Decisions/ADR-011-Event-Driven-Automation.md), and resolves a terminology collision found while cross-checking [Contract #1](01-Canonical-Intent-Specification.md) against [ADR-001](../03-Decisions/ADR-001-Nautobot-Source-of-Truth.md))

**This document is the authoritative specification.** [`platform/canonical_intent/models.py`](../../platform/canonical_intent/models.py)'s `LifecycleState` enum and `ExecutionState.desired_version`/`applied_version` fields are the reference implementation of this specification.

> **Revised 2026-07-05 (Control Plane coherence review):** the original version of this contract described a single `ACCEPTED` transition gated by "Policy Evaluation." That has been superseded by [ADR-014](../03-Decisions/ADR-014-Policy-Enforcement.md) (Technical Policy, evaluated during the separate Intent Lifecycle, never producing an `ExecutionState` transition at all) and [ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md) (Approval Workflow, the actual gate on `ACCEPTED`). This revision also adds the `PENDING_APPROVAL` state and an explicit Persistence Boundary (§5) resolving where `ExecutionState` actually lives.

---

# Purpose

This is a **stabilization contract**, written before the Technical Policy Decision Contract and Deployment Approval Contract deliberately: both are themselves state transitions (Contract #2, Request Lifecycle), and neither can be specified correctly against ambiguous lifecycle, ownership, or event-timing semantics. This document resolves those three cross-cutting models once, so every subsequent contract (Technical Policy Decision, Deployment Approval, Validation, Platform Events, Domain Provider) builds on the same foundation instead of each silently assuming its own.

---

# 1. System-Wide Lifecycle Model

## Externally visible lifecycle

`ExecutionState.lifecycle_state` (Contract #1) exposes exactly these eight states — no more:

| State | Meaning | Sync/Async | Persisted |
|---|---|---|---|
| `PENDING_APPROVAL` | `RequestDeployment` was accepted and recorded, but the Approval Workflow ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)) requires human approval not yet given. A resting state. | Synchronous entry, asynchronous resolution | Yes |
| `ACCEPTED` | The Approval Workflow authorized this deployment — either immediately (no approval required) or by resolving a `PENDING_APPROVAL` rest. | Synchronous or asynchronous (see above) | Yes |
| `DEPLOYING` | Terraform/Ansible execution in progress. | Asynchronous | Yes |
| `VALIDATING` | pyATS/Catfish validation in progress. | Asynchronous | Yes |
| `STABLE` | Validation confirmed `applied_version` matches `desired_version`. Steady state. | Asynchronous | Yes |
| `DRIFTED` | Live infrastructure no longer matches `applied_version`'s desired state. | Asynchronous, recurring | Yes |
| `FAILED` | Approval Workflow denied the request, OR deployment/validation failed. | Either | Yes (see Persistence Boundary, §5) |
| `RETIRED` | Intent's infrastructure has been deliberately decommissioned. | Synchronous request, async teardown | Yes |

## Internal implementation steps are not lifecycle states

Intent Translation and Technical Policy ([ADR-014](../03-Decisions/ADR-014-Policy-Enforcement.md)) belong to the separate **Intent Lifecycle** (`SubmitIntent`, [Contract #2](02-Platform-API-Specification.md) §3) and happen entirely **before** any `ExecutionState` exists — they are not folded into any state in the table above, they simply precede this state machine altogether. Within the **Deployment Lifecycle** itself, only the Approval Workflow's evaluation is folded into the transition into `PENDING_APPROVAL`/`ACCEPTED` as implementation detail; no external caller, subscriber, or Knowledge Layer entry needs to know how that evaluation is internally implemented, only that it resolves to one of the two states.

**Rationale for this simplification:** exposing implementation stages as lifecycle states couples every subscriber to the Platform API's internal pipeline shape. Eight stable, meaningful, user-facing states are the contract; how each is internally reached is not.

## Persisted vs. transient

Everything in the table above is persisted once reached. The only genuinely transient data is a request that never becomes a `CanonicalIntent` at all (fails schema validation in Intent Translation, or is denied by Technical Policy at `SubmitIntent` time) — it produces an error response ([Contract #2](02-Platform-API-Specification.md) §7) and nothing durable in Nautobot, though a Technical Policy denial is still recorded in the audit log (§5).

An **outright-denied** `RequestDeployment` (Approval Workflow returns deny without ever resting at `PENDING_APPROVAL` — e.g. quota exceeded) does create a `DeploymentContext`/`ExecutionState` and reaches `FAILED` directly. A `PENDING_APPROVAL` deployment that is later denied via `DenyDeployment` also reaches `FAILED`. Both are persisted to the Workflow/Execution store (§5) — `FAILED` is not the same thing as "nothing happened."

---

# 2. State Ownership Model

| Transition | Owner | Trigger |
|---|---|---|
| (none) → `PENDING_APPROVAL` | Platform API / Approval Workflow ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)) | Synchronous, direct call (`RequestDeployment`), when approval is required and not yet given |
| (none) → `ACCEPTED` | Platform API / Approval Workflow ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)) | Synchronous, direct call (`RequestDeployment`), when approval is not required or was already granted |
| (none) → `FAILED` | Approval Workflow ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)) | Synchronous, direct call (`RequestDeployment`), outright denial (e.g. quota exceeded) |
| `PENDING_APPROVAL` → `ACCEPTED` | Approval Workflow ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)), via `ApproveDeployment` | Synchronous, direct call |
| `PENDING_APPROVAL` → `FAILED` | Approval Workflow ([ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md)), via `DenyDeployment` | Synchronous, direct call |
| `ACCEPTED` → `DEPLOYING` | Execution Plane (Terraform/Ansible), invoked by the Workflow Engine | Asynchronous, reacts to `DeploymentRequested` |
| `DEPLOYING` → `VALIDATING` | Validation (pyATS/Catfish) | Asynchronous, reacts to `DeploymentCompleted` |
| `VALIDATING` → `STABLE` | Validation — sets `applied_version = desired_version` on success | Asynchronous |
| `VALIDATING` → `FAILED` | Validation — on validation failure | Asynchronous |
| `STABLE` → `DRIFTED` | Validation (Continuous Compliance, ADR-008) | Asynchronous, scheduled or event-driven |
| `DRIFTED` → `STABLE` | Validation, **only** after a new forward-authored `CanonicalIntent` resolves the drift (never by re-running drift detection alone — see [ADR-001's Brownfield Onboarding Exception](../03-Decisions/ADR-001-Nautobot-Source-of-Truth.md)) | Asynchronous |
| `DEPLOYING` → `FAILED` | Execution Plane (deployment failure) | Asynchronous |
| (any) → `RETIRED` | Platform API | Synchronous request, async teardown |

No component ever transitions `ExecutionState` on another component's behalf. The Workflow Engine, in particular, **orchestrates** the `ACCEPTED → DEPLOYING` reaction but does not itself own the transition — the Execution Plane (Terraform/Ansible) does, since it is the actual action that makes `DEPLOYING` true. Similarly, the Platform API orchestrates the *call* to the Approval Workflow but does not itself decide authorization — [ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md) owns that decision.

---

# 3. Event Timing Model

## Principle: Events Are Facts, Not Commands

**Elevated to a platform-wide architectural principle**, applying to every event named in [ADR-011](../03-Decisions/ADR-011-Event-Driven-Automation.md):

> Every event represents a **completed** state transition. No event is an instruction. Subscribers decide independently whether and how to react; a publisher's event never dictates a subscriber's internal behavior.

This is what makes ADR-011's decoupling claim ("event publishers do not know or care who is listening") actually true rather than aspirational: if an event *told* a subscriber what to do, the publisher would be implicitly coupled to the subscriber's state machine. Instead, the chain is always:

```text
Component performs a transition it owns (Section 2)
        │
        ▼
Component publishes an event announcing that transition already happened
        │
        ▼
Subscriber(s) independently decide to react
        │
        ▼
Each reacting subscriber performs and owns ITS OWN transition (Section 2)
        │
        ▼
That subscriber publishes ITS OWN event
        │
        ▼
        ... (chain continues)
```

## Principle: Events Are Published Only After the Transition Is Committed

An event for a transition is published **strictly after** that transition has been durably committed (Section 1's "persisted" column) — never before, never speculatively. A subscriber must always be able to trust that observing an event means the corresponding state is real and durable, not a state that might still be rolled back.

**Consequence:** `IntentSubmitted` is published after the Nautobot write inside the Intent Lifecycle succeeds, not before. `DeploymentRequested` is published after `ACCEPTED` is durably recorded — whether reached immediately or after a `PENDING_APPROVAL` rest resolves — not before. `DeploymentCompleted` is published after `DEPLOYING` → `VALIDATING` is durably recorded, not while Terraform is still applying. This is a stricter reading than some event-driven systems use (some publish "in-flight" events for progress reporting) — this platform deliberately does not, to keep "an event exists" and "the state is real" equivalent, simplifying every subscriber's correctness reasoning.

## Consequence for Contract #2's two lifecycles

The Intent Lifecycle (`SubmitIntent`) is **entirely event-free** until it completes — Intent Translation, Technical Policy, and the Nautobot write are direct synchronous calls within one Platform API request. `IntentSubmitted` fires once, at the end of that lifecycle; no `ExecutionState` exists at any point during it.

The Deployment Lifecycle (`RequestDeployment`) is synchronous through either `ACCEPTED` or `PENDING_APPROVAL`. `DeploymentRequested` — the event the Workflow Engine subscribes to — fires only once `ACCEPTED` is reached, whether that happens within the original `RequestDeployment` call (no approval required) or later, asynchronously, once `ApproveDeployment` resolves a `PENDING_APPROVAL` rest. Every subsequent transition (`DEPLOYING`, `VALIDATING`, `STABLE`, `DRIFTED`, `FAILED` after acceptance, `RETIRED`) is event-mediated, one reaction per step, per the chain above.

---

# 4. Desired Version vs. Applied Version

`ExecutionState` tracks two version numbers, not one:

| Field | Meaning | Set by | Updated when |
|---|---|---|---|
| `desired_version` | The `engineering_version` this execution is converging toward. | Platform API, at `ACCEPTED` | Never changes for this `ExecutionState` — a new desired version means a new `DeploymentContext`/`ExecutionState`. |
| `applied_version` | The `engineering_version` last **confirmed actually live** by Validation. | Validation, at `STABLE` | Set on first successful validation; left unchanged (not nulled) if a later drift check finds divergence — `DRIFTED` means `applied_version`'s recorded intent no longer matches the live infrastructure, not that `applied_version` itself is unknown. |

**Why this distinction matters, concretely:**

- **Rollback:** `RequestRollback` (Contract #2 §5) targets a previous `engineering_version` of the same `intent_id`. The new `DeploymentContext`'s `desired_version` is the older version; `applied_version` only catches up once that rollback is itself validated `STABLE`. Without this split, "what are we rolling back to" and "what is currently live" would be the same field, making an in-progress rollback unrepresentable.
- **Drift detection:** drift is precisely "the live infrastructure no longer matches `applied_version`'s `domain_intent`" — comparing against `applied_version`, not `desired_version`, because during an active `DEPLOYING`/`VALIDATING` window the two legitimately differ without that being drift.
- **Auditability and AI explanation:** "why did the platform do X" is answerable by comparing `desired_version` and `applied_version` at any point in history without needing to replay the full event log — both are plain fields on a persisted object.

---

# 5. Persistence Boundary

Three distinct stores exist, each with a single owner, resolving the ambiguity found during the Control Plane coherence review over where `ExecutionState` actually lives:

| Object | Store | Owner | Rationale |
|---|---|---|---|
| `CanonicalIntent` | Nautobot | ADR-001 | Desired infrastructure state — Nautobot's actual scope as Source of Truth. Slow-moving relative to execution telemetry; a `CanonicalIntent` can be unreferenced by any deployment for weeks or months. |
| `DeploymentContext` + `ExecutionState` | Workflow/Execution store (technology not yet chosen) | Workflow Engine domain | High-frequency mutable execution telemetry (`lifecycle_state`, timestamps, `approval_decision`) — a fundamentally different access pattern and rate of change from Nautobot's inventory data. Nautobot is not the right home for this; forcing it in would couple the desired-state SoT's data model to execution-plane churn. |
| Denied/rejected requests (Technical Policy or Approval Workflow denial) | Audit log (technology not yet chosen), distinct from both of the above | Platform Gateway | Forensic record of what was requested and refused — not active desired state, not execution progress. A `SubmitIntent` denied by Technical Policy never becomes a `CanonicalIntent` at all and has nothing to record in Nautobot; its only durable record is here. |

**Consequence for ADR-001:** "Nautobot as the Source of Truth" scopes specifically to desired infrastructure state (`CanonicalIntent`), not to execution history or telemetry. This is a narrowing clarification, not a contradiction — ADR-001 was never explicit about `ExecutionState`, and this section makes that scope boundary explicit for the first time.

**Consequence for the Knowledge Layer (ADR-009):** the historical engineering record is a fourth, read-oriented capability layered *over* both Nautobot (`CanonicalIntent` history via `previous_version` lineage) and the Workflow/Execution store (`ExecutionState` history) — it is not itself a fourth place either object is natively persisted; it is where both are made queryable together for humans and AI over time.

---

# Relationship to Existing Decisions

- **ADR-001** — `STABLE` (this contract) and "platform-managed" (ADR-001's Brownfield Onboarding Exception) are **independent concepts that must never be conflated**. `STABLE` is an execution-convergence fact: has validation confirmed `applied_version` matches `desired_version`? It is reversible (`STABLE` ⇄ `DRIFTED`). "Platform-managed" is a provenance fact: was this object's desired state ever authored via forward intent? It is set once, permanently, and never reverses. An object can be `DRIFTED` and still platform-managed; an object can be `STABLE` and still brownfield/unmanaged if it was never touched by forward intent at all (this contract only governs objects that *are* under forward-intent management — brownfield objects outside that path have no `ExecutionState` at all). Additionally, §5 narrows ADR-001's SoT scope to `CanonicalIntent` specifically, not `ExecutionState`.
- **ADR-011** — this contract elevates and formalizes "events describe facts, not commands" from an implicit design quality into an explicit, mandatory principle (Section 3), and adds the "published only after commit" rule that ADR-011 did not previously state. It also renames `IntentReceived` to `IntentSubmitted` (ADR-011, updated 2026-07-05) to match the Intent/Deployment lifecycle split.
- **ADR-014 (Technical Policy)** — evaluated entirely within the Intent Lifecycle, before any `ExecutionState` exists. Never appears in this contract's state machine at all — a Technical Policy denial has no `ExecutionState` to set to `FAILED`, because none has been created yet.
- **ADR-015 (Deployment Approval)** — owns the `PENDING_APPROVAL`/`ACCEPTED`/`FAILED` transitions this contract's state machine centers on (Section 2). This contract defines *when* those transitions happen and what they persist/publish; ADR-015 defines *how* the authorization decision itself is made.
- **Contract #1 (Canonical Intent)** — `LifecycleState` enum and `ExecutionState.desired_version`/`applied_version` are defined here conceptually; Contract #1's field tables should be read as deferring to this document for their rationale.
- **Contract #2 (Platform API)** — Section 3's Intent Lifecycle / Deployment Lifecycle split is the direct basis for this contract's Sections 1-3; this contract makes that split's state-machine, ownership, and event-timing implications precise.

---

# What This Contract Does Not Yet Define

- The Technical Policy Decision Contract (ADR-014) and the Deployment Approval Contract (ADR-015) — this contract only establishes that their outcomes determine `PENDING_APPROVAL`/`ACCEPTED`/`FAILED`, not the shape of either decision itself, nor approval-routing/change-window logic.
- The Platform Events Specification (Tier 2) — event payload schemas; this contract only establishes *when* events fire and what they may never do (carry commands, fire before commit).
- The specific technology for the Workflow/Execution store and the audit log (Section 5) — named as distinct stores with distinct owners, but no technology chosen for either yet.
