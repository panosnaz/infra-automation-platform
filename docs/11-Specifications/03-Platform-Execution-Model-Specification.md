---
title: "Platform Specification 03 — Platform Execution Model"
description: "Contract #3: the system-wide lifecycle, state ownership, and event timing models every other contract depends on"
---

# Platform Specification 03 — Platform Execution Model

**Status:** Accepted

**Date:** 2026-07-05

**Decision Makers:** Platform Engineering Team

**Type:** Platform Specification (not an ADR — this formalizes and elevates a principle already implied by [ADR-011](../03-Decisions/ADR-011-Event-Driven-Automation.md), and resolves a terminology collision found while cross-checking [Contract #1](01-Canonical-Intent-Specification.md) against [ADR-001](../03-Decisions/ADR-001-Nautobot-Source-of-Truth.md))

**This document is the authoritative specification.** [`platform/canonical_intent/models.py`](../../platform/canonical_intent/models.py)'s `LifecycleState` enum and `ExecutionState.desired_version`/`applied_version` fields are the reference implementation of this specification.

---

# Purpose

This is a **stabilization contract**, written before the Policy Decision Contract deliberately: Policy Evaluation is itself a state transition (Contract #2, Request Lifecycle), and it cannot be specified correctly against ambiguous lifecycle, ownership, or event-timing semantics. This document resolves those three cross-cutting models once, so every subsequent contract (Policy Decision, Validation, Platform Events, Domain Provider) builds on the same foundation instead of each silently assuming its own.

---

# 1. System-Wide Lifecycle Model

## Externally visible lifecycle

`ExecutionState.lifecycle_state` (Contract #1) exposes exactly these seven states — no more:

| State | Meaning | Sync/Async | Persisted |
|---|---|---|---|
| `ACCEPTED` | Request passed Policy Evaluation and was persisted to Nautobot. | Synchronous | Yes |
| `DEPLOYING` | Terraform/Ansible execution in progress. | Asynchronous | Yes |
| `VALIDATING` | pyATS/Catfish validation in progress. | Asynchronous | Yes |
| `STABLE` | Validation confirmed `applied_version` matches `desired_version`. Steady state. | Asynchronous | Yes |
| `DRIFTED` | Live infrastructure no longer matches `applied_version`'s desired state. | Asynchronous, recurring | Yes |
| `FAILED` | Policy denied the request, OR deployment/validation failed. | Either | Yes (see Audit Trail below) |
| `RETIRED` | Intent's infrastructure has been deliberately decommissioned. | Synchronous request, async teardown | Yes |

## Internal implementation steps are not lifecycle states

Intent Translation, Policy Evaluation, and Nautobot persistence (Contract #2, Request Lifecycle Phase A) are **implementation detail**, not contract. They happen synchronously, in-process, inside the transition into `ACCEPTED`. No external caller, subscriber, or Knowledge Layer entry should ever need to know these three sub-steps exist as distinct states — only that a request either becomes `ACCEPTED` or fails with a `POLICY_DENIED`/validation error (Contract #2 §7) before ever reaching `ACCEPTED`.

**Rationale for this simplification:** exposing implementation stages as lifecycle states couples every subscriber to the Platform API's internal pipeline shape. If Intent Translation is later split into two steps, or Policy Evaluation is parallelized, external consumers must not need to change. Seven stable, meaningful, user-facing states are the contract; how `ACCEPTED` is internally achieved is not.

## Persisted vs. transient

Everything in the table above is persisted once reached. The only genuinely transient data is a request that never becomes a `CanonicalIntent` at all (fails schema validation in Intent Translation) — it produces an error response (Contract #2 §7) and nothing durable.

A **denied** request (Policy Evaluation returns deny) does become a `CanonicalIntent` and reaches `FAILED` — but per Contract #2, this never triggers a Nautobot write. `FAILED` for a denied request is recorded in an **audit log**, a distinct store from Nautobot serving a distinct purpose (forensic record of what was requested and refused, not active desired state). This is why `FAILED` is persisted in the table above despite Contract #2 explicitly saying denial produces "no Nautobot write" — persistence and Nautobot-persistence are not the same thing.

---

# 2. State Ownership Model

| Transition | Owner | Trigger |
|---|---|---|
| (none) → `ACCEPTED` | Platform API (Intent Translation + Policy Evaluation + Nautobot write, internally) | Synchronous, direct call |
| `ACCEPTED` → `DEPLOYING` | Execution Plane (Terraform/Ansible), invoked by the Workflow Engine | Asynchronous, reacts to `IntentReceived` |
| `DEPLOYING` → `VALIDATING` | Validation (pyATS/Catfish) | Asynchronous, reacts to `DeploymentCompleted` |
| `VALIDATING` → `STABLE` | Validation — sets `applied_version = desired_version` on success | Asynchronous |
| `VALIDATING` → `FAILED` | Validation — on validation failure | Asynchronous |
| `STABLE` → `DRIFTED` | Validation (Continuous Compliance, ADR-008) | Asynchronous, scheduled or event-driven |
| `DRIFTED` → `STABLE` | Validation, **only** after a new forward-authored `CanonicalIntent` resolves the drift (never by re-running drift detection alone — see [ADR-001's Brownfield Onboarding Exception](../03-Decisions/ADR-001-Nautobot-Source-of-Truth.md)) | Asynchronous |
| `ACCEPTED`/`DEPLOYING` → `FAILED` | Policy Engine (deny) or Execution Plane (deployment failure) | Synchronous (deny) or asynchronous (deployment failure) |
| (any) → `RETIRED` | Platform API | Synchronous request, async teardown |

No component ever transitions `ExecutionState` on another component's behalf. The Workflow Engine, in particular, **orchestrates** the `ACCEPTED → DEPLOYING` reaction but does not itself own the transition — the Execution Plane (Terraform/Ansible) does, since it is the actual action that makes `DEPLOYING` true.

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

**Consequence:** `IntentReceived` is published after the Nautobot write inside `ACCEPTED` succeeds, not before. `DeploymentCompleted` is published after `DEPLOYING` → `VALIDATING` is durably recorded, not while Terraform is still applying. This is a stricter reading than some event-driven systems use (some publish "in-flight" events for progress reporting) — this platform deliberately does not, to keep "an event exists" and "the state is real" equivalent, simplifying every subscriber's correctness reasoning.

## Consequence for Contract #2's sync/async split

Phase A (Section 1: the internal path into `ACCEPTED`) is **entirely event-free** — Intent Translation, Policy Evaluation, and the Nautobot write are direct synchronous calls within one Platform API request. The **first** event of any deployment's lifecycle (`IntentReceived`) is published only once `ACCEPTED` is reached. Every subsequent transition (`DEPLOYING`, `VALIDATING`, `STABLE`, `DRIFTED`, `FAILED` after acceptance, `RETIRED`) is event-mediated, one reaction per step, per the chain above.

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

# Relationship to Existing Decisions

- **ADR-001** — `STABLE` (this contract) and "platform-managed" (ADR-001's Brownfield Onboarding Exception) are **independent concepts that must never be conflated**. `STABLE` is an execution-convergence fact: has validation confirmed `applied_version` matches `desired_version`? It is reversible (`STABLE` ⇄ `DRIFTED`). "Platform-managed" is a provenance fact: was this object's desired state ever authored via forward intent? It is set once, permanently, and never reverses. An object can be `DRIFTED` and still platform-managed; an object can be `STABLE` and still brownfield/unmanaged if it was never touched by forward intent at all (this contract only governs objects that *are* under forward-intent management — brownfield objects outside that path have no `ExecutionState` at all).
- **ADR-011** — this contract elevates and formalizes "events describe facts, not commands" from an implicit design quality into an explicit, mandatory principle (Section 3), and adds the "published only after commit" rule that ADR-011 did not previously state.
- **Contract #1 (Canonical Intent)** — `LifecycleState` enum and `ExecutionState.desired_version`/`applied_version` are defined here conceptually; Contract #1's field tables should be read as deferring to this document for their rationale.
- **Contract #2 (Platform API)** — Section 3's Request Lifecycle Phase A/B split is the direct basis for this contract's Sections 1 and 3; this contract makes that split's state-machine and event-timing implications precise.

---

# What This Contract Does Not Yet Define

- The Policy Decision Contract (Tier 1 #3, next in sequence) — this contract only establishes that Policy Evaluation's allow/deny result determines `ACCEPTED` vs. `FAILED`, not the shape of the decision itself.
- The Platform Events Specification (Tier 2) — event payload schemas; this contract only establishes *when* events fire and what they may never do (carry commands, fire before commit).
- The exact audit log store/schema for denied/failed requests (Section 1) — flagged here as a real gap, not yet assigned to any existing Tier item.
