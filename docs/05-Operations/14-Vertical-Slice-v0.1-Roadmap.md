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

## M1 — Intent Lifecycle only (no Policy, no Deployment) ✅ Complete (2026-07-05)

`SubmitIntent` → Intent Translation → **Persist directly to Nautobot Custom Field** → response. No Technical Policy gate yet.

**Checkpoint:** `GetIntent` returns a `CanonicalIntent` whose envelope was actually read back from Nautobot (restart the API process between submit and get, to prove it isn't held in memory). **Passed** — see `tests/integration/milestone1_smoke_test.py`.

**What was built:** `POST /intents` and `GET /intents/{intent_id}/{engineering_version}` added to `lab/docker/platform-api/app/main.py`; a new `app/nautobot_store.py` persists/retrieves the full `CanonicalIntent` as JSON in a Nautobot Tenant custom field (`canonical_intent`, type JSON, content type `tenancy.tenant` — created via the Nautobot REST API, no custom plugin). The Docker build now uses an additional build context (`docker compose`'s `build.additional_contexts`) to reuse `platform/canonical_intent/` unchanged rather than duplicating Contract #1's models.

**Real findings, not architectural problems (implementation continued without stopping):**

- **Scope clarification, not a defect:** `SubmitIntent` requires a Nautobot Tenant matching `domain_intent`'s tenant name to already exist — it does not create/update Tenant/VRF/BridgeDomain/Prefix objects from `domain_intent`. The roadmap's original wording ("domain_intent materializes as real objects, as Phase 3 already does") overstated what exists today; Phase 3 never included a write path from intent into Nautobot inventory. This is a real, tracked gap (see `nautobot_store.py`'s module docstring) but does not block M1 as scoped — it is not yet assigned to a milestone above.
- **Real bug, fixed:** `pydantic.ValidationError.errors()` embeds a raw exception object in `ctx.error` for validators that raise `ValueError` (e.g. `CanonicalIntent`'s `domain_id` check) — passing it straight to `HTTPException(detail=...)` turned an intended 422 into an unhandled 500 at JSON-serialization time. Fixed with `errors(include_context=False, include_url=False)`. Worth carrying forward to any future FastAPI + Pydantic v2 route with custom validators.

**Architecture Validation Review (2026-07-05):** performed after M1 completion, per the process this roadmap established (implementation feedback drives architecture refinement, not the reverse). Verdict: the architecture validated cleanly — no contract proved unnecessary, no abstraction felt forced, and Contract #3 §5's Persistence Boundary worked exactly as specified on the first real attempt. One small separation-of-concerns violation was found and fixed as an **implementation refinement, not an architecture change**: `NautobotIntentStore` (meant to be domain-agnostic per Contract #1's opacity rule for `domain_intent`) contained ACI-specific parsing (`domain_intent['apic']['tenants'][0]['name']`) to resolve which Nautobot Tenant to anchor to. Fixed by moving that resolution to `app/main.py`'s `_aci_tenant_name()` — the domain-aware API boundary — and having `NautobotIntentStore.save()` accept a plain `tenant_name: str` instead of deriving it internally. No new abstraction, interface, or provider class was introduced; re-verified with `tests/integration/milestone1_smoke_test.py` (no behavioral change). Architecture remains unchanged.

## M2 — Add Technical Policy ✅ Complete (2026-07-06)

Insert OPA evaluation between Intent Translation and Nautobot persistence.

**Checkpoint:** a deliberately-invalid tenant name is rejected with `TECHNICAL_POLICY_DENIED` and never reaches Nautobot; a valid one proceeds exactly as M1. **Passed** — see `tests/integration/milestone2_smoke_test.py` (allow, deny + audit record, and OPA-unavailable fail-closed, all verified against the live stack) and `tests/unit/test_technical_policy.py` (8 contract tests, no Docker/OPA required, using `httpx.MockTransport` against the real client rather than a throwaway parallel stub).

**What was built:** `app/technical_policy.py` (`TechnicalPolicyClient`, `PolicyDecision`, `TechnicalPolicyUnavailableError`), `app/audit_log.py` + `app/jsonl_writer.py` (the latter a generic shared primitive, reused as-is by Knowledge Capture later), an OPA sidecar added to `docker-compose.yml` (host-mounted `./policy:/policy:ro`, no image build needed), and `policy/cisco_aci/tenant_naming.rego` (one real rule). Full runtime contract documented in [ADR-014 Appendix A](../03-Decisions/ADR-014-Policy-Enforcement.md#appendix-a--policydecision-runtime-contract) rather than a new standalone specification document — a finding from the Milestone 2 architecture review (the content was too small to justify the ceremony of a new numbered spec).

**Five review cycles preceded this implementation** (architecture validation, design challenge, dependency review, multi-domain stress test, final readiness gate) — see session history. Two real findings survived to implementation, both applied directly rather than reopening design discussion:

- `jsonl_writer.append_jsonl()` creates parent directories defensively (`mkdir(parents=True, exist_ok=True)`) rather than assuming the bind-mounted `data/` directory already exists.
- `PolicyDecision.evaluated_at` uses `datetime.now(timezone.utc)`, matching the timezone-aware convention already established throughout `platform/canonical_intent/models.py`.

**One real implementation-time discovery, not an architecture contradiction:** the official `openpolicyagent/opa` Docker image has no shell, `wget`, or `curl` — a Docker healthcheck for it cannot work as originally planned. Fixed by removing the healthcheck entirely; `depends_on` only waits for container start, and `technical_policy.py` already fails closed on an unready OPA regardless, so this is a tooling correction, not a design gap.

**Domain independence confirmed as designed:** the OPA query path (`data.platform.<domain_id>.decision`) and the fixed `decision` entry-point convention (every domain package exposes exactly one combined `{allow, reasons}` object, regardless of how many internal rules compose it) mean `technical_policy.py` never changed once written. A second domain requires only a new `policy/<domain_id>/*.rego` package — confirmed by design, not yet exercised with a real second domain.

## M3 — Deployment Lifecycle, `ACCEPTED` through `STABLE` ✅ Complete (2026-07-06)

Implemented as one milestone rather than the two originally sketched below (M3 "ACCEPTED only" and M4 "stub chain to STABLE") — in practice, proving the Deployment Lifecycle meant proving the whole `ACCEPTED → DEPLOYING → VALIDATING → STABLE` sequence together, since a lifecycle that only reaches `ACCEPTED` doesn't yet exercise `desired_version`/`applied_version` convergence, the actual point of Contract #3 §4. The original two-milestone split is left below for history, but both are done.

`RequestDeployment` → create `DeploymentContext`/`ExecutionState` in SQLite → lab environment, `approval_state=none_required` → `ACCEPTED` immediately (no `PENDING_APPROVAL` exercised in v0.1, per scope exclusions above). `ACCEPTED` → `DEPLOYING` → `VALIDATING` → `STABLE` via the three stubs, run as a FastAPI `BackgroundTask` scheduled after `RequestDeployment`'s response is sent — this is what makes the HTTP response return at `ACCEPTED` (Contract #2 §3) while the rest proceeds asynchronously, without building a real event bus (ADR-011, still deferred). Each stub owns exactly one transition (Contract #3 §2): `workflow_stub.py` (`ACCEPTED→DEPLOYING`), `terraform_stub.py` (`DEPLOYING→VALIDATING`, sets `deployed_at`), `validation_stub.py` (`VALIDATING→STABLE`, sets `validated_at` and `applied_version = desired_version`).

**Checkpoint:** `GetDeploymentStatus` (`GET /deployments/{deployment_id}`, a composite `DeploymentContext` + `ExecutionState` view per Contract #2 §4) returns `ACCEPTED` immediately after `RequestDeployment`, then `STABLE` once polled after the background chain completes, `desired_version == applied_version`, `deployed_at`/`validated_at` both set. **Passed** — see `tests/integration/milestone3_smoke_test.py` and `tests/unit/test_execution_store.py`/`test_deployment_stubs.py` (17 unit tests total across M2+M3, no Docker required).

**What was built:** `app/execution_store.py` (SQLite, one table, `DeploymentContext`/`ExecutionState` stored as JSON per `deployment_id`, with a `transition()` method that validates the current→next state pair against Contract #3 §2's allowed transitions — `DRIFTED`/`FAILED`/`RETIRED` deliberately excluded, not required by this milestone); `app/workflow_stub.py`, `app/terraform_stub.py`, `app/validation_stub.py` (one file per stub, mirroring the one-file-per-concern discipline from M1/M2); `POST /deployments` and `GET /deployments/{deployment_id}` in `main.py`.

**Real findings, not architectural problems:**

- **Design decision, not a contradiction:** Contract #2 §3 requires `RequestDeployment`'s response to return at `ACCEPTED`, with the rest happening afterward, tracked via polling. With no real event bus (correctly still deferred), FastAPI's built-in `BackgroundTasks` is the smallest mechanism that honors this split without inventing messaging infrastructure — confirmed working via the integration test observing `ACCEPTED` in the initial response and `STABLE` only after polling.
- **Naming reconciliation:** Contract #2 §4 defines a single composite "Deployment" resource (`DeploymentContext` + `ExecutionState`), so `GetDeployment` and `GetExecutionState` were implemented as one endpoint (`GET /deployments/{deployment_id}`) returning both, rather than two separate endpoints that would have diverged from the contract's own resource model.
- **Scope boundary, stated explicitly in code:** `RequestDeployment` accepts an `environment` field but always hardcodes `approval_state=none_required` regardless of its value — Business Approval (ADR-015) isn't implemented, so selecting `production` today does not trigger any gate. This is a deliberate Milestone 3 boundary, not a hidden gap; documented directly in `main.py`'s docstring to prevent it being mistaken for approval support later.

## Business Approval (ADR-015) ✅ Complete (2026-07-14)

Implemented after the Platform v0.3 architecture freeze, entirely within the frozen model — no contract or ADR change required. Closes the M3 scope boundary noted above: `RequestDeployment` for `environment=production` now rests at `PENDING_APPROVAL` (202) instead of hardcoding `approval_state=none_required`; `lab`/`staging` are unaffected (still immediate `ACCEPTED`, 201).

**What was built:** `app/approval_workflow.py` (`approval_required()` — plain Python, not OPA, per ADR-015's own reasoning that this is stateful/time-dependent and belongs to a different implementation shape than Technical Policy's Rego rules; the only rule is environment == production, matching ADR-015's own example exactly — change windows and approver routing remain ADR-015's named Open Items, not built here). `POST /deployments/{deployment_id}/approve` and `.../deny` (Contract #2 §5's `ApproveDeployment`/`DenyDeployment`) — both reject acting on a deployment not currently `PENDING_APPROVAL` with 409, per the contract's own "no-op error" wording, rather than silently accepting it. `ExecutionStore` gained `update_context()` (persists `approval_state`/`approved_by`/`approved_at` on `DeploymentContext`) and two new allowed transitions (`PENDING_APPROVAL → ACCEPTED`, `PENDING_APPROVAL → FAILED`), both already specified in Contract #3 §2 — no new architecture, just the remaining rows of an already-drawn table.

**Checkpoint:** `tests/integration/business_approval_smoke_test.py` — production rests at `PENDING_APPROVAL`; approving resumes the same background pipeline used since M3, reaching `STABLE`; denying reaches `FAILED` with the pipeline never running (`deployed_at` confirmed still null); acting twice on a resolved deployment returns 409; lab is unaffected. 8 new unit tests (`test_approval_workflow.py`, plus `PENDING_APPROVAL`-specific cases in `test_execution_store.py`), all passing with zero Docker. Full M1-M3 regression re-run unchanged and still passing.

**Real finding, not new architectural debt:** this milestone's own test incidentally exercised something the 2026-07-13 freeze review had marked **Unvalidated** — two independent `DeploymentContext`s (one denied, one accepted) against the same `CanonicalIntent`, both resolving correctly and independently. That design claim (the entire justification for splitting the three Contract #1 objects) now has real test evidence behind it, not just code inspection.

## Domain Materialization ✅ Complete (2026-07-14)

Closes the Milestone 1 gap: `SubmitIntent` previously required a Nautobot Tenant matching `domain_intent`'s tenant name to already exist. Implemented within the frozen architecture — Contract #1 already assigned this responsibility to "that domain's own generator"; this is that generator's write-side counterpart, not a new decision.

**What was built:** `app/aci_materializer.py` (`AciMaterializer`) — domain-specific by nature (ACI's Tenant/Namespace/VRF/Prefix/VRFPrefixAssignment shape), deliberately kept at the domain-aware boundary alongside `_aci_tenant_name()`, never inside `NautobotIntentStore` (which stays domain-agnostic per the Milestone 1 Architecture Validation Review's already-established rule). Create-if-missing only — an object matched by name/prefix is left as-is; this does not reconcile drift on a resubmission, which is `DRIFTED`'s job (not implemented) rather than materialization's. Verified empirically against the live Nautobot API before writing code (exact filter field names — `vrf`/`prefix`, not `vrf_id`/`prefix_id`, on `vrf-prefix-assignments` — a real, would-have-been-silent bug caught by testing against the running instance rather than assuming REST conventions).

Wired into `SubmitIntent` (`app/main.py`) between Technical Policy's allow decision and Nautobot persistence — materialization must complete before `NautobotIntentStore.save()` can find its anchor Tenant.

**Checkpoint:** `tests/integration/domain_materialization_smoke_test.py` — `SubmitIntent` for a tenant confirmed not to exist yet succeeds (previously impossible); the created Tenant/VRF/Prefix are read back independently via the Nautobot API with the exact shape `platform/python/generator/transformer.py` expects (network address stored, not the gateway; the `"ACI Bridge Domain: <bd>:<tenant>"` description encoding); **the existing generator (`generate_aci.py --dry-run`) was run directly against the newly materialized tenant and correctly reconstructed the original gateway IP** — a genuine, real round-trip proof, not just a shape check; resubmitting the same intent is confirmed idempotent (no duplicate objects). 5 new unit tests (`test_aci_materializer.py`, `httpx.MockTransport`-based, zero Nautobot required). Full regression (Milestones 1-3 + Business Approval, 30 unit tests total) re-run unchanged and still passing.

## M4 — Workflow Engine stub → Terraform stub → Validation stub chain (superseded — see M3 above)

Wire the three stubs so reaching `ACCEPTED` triggers `DEPLOYING` → `VALIDATING` → `STABLE` (or `FAILED`, exercised with a stub configured to fail, to confirm the failure path is real and not just the happy path).

**Checkpoint:** `GetDeploymentStatus` shows the full transition history via `lifecycle_state` changes across polls; `desired_version`/`applied_version` converge correctly at `STABLE`.

## M5 — Knowledge Capture ✅ Complete (2026-07-14)

Implemented after a Capability Readiness Review confirmed the milestone fit cleanly within the frozen architecture (Contract #1-#3, ADR-009) with no blocker. On reaching `STABLE` or `FAILED`, a record is appended to a new JSON Lines file.

**What was built:** `app/knowledge_capture.py` (`capture_deployment_outcome()`) — a single, read-only function: it reads `DeploymentContext`+`ExecutionState` from the Execution Store and the matching `CanonicalIntent` from the Intent Store, never writing to either, and appends one record via `jsonl_writer.append_jsonl()` (the same generic primitive `audit_log.py` already used, whose docstring had reserved this exact reuse since Milestone 2). Wired into `app/main.py` at the two places a deployment currently reaches a terminal state: the end of the background pipeline (`STABLE`) and `deny_deployment` (`FAILED`) — both call sites wrapped in the same "failures must never affect the response/state" pattern already established for `log_denial`.

**Scope decision, made explicitly during the readiness review:** the record captures `CanonicalIntent` + `DeploymentContext` + `ExecutionState` together — expanded from this document's original "`CanonicalIntent` + final `ExecutionState`" wording once it was pointed out that including `DeploymentContext` gives `correlation_id` (Contract #1, previously unconsumed since it was added) its first real consumer, at no cost in new abstractions or persistence. No API surface was added — Contract #2 names no Knowledge Capture read endpoint, and the checkpoint below is validated by reading the file directly, exactly as the existing audit-denial JSONL file already is in `tests/integration/milestone2_smoke_test.py`.

**Checkpoint:** `tests/integration/knowledge_capture_smoke_test.py` — a deployment reaching `STABLE` produces exactly one new record whose `canonical_intent`/`deployment_context`/`execution_state` match Nautobot and SQLite exactly (including `correlation_id`); a denied production deployment produces a `lifecycle_state=failed` record too. 3 new unit tests (`test_knowledge_capture.py`, zero Docker, using a minimal fake intent store). Full regression (Milestones 1-3 + Business Approval + Domain Materialization, 33 unit tests total, all 6 integration checkpoints) re-run unchanged and still passing — i.e. Knowledge Capture is a read-only reflection of the other two stores, not a fourth independent source of truth (consistent with [Contract #3](../11-Specifications/03-Platform-Execution-Model-Specification.md) §5).

**Real finding, not new architectural debt:** `correlation_id` (Contract #1) had no consumer from the moment it was added through the Platform v0.4 Readiness Review. This milestone gives it its first — every captured record now threads the same `correlation_id` a deployment attempt carries throughout its lifecycle, ready for a future Platform Events Specification (Tier 2, ADR-011) to key on, without building any tracing infrastructure now.

## M6 — End-to-end test script

A single script (not a manual walkthrough) that performs the full Success Criteria sequence against the live lab and exits non-zero on any deviation.

**Checkpoint:** this is the actual deliverable. Vertical Slice v0.1 is "done" when this script passes on a clean run.

## M6A — Real Terraform Integration ✅ Complete (2026-07-16)

Implemented after a Capability Readiness Review found no blocker beyond small, contract-aligning corrections (no Architecture Exception Report required). Replaces `terraform_stub.py`'s simulated success with the already-proven Phase 3 Terraform module (`platform/terraform/aci/`), invoked exactly as it was run by hand — `terraform init` → `plan` → `apply` against a freshly regenerated NetAsCode YAML.

**What was built:** `app/terraform_executor.py` (replaces `terraform_stub.py` — not kept alongside it) calls `platform/python/generate_aci.py`'s own generator functions (`NautobotClient`, `build_netascode_yaml`) directly — no provider abstraction was introduced for the single existing domain. It reads ACI credentials from Vault (`secret/lab/platform`, the same secret `scripts/load-vault-creds.sh` already read by hand) and runs `terraform init/plan/apply` as a subprocess against the unmodified Terraform module.

**Contract #3 §2 correction, found during the readiness review:** the M3 stubs had `ACCEPTED→DEPLOYING` and `DEPLOYING→VALIDATING` inverted relative to Contract #3's explicit ownership table (Execution Plane owns the former and `DEPLOYING→FAILED`; Validation owns the latter). This milestone corrected it: `workflow_stub.py` (which performed `ACCEPTED→DEPLOYING` on the Workflow Engine's behalf) is retired entirely; `terraform_executor.py` now owns `ACCEPTED→DEPLOYING` (its own entry) and `DEPLOYING→FAILED` (on any execution error — genuinely reachable for the first time, since no stub ever failed); `validation_stub.py` gained its own `DEPLOYING→VALIDATING` entry transition, including `deployed_at` (relocated from the old `terraform_stub.py`, which set it at the same logical point). `execution_store.py`'s `_ALLOWED_TRANSITIONS` gained `DEPLOYING → FAILED` — a hard blocker without it. None of this touched Contract #1-#3 or any ADR; it aligned implementation with what Contract #3 already specified.

`main.py`'s `_run_deployment_pipeline()` stays orchestration-only: it invokes `terraform_executor.execute_deployment()` then checks the resulting `lifecycle_state` — if `FAILED`, Knowledge Capture runs and validation is skipped (since `VALIDATING` is only reachable from `DEPLOYING`); otherwise `validation_stub.simulate_validation()` runs as before. No Terraform-specific exception handling exists in the Platform API (ADR-004) — `terraform_executor.execute_deployment()` never raises to its caller, it always resolves internally to either `DEPLOYING` (success) or `FAILED`.

**Packaging:** the platform-api image now installs the Terraform CLI (pinned to the same version already proven against the module's existing state) and reuses `platform/python/` (the generator) via a build-time `additional_context`, exactly like `platform/canonical_intent/`. `platform/terraform/aci/` itself is a live, read-write bind mount (not a build-time copy) — the same host directory Phase 3 already ran `terraform apply` in by hand, so its existing `.terraform/` cache and `terraform.tfstate` are reused and persist naturally across container rebuilds, with no separate state-sync mechanism needed. A `VAULT_TOKEN` environment variable was added (required, fail-fast, matching `NAUTOBOT_TOKEN`'s existing pattern) — platform-api had never read a Vault secret before this milestone, only used `VAULT_ADDR` for an unauthenticated health check.

**Real finding, fixed during implementation:** concurrent deployments (e.g. running multiple integration tests back-to-back) can trigger `terraform plan`/`apply` calls against the same shared local state file at the same time, and Terraform's state lock fails immediately by default rather than waiting. Fixed with `-lock-timeout=60s` on every Terraform CLI invocation — a standard Terraform CLI flag, not a platform abstraction. The existing M3/Business Approval/Knowledge Capture integration tests' poll timeouts were also increased (10s → 90s) since real `terraform init/plan/apply` against a live APIC takes real time (observed ~15-20s), unlike the near-instant stub they were originally written against.

**Checkpoint:** `tests/integration/real_terraform_smoke_test.py` — a deployment reaching `STABLE` is independently verified against the **live APIC** (not just `GetDeploymentStatus` or Nautobot), confirming the tenant actually exists with `annotation: "orchestrator:terraform"`; a deliberate failure (Vault stopped mid-test, mirroring `milestone2_smoke_test.py`'s existing OPA-unavailable pattern) reaches `FAILED`, is recorded by Knowledge Capture, writes no audit-log entry (not a Technical Policy denial), and remains observable only via `GetDeploymentStatus` (HTTP contract unchanged). 9 new unit tests (`test_terraform_executor.py`, `subprocess.run` mocked, zero Docker/Terraform/Nautobot/Vault required) plus updates to `test_execution_store.py` and the renamed-scope `test_deployment_stubs.py` (now Validation-only; `workflow_stub`/`terraform_stub` tests removed). Full regression — 43 unit tests, all 7 integration checkpoints — re-run and passing.

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
