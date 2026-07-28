---
type: adr
domain: platform
status: active
tags: [platform-v2, replacement, mcp, gitlab]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# ADR-016 — Platform v2 Replacement Architecture

**Status:** Accepted

**Date:** 2026-07-28

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-002 — Terraform Owns Desired State Provisioning
- ADR-003 — Ansible Owns Day-2 Operations
- ADR-004 — Platform API as the Unified Platform Interface (superseded by this ADR)
- ADR-005 — Workflow Orchestration (superseded by this ADR)
- ADR-006 — Platform Control Plane as the Single Orchestration Layer (superseded by this ADR)
- ADR-007 — Cisco NetAsCode as the Canonical Engineering Model
- ADR-009 — Knowledge Layer as the Engineering Memory of the Platform
- ADR-010 — AI as an Engineering Assistant
- ADR-011 — Event-Driven Automation
- ADR-014 — Technical Policy Enforcement (OPA)
- ADR-015 — Deployment Approval as a Distinct Capability from Technical Policy (superseded by this ADR)

---

# Context

The Platform API (Contract #2, Contract #3, and the ADRs listed above as superseded) was implemented end-to-end through Milestone 6A: Intent Lifecycle, Technical Policy, Domain Materialization, Business Approval, Knowledge Capture, and Real Terraform Integration, backed by a 44-unit-test and 7-integration-test regression suite, all passing against live infrastructure.

During that implementation, a recurring pattern emerged across multiple readiness reviews: the Platform API's custom Python code was re-implementing capabilities that enterprise-grade, already-adopted tools already provide natively. Concretely:

- `execution_store.py`'s hand-rolled SQLite lifecycle/state machine duplicates what Nautobot's native Change Log and GitLab's native pipeline status already record.
- `approval_workflow.py`'s one-rule approval gate duplicates GitLab's native protected-environment approval mechanism.
- `terraform_executor.py`'s in-process `threading.Lock`, added specifically to prevent concurrent Terraform runs from corrupting shared local state, duplicates what GitLab's native `resource_group:` keyword already provides — better, since it serializes across runners, not just within one process.

At the same time, a new requirement emerged: AI agents (VS Code Copilot Agent, Claude Desktop, future assistants) needed to become first-class operators of the platform, not just engineering assistants (per ADR-010's original framing). This called for a Model Context Protocol (MCP) server as the AI-facing interface — a capability the Platform API was never designed to expose.

---

# Problem Statement

Should the Platform API be extended and migrated incrementally to support AI agents and reduce its custom orchestration surface, or should it be replaced outright by a combination of existing enterprise-grade platforms (Nautobot, GitLab) plus a new, deliberately thin MCP Server?

---

# Decision

The platform adopts **Platform v2 as a replacement architecture, not a migration.**

The Platform API (`main.py`, `execution_store.py`, `approval_workflow.py`, `terraform_executor.py`, `workflow_stub.py`, `validation_stub.py`, `nautobot_store.py`) becomes legacy (Platform v1). It is not preserved, ported, or kept compatible.

Their responsibilities move to:

- **Nautobot** — remains the Source of Truth for desired state, inventory, topology, allocations, lifecycle, and engineering metadata. Its native Change Log replaces the custom execution state history.
- **GitLab (CE + Runner)** — becomes the execution engine: execution, approvals (protected environments), retries, concurrency/resource locking (`resource_group:`), artifacts, logs, and pipeline history.
- **MCP Server** — becomes the only entry point for AI agents. It owns tool registration, input validation, authentication, the Nautobot/GitLab/Vault API wrappers, and deployment status aggregation. It must never become another orchestration engine.

The proven domain automation (`platform/python/` generator, `platform/terraform/aci/`, `platform/ansible/aci/`, `tests/pyats/`) is reused unmodified — only its execution environment changes, from Python subprocess calls to GitLab CI jobs.

---

# Consequences

- ADR-004, ADR-005, ADR-006, and ADR-015 are superseded. They remain in `knowledge/adr/archive/` as an accurate historical record of the architecture that was actually built and proven working — not deleted, since that implementation is what validated the domain automation this replacement continues to reuse.
- Contracts #1-#3 (`knowledge/architecture/archive/Contract-1..3-*.md`) are superseded as governing specifications. `CanonicalIntent`'s Pydantic model survives as the MCP Server's input-validation schema — a reduced role, not a deletion.
- No compatibility shim is built between Platform v1 and Platform v2. The cutover is a full replacement once Platform v2 is validated end-to-end against the same regression evidence Platform v1 already established.
- The full replacement architecture, container design, GitLab pipeline design, and MCP Server design are recorded in `knowledge/architecture/Platform-v2-Reference-Architecture.md`.
