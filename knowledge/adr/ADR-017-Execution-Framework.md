---
type: adr
domain: platform
status: active
tags: [platform-v2, execution-framework, roadmap]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# ADR-017 — Execution Framework as the Phase 2 Model

**Status:** Accepted (Stage 1/Stage 2 ownership rescoped 2026-07-28 — see ADR-018)

**Date:** 2026-07-28

**Decision Makers:** Platform Engineering Team

> **Rescoped 2026-07-05 pattern, reused 2026-07-28:** the seven named stages below remain the accepted lifecycle model. [ADR-018](ADR-018-NetAsCode-Centric-Execution-Framework.md) rescopes only Stage 1 (Intent) and Stage 2 (Validation): their artifact is NetAsCode YAML generated from Nautobot, not a Pydantic `CanonicalIntent` owned by the MCP Server. Read ADR-018 alongside this ADR for the current, accurate ownership of those two stages.

**Related ADRs:**

- ADR-008 — Validation Strategy
- ADR-009 — Knowledge Layer as the Engineering Memory of the Platform
- ADR-010 — AI as an Engineering Assistant
- ADR-014 — Technical Policy Enforcement (OPA)
- ADR-016 — Platform v2 Replacement Architecture

**Related architecture:** [`Execution-Framework.md`](../architecture/Execution-Framework.md), [`Platform-v2-Reference-Architecture.md`](../architecture/Platform-v2-Reference-Architecture.md), [`../ai/Future-AI-Integration-Design.md`](../ai/Future-AI-Integration-Design.md)

---

# Context

Phase 1 delivered the infrastructure substrate for Platform v2: GitLab CE, GitLab Runner (staged), Prometheus, Grafana, Loki, MinIO, and Traefik, alongside the already-proven Nautobot/Vault/OPA/Platform-API stack (see [`Platform-v2-As-Built.md`](../architecture/Platform-v2-As-Built.md) and the [Phase 1 Infrastructure Validation Report](../runbooks/Phase1-Infrastructure-Validation-Report.md)).

The original Roadmap ([`Roadmap.md`](../architecture/Roadmap.md)) and the Phase 1 handoff framed the next increment simply as "Phase 2 — GitLab CI": design pipeline YAML, wire Terraform and OPA together, register a runner, run a pipeline. Taken at face value, this risks jumping straight to implementation (`.gitlab-ci.yml` stage definitions) before the end-to-end **execution lifecycle** that GitLab CI is meant to serve has actually been designed.

This matters because GitLab CI is one **execution engine** choice within a larger lifecycle — Intent capture, technical Validation, Policy evaluation, human Approval, Execution, post-execution Verification, and Knowledge Capture — a lifecycle already implied piecemeal across ADR-008 (Validation), ADR-014 (Policy), ADR-016 (Approval via GitLab protected environments, Execution via GitLab CI), and ADR-009 (Knowledge Capture), but never assembled into one named, ordered model before now.

---

# Problem Statement

Should Phase 2 be scoped narrowly as "build the GitLab CI pipeline," or should it first define the complete execution lifecycle each deployment intent passes through — of which GitLab CI implements only the Execution stage — so that pipeline YAML is written against an already-agreed stage contract rather than being designed ad hoc?

---

# Decision

Phase 2 is reframed from "GitLab CI" to the **Execution Framework**: a seven-stage lifecycle —

```text
Intent → Validation → Policy → Approval → Execution → Verification → Knowledge Capture
```

Each stage is mapped to a specific Platform v2 component before any pipeline YAML is written. GitLab CI (+ Runner) implements exactly one stage — **Execution** — plus hosts the Approval gate as a native protected-environment manual job. It is not itself the framework.

The full stage-by-stage design, including which component owns each stage, what native capability it uses, and what artifact/record it produces, is recorded in [`Execution-Framework.md`](../architecture/Execution-Framework.md) — not duplicated here.

In parallel, the future AI integration — how an Obsidian-compatible knowledge base (this `knowledge/` vault), Nautobot, GitLab, Vault, OPA, and a future LangGraph reasoning layer relate to this same lifecycle — is designed now, in [`../ai/Future-AI-Integration-Design.md`](../ai/Future-AI-Integration-Design.md), even though LangGraph itself remains unimplemented until a later phase (per ADR-010's existing "AI reasons, platform executes" boundary — this decision does not change that boundary, it only gives the future reasoning layer a stage-aligned design to slot into later).

---

# Consequences

- [`Roadmap.md`](../architecture/Roadmap.md)'s Phase 2 entry is updated to reference the Execution Framework rather than describing GitLab CI pipeline work directly.
- Pipeline YAML (`.gitlab-ci.yml`, `pipelines/includes/common.gitlab-ci.yml`) is not written until the Execution Framework document exists and each stage's component mapping is agreed — this ADR is the gate that gives future pipeline work a stage contract to implement against, not a license to skip design.
- The OPA-extraction question left open at the end of Phase 1 ("does GitLab CI need to call OPA directly now that it exists?") is resolved by this framing: yes — Policy is stage 3 of the Execution Framework, implemented as a GitLab CI job calling OPA directly, replacing the Phase 1-era in-process `TechnicalPolicyClient` call pattern once the pipeline exists.
- No new component is introduced by this decision. It is a sequencing and naming decision, not an architecture change — every component referenced (MCP Server, Nautobot, OPA, GitLab, pyATS, Knowledge Layer) is already named in ADR-016 and the Platform v2 Reference Architecture.
