---
title: "Platform Specification 01 — Canonical Intent"
description: "Contract #1 from the Platform Specification Roadmap: the immutable desired-state engineering object, and its two companion runtime objects"
---

# Platform Specification 01 — Canonical Intent

**Status:** Accepted

**Date:** 2026-07-04

**Decision Makers:** Platform Engineering Team

**Type:** Platform Specification (not an ADR — this is a contract implementing decisions already made in [ADR-004](../03-Decisions/ADR-004-Platform-API.md), [ADR-014](../03-Decisions/ADR-014-Policy-Enforcement.md), and [ADR-001](../03-Decisions/ADR-001-Nautobot-Source-of-Truth.md))

**This document is the authoritative specification.** [`platform/canonical_intent/models.py`](../../platform/canonical_intent/models.py) is a Python/Pydantic reference implementation that conforms to it — not the other way around. The specification is the language-agnostic contract; any future implementation (Go, TypeScript, Java) must conform to *this document*, not to the Pydantic code. Generated artifacts (JSON Schema, OpenAPI) derive from the executable model but must remain traceable back to this specification.

---

# Purpose

This is Contract #1 of the Platform Specification Roadmap (see the roadmap discussion in project history) — the transition point from architecture description to engineering contract. `03b-Reference-Architecture.md` and `03c-Platform-Control-Plane.md` describe "Canonical Intent" in prose; this document and its accompanying Pydantic implementation make it a concrete, versioned, testable shape that Policy Evaluation (ADR-014), Nautobot persistence, Knowledge Layer intake, and every future Domain Provider can be built against.

---

# Three Objects, Not One

An early design question was whether Canonical Intent should also carry approval state, deployment lifecycle, and requester identity. It does not. Three related but distinct objects exist:

```text
CanonicalIntent        (immutable desired state)
       │
       │ referenced by (intent_id, engineering_version)
       ▼
DeploymentContext      (mutable request metadata — one per deployment attempt)
       │
       │ referenced by (deployment_id)
       ▼
ExecutionState         (mutable execution record — one per deployment attempt)
```

**Why split them:** a single `CanonicalIntent` may be deployed more than once — retried after a transient failure, redeployed to a different environment, or rolled back to. If approval state, requester, and deployment progress lived inside `CanonicalIntent` itself, every one of those situations would force a mutation (or a confusing new "version") of an object that is supposed to represent *desired state*, not *what happened when we tried to achieve it*. Separating them means:

- `CanonicalIntent` stays immutable and cheap to reference, diff, and version.
- Retries and multi-environment promotion reuse the same intent without inventing new "fake" versions.
- Knowledge Layer and rollback tooling can ask "what was the desired state" (`CanonicalIntent`) completely independently of "what happened and when" (`ExecutionState`).

This mirrors a pattern already familiar from Kubernetes (`spec` vs `status`) and Terraform (config vs state) — desired state and observed/execution state are always kept as separate objects once a platform matures past its first version.

---

# CanonicalIntent — Immutable Desired State

Describes **what** the business wants, in one domain-agnostic envelope regardless of target infrastructure domain.

## Envelope / Domain Intent split

```text
CanonicalIntent
├── Envelope        — identical shape regardless of domain_id
│   ├── intent_id, engineering_version, previous_version
│   ├── domain_id
│   ├── owner, tags
│   └── created_at
│
└── domain_intent   — domain-specific desired-state content
    └── shape defined by that domain's own provider
        (see the future Domain Provider Specification, Tier 3)
```

The envelope is what Policy Evaluation, Knowledge Layer, and Observability all consume identically, regardless of which infrastructure domain a request targets — this is what makes those capabilities genuinely domain-agnostic, as ADR-008/009/013 already claim. `domain_intent` is intentionally opaque to everything except the domain's own generator (today: `platform/python/generate_aci.py`).

## Fields

| Field | Type | Rationale |
|---|---|---|
| `intent_id` | UUID | Stable identity across every revision of this intent's lineage. Never changes. |
| `engineering_version` | int, ≥1 | Monotonically increasing revision number. Lets intent evolution, rollback, and Knowledge Layer capture reference a *specific* revision independently of deployment history. |
| `previous_version` | int, optional | The `engineering_version` this revision supersedes. Enables lineage tracing and rollback without consulting deployment records. |
| `domain_id` | str | See **Domain Identifier Resolution** below. |
| `domain_intent` | dict | Domain-specific desired-state payload (e.g. the NetAsCode-shaped ACI tenant/VRF/BD structure this platform already generates). |
| `owner` | str | Team/individual accountable for this object *on an ongoing basis*. Persists across every version. **Distinct from `DeploymentContext.requester`** — a platform admin may submit a deployment (`requester`) on behalf of a team that owns the object (`owner`). |
| `tags` | dict[str, str] | Business metadata (cost-center, department, etc). Enduring attributes of the object, not of one request. |
| `created_at` | datetime | When this specific version was created. |

## Why immutable

`model_config = ConfigDict(frozen=True)` — enforced at the type level, not just by convention. Any change to desired state must produce a **new** `CanonicalIntent` (new `engineering_version`), never a mutation. This is what makes `intent_id` + `engineering_version` a safe, stable reference for `DeploymentContext`, `ExecutionState`, Knowledge Layer capture, and audit logs to point at without the risk of the referenced object changing underneath them.

## Domain Identifier Resolution

`domain_id` is a plain string field, not a closed enum. Validation today checks it against `KNOWN_DOMAINS` (currently `{"cisco_aci"}`) — a hardcoded allow-list standing in for the future **Domain Provider Registry** (Platform Specification Tier 4). This is a deliberate interim measure: adding a second domain (VXLAN EVPN, Azure) only ever requires widening the allow-list or swapping it for a live registry lookup — it never requires changing `CanonicalIntent`'s type or schema. No redesign, at any point, as domains are added.

---

# DeploymentContext — Request-Scoped Metadata

One `DeploymentContext` exists per **attempt** to deploy a `CanonicalIntent` — including retries. Mutable/transactional, unlike `CanonicalIntent`.

| Field | Type | Rationale |
|---|---|---|
| `deployment_id` | UUID | Identity of this specific deployment attempt. |
| `intent_id`, `engineering_version` | UUID, int | Which immutable desired state this attempt targets. |
| `correlation_id` | UUID | Ties together every event/log/trace this attempt produces across the platform — the join key for the future Platform Events Specification (Tier 2). |
| `requester` | str | Who/what submitted *this* attempt. May differ from `CanonicalIntent.owner`. |
| `entry_point` | str | Which channel this arrived through (`cli`, `jira`, `ai_agent`, `rest`, ...) — per ADR-010's "many entry points" principle. |
| `environment` | enum: `lab` / `staging` / `production` | Required input to Policy Evaluation's environment-restriction rules (ADR-014). |
| `approval_state` | enum: `none_required` / `pending` / `approved` / `denied` | Required input to Policy Evaluation's approval-requirement rules (ADR-014). |
| `approved_by`, `approved_at` | str, datetime, optional | Populated once `approval_state` transitions to `approved`. |
| `submitted_at` | datetime | When this attempt was submitted. |

---

# ExecutionState — What Actually Happened

One `ExecutionState` exists per `DeploymentContext`, updated in place as the deployment progresses. This is the object that changes constantly — `CanonicalIntent` never does.

| Field | Type | Rationale |
|---|---|---|
| `deployment_id` | UUID | Which `DeploymentContext` this tracks. |
| `lifecycle_state` | enum (see below) | Current stage of this deployment attempt. |
| `policy_decision`, `policy_reasons` | str, list[str] | Recorded output of the Policy Decision Contract (Tier 1 #3, not yet drafted). |
| `persisted_to_nautobot_at`, `deployed_at`, `validated_at` | datetime, optional | Pipeline stage timestamps. |
| `validation_result_ref` | str, optional | Points to a Validation Result object (Validation Specification, Tier 1 #4, not yet drafted). |
| `rollback_of` | UUID, optional | If this deployment is a rollback, the `deployment_id` it rolls back. |
| `last_updated_at` | datetime | Updated on every state transition. |

## Lifecycle State Machine

```text
submitted → policy_evaluated → persisted → deployed → validated → managed
                                                              │
                                                              ▼
                                                          drifted → (forward intent resolves) → managed
                                                              │
                                                              ▼
                                                          retired
```

A `deny` decision at `policy_evaluated` halts the pipeline — no `persisted`, no Nautobot write, no `IntentReceived` event. This state machine is exactly what makes the [ADR-001 Brownfield Onboarding Exception](../03-Decisions/ADR-001-Nautobot-Source-of-Truth.md) enforceable: an object is "platform-managed" from the moment its `ExecutionState.lifecycle_state` first reaches `managed` via this forward pipeline, as opposed to having arrived through brownfield SSoT import.

---

# Relationship to Existing Decisions

- **ADR-001** — `ExecutionState.lifecycle_state = managed` is the machine-readable signal for "this object is now platform-managed," resolving the open question the Brownfield Onboarding Exception amendment left implicit.
- **ADR-004** — The Platform Gateway accepts requests; Intent Translation builds `CanonicalIntent` and a `DeploymentContext`; both are hand-off points this contract now makes concrete.
- **ADR-014** — Policy Evaluation's input is a `CanonicalIntent` + `DeploymentContext` (for `environment`/`approval_state`); its output populates `ExecutionState.policy_decision`/`policy_reasons`.
- **ADR-009** — Knowledge Layer can capture "what was decided" (`CanonicalIntent`, stable and immutable) independently of "what happened" (`ExecutionState`, which changes and eventually gets archived).

---

# What This Contract Does Not Yet Define

- The **Policy Decision Contract** (Tier 1 #3) — the actual JSON shape OPA receives and returns, referenced here only as `policy_decision`/`policy_reasons` fields.
- The **Validation Specification** (Tier 1 #4) — what `validation_result_ref` actually points to.
- The **Domain Provider Specification** (Tier 3) — the schema `domain_intent` must conform to per `domain_id`.
- The **Platform Events Specification** (Tier 2) — how `correlation_id` propagates through actual event payloads.

These are the next contracts in the roadmap, in that order.
