# 14 – Vertical Slice v0.1 Implementation Roadmap

**Project:** Network Platform Engineering Platform

**Document Type:** Implementation Roadmap

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

**Date:** 2026-07-05

---

# Purpose

The Control Plane architecture reached a stable point on 2026-07-05: [Contract #1 — Canonical Intent](../11-Specifications/01-Canonical-Intent-Specification.md), [Contract #2 — Platform API](../11-Specifications/02-Platform-API-Specification.md), and [Contract #3 — Platform Execution Model](../11-Specifications/03-Platform-Execution-Model-Specification.md) are internally consistent, cross-checked against every ADR that constrains them, with no known open gaps.

This document is **not** a new architecture decision. It is an implementation plan to build the first executable proof that this architecture actually works, end to end, against real infrastructure (the existing lab: Nautobot + the ACI simulator). Specification work is paused until this slice either confirms the architecture or surfaces a concrete reason to revise it.

## Objective

Prove the sequence:

```text
REST API → Canonical Intent → Technical Policy → Nautobot → Deployment Request
    → Workflow Engine (stub) → Terraform (stub) → Validation (stub) → Knowledge Capture
```

**This is architectural validation, not production readiness.** Success is a single request flowing through every real architectural boundary at least once, with the right object persisted in the right store at each step. It is explicitly not: full RBAC, an event bus, approval routing, multi-domain support, or a hardened API.

## Success Criteria

Vertical Slice v0.1 is complete when a single scripted test, run against the live lab, does all of the following without manual intervention:

1. `POST` a Canonical Intent to the REST API for the existing `web-tenant` domain content ([Phase 3](../01-Vision/01-Current-State.md)'s known-good payload).
2. Confirms Technical Policy actually evaluated it (a deliberately-invalid tenant name is rejected; a valid one is not).
3. Confirms the intent envelope is retrievable from **Nautobot**, not from the Platform API's own memory.
4. `POST` a deployment request against that intent and confirms it reaches `ACCEPTED` (lab environment, no approval required).
5. Confirms the Workflow Engine stub, Terraform stub, and Validation stub each ran, in order, and `ExecutionState.lifecycle_state` reaches `STABLE`.
6. Confirms a Knowledge Capture record exists for the completed deployment, containing both the `CanonicalIntent` and the final `ExecutionState`.

If any of these six requires an architectural change to satisfy, that is itself a valid and expected outcome of this slice — record it as a new Open Question, do not force-fit it.

---

# What v0.1 Deliberately Does Not Include

Listed explicitly so scope does not creep during implementation:

| Excluded | Why | Where it's specified for later |
|---|---|---|
| Approval Workflow / `PENDING_APPROVAL` path | v0.1 only targets `environment=lab`, which never requires approval | [ADR-015](../03-Decisions/ADR-015-Deployment-Approval.md) |
| Real event bus (Kafka/RabbitMQ/webhooks) | Technology deliberately deferred; no producer/consumer volume exists yet to evaluate against | [ADR-011](../03-Decisions/ADR-011-Event-Driven-Automation.md) |
| Full authentication/RBAC | Not the architectural claim under test in this slice | [Contract #2](../11-Specifications/02-Platform-API-Specification.md) §11, `10-Platform-Security-Architecture.md` |
| Domain Provider Registry | Only one domain (`cisco_aci`) exists; `KNOWN_DOMAINS` allow-list is sufficient | [Contract #1](../11-Specifications/01-Canonical-Intent-Specification.md) |
| Platform Events Specification (real payload schemas) | No real event bus yet to schematize payloads for | Tier 2 roadmap item |
| Rollback, retry, multi-environment promotion | Exercises `previous_version`/`rollback_of` machinery not needed to prove the base sequence once | Future vertical slice iteration |
| Drift detection (`STABLE` → `DRIFTED`) loop | Requires a scheduler/continuous-compliance runner; out of scope for a single request/response proof | [ADR-008](../03-Decisions/ADR-008-Validation.md) |
| Knowledge Layer semantic search / AI retrieval | Level 4 maturity ([12-Roadmap.md](12-Roadmap.md)); v0.1 only proves a record can be captured at all | ADR-009, future AI work |
| Real Terraform/Ansible/pyATS execution | Already proven working end-to-end in Phases 3–5; re-proving it is not this slice's purpose | `01-Current-State.md` |

---

# Component Inventory: Real vs. Mocked

| # | Component | v0.1 Treatment | Why |
|---|---|---|---|
| 1 | **REST API** (Platform Gateway + Intent Translation) | **Real**, minimal | Extends the existing skeleton (`lab/docker/platform-api/`) with exactly two write operations (`SubmitIntent`, `RequestDeployment`) and two read operations (`GetIntent`, `GetDeploymentStatus`). No auth, no rate limiting, no other Contract #2 operations — those don't affect whether the sequence works. |
| 2 | **Canonical Intent** | **Real**, already built | `platform/canonical_intent/` (Contract #1's reference implementation) is used as-is. No changes expected. |
| 3 | **Technical Policy** | **Real engine, minimal rules** | Run an actual OPA instance (official Docker image) with exactly one Rego rule (tenant naming convention). Proves the real architectural claim — an independent service the Platform API calls out to, not inline `if` statements — without building a rule catalog. |
| 4 | **Nautobot persistence** | **Real, using existing Nautobot primitives** | A new Nautobot **Custom Field** (JSON type) on the `Tenant` model, e.g. `canonical_intent_envelope`, holds the `CanonicalIntent` envelope (`intent_id`, `engineering_version`, `owner`, `tags`, `created_at`). Zero new Nautobot app/plugin code. `domain_intent` itself continues to materialize as real Tenant/VRF/BridgeDomain/Subnet objects, exactly as Phase 3 already does. |
| 5 | **Deployment Request / `ExecutionState` store** | **Real, minimal** | A single SQLite file (new). Holds `DeploymentContext` and `ExecutionState` rows. Deliberately not Nautobot (Contract #3 §5, Persistence Boundary) and deliberately not a new container/service — SQLite is the smallest real, durable, inspectable option. |
| 6 | **Workflow Engine** | **Stub** | A plain Python function, called directly (in-process or via a trivial background task) once `RequestDeployment` reaches `ACCEPTED`. Not n8n. Not an event bus. Proves the sequencing contract (something reacts to `ACCEPTED` and drives `DEPLOYING`) without standing up orchestration infrastructure. |
| 7 | **Terraform** | **Stub** | A Python function simulating `DEPLOYING` → success/failure after a short delay. Does not shell out to `terraform apply`. Real Terraform already works end-to-end (Phase 3) — re-exercising it isn't this slice's purpose. The stub's call signature should be swappable for the real Phase 3 module later with no Contract change (this is itself part of what's being validated — see Risks below). |
| 8 | **Validation** | **Stub** | Same pattern as Terraform — a function simulating `VALIDATING` → `STABLE`/`FAILED`. Real pyATS already works end-to-end (Phase 5). |
| 9 | **Knowledge Capture** | **Real, minimal** | A single append-only JSON Lines file (new, e.g. `lab/knowledge/deployments.jsonl`). One line per completed deployment: `CanonicalIntent` + final `ExecutionState`. No semantic search, no vector DB, no Obsidian integration — just proof that a durable, structured engineering record is produced. |

**Rule of thumb applied throughout:** if a component already works end-to-end from an earlier phase (Terraform, Ansible*, pyATS), it is stubbed here — re-validating it adds no information. If a component is cheap to stand up for real and its realness is the actual claim under test (OPA, Nautobot persistence, a durable execution store, a durable knowledge record), it is built for real, at the smallest possible scope.

<sub>*Ansible (Day-2) is not part of the v0.1 sequence at all — Day-2 operations happen after `STABLE`, out of scope for a first-deployment proof.</sub>

---

# Minimum Components Required

Concretely, the new artifacts this slice adds:

1. New FastAPI routes in the existing `lab/docker/platform-api/` skeleton: `POST /intents` (`SubmitIntent`), `GET /intents/{intent_id}/{engineering_version}` (`GetIntent`), `POST /deployments` (`RequestDeployment`), `GET /deployments/{deployment_id}` (`GetDeploymentStatus`).
2. One OPA container + one Rego policy file (naming convention rule).
3. One Nautobot Custom Field definition (`canonical_intent_envelope`, JSON, on `Tenant`) — configuration, not code. **Verify at implementation time** whether this Nautobot 2.x instance supports the JSON custom field type; if not, fall back to a text field storing serialized JSON.
4. One SQLite file + a thin data-access module for `DeploymentContext`/`ExecutionState` rows.
5. One Workflow Engine stub module (plain Python).
6. One Terraform stub module (plain Python, no real Terraform invocation).
7. One Validation stub module (plain Python, no real pyATS invocation).
8. One Knowledge Capture module (append to JSON Lines).
9. One end-to-end test script exercising the Success Criteria above.

Nine artifacts. Six are new "for real" (1, 3, 4, 5 as infra, 8, 9); three are deliberate stand-ins for already-proven capabilities (6 for Workflow Engine orchestration, and the stub bodies of 7 and the Validation stub).

---

# Implementation Milestones

Ordered by dependency — each milestone has its own checkpoint so the slice is validated incrementally rather than all at once.

## M1 — Intent Lifecycle only (no Policy, no Deployment)

`SubmitIntent` → Intent Translation → **Persist directly to Nautobot Custom Field** → response. No Technical Policy gate yet.

**Checkpoint:** `GetIntent` returns a `CanonicalIntent` whose envelope was actually read back from Nautobot (restart the API process between submit and get, to prove it isn't held in memory).

## M2 — Add Technical Policy

Insert OPA evaluation between Intent Translation and Nautobot persistence.

**Checkpoint:** a deliberately-invalid tenant name is rejected with `TECHNICAL_POLICY_DENIED` and never reaches Nautobot; a valid one proceeds exactly as M1.

## M3 — Deployment Lifecycle, `ACCEPTED` only

`RequestDeployment` → create `DeploymentContext`/`ExecutionState` in SQLite → lab environment, `approval_state=none_required` → `ACCEPTED` immediately (no `PENDING_APPROVAL` exercised in v0.1, per scope exclusions above).

**Checkpoint:** `GetDeploymentStatus` returns `ACCEPTED`, read back from SQLite, independent of the Nautobot-backed `CanonicalIntent` lookup.

## M4 — Workflow Engine stub → Terraform stub → Validation stub chain

Wire the three stubs so reaching `ACCEPTED` triggers `DEPLOYING` → `VALIDATING` → `STABLE` (or `FAILED`, exercised with a stub configured to fail, to confirm the failure path is real and not just the happy path).

**Checkpoint:** `GetDeploymentStatus` shows the full transition history via `lifecycle_state` changes across polls; `desired_version`/`applied_version` converge correctly at `STABLE`.

## M5 — Knowledge Capture

On reaching `STABLE` or `FAILED`, append a record to the JSON Lines file.

**Checkpoint:** the file contains one line per completed deployment, and that line's `CanonicalIntent` matches what Nautobot holds and its `ExecutionState` matches what SQLite holds — i.e. Knowledge Capture is a read-only reflection of the other two stores, not a fourth independent source of truth (consistent with [Contract #3](../11-Specifications/03-Platform-Execution-Model-Specification.md) §5).

## M6 — End-to-end test script

A single script (not a manual walkthrough) that performs the full Success Criteria sequence against the live lab and exits non-zero on any deviation.

**Checkpoint:** this is the actual deliverable. Vertical Slice v0.1 is "done" when this script passes on a clean run.

---

# Risks and Things Likely to Surface Real Architecture Questions

Flagged as things to watch during implementation, not solved in advance — consistent with "avoid adding new architecture unless implementation proves it necessary":

- **Nautobot JSON custom field availability** — if this Nautobot version doesn't support it, the fallback (serialized JSON in a text field) works but is worth confirming doesn't force an uglier design than expected.
- **Swapping stubs for real Terraform/Validation later** — the stub function signatures should be designed so that replacing the stub body with a real `terraform apply`/pyATS call requires no change to the Workflow Engine stub's calling contract. If it turns out this isn't naturally true, that is a real signal about the Execution Plane's interface, worth its own ADR/Contract note at that point — not before.
- **Idempotency keys (Contract #2 §9)** — not implemented in v0.1's minimal routes. If retry behavior surfaces problems during the M6 test script, that's real evidence for prioritizing it; don't build it speculatively first.
- **`correlation_id` propagation (Contract #2 §10)** — v0.1's stubs should still thread `correlation_id` through their calls even though nothing consumes it yet (cheap to do now, expensive to retrofit), but no tracing infrastructure should be built around it.

---

# Relationship to Existing Work

- Builds directly on [Contract #1](../11-Specifications/01-Canonical-Intent-Specification.md), [Contract #2](../11-Specifications/02-Platform-API-Specification.md), and [Contract #3](../11-Specifications/03-Platform-Execution-Model-Specification.md) — this roadmap introduces no new architectural decisions, only an implementation sequence for what those three already specify.
- Reuses `platform/canonical_intent/` (Contract #1's Pydantic reference implementation) unchanged.
- Extends `lab/docker/platform-api/` (existing skeleton) rather than creating a new service.
- Deliberately does not re-exercise Phases 3–5 (Terraform/Ansible/pyATS) — those are stubbed here specifically because they are already proven; see `01-Current-State.md`.
- Corresponds to Level 2 ("Platform Automation") of the strategic maturity model in [12-Roadmap.md](12-Roadmap.md) — this is the first concrete implementation step toward that level, not a redefinition of it.
