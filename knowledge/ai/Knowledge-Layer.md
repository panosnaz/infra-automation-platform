---
type: architecture
domain: platform
status: active
tags: [knowledge, ai]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# Knowledge Layer

**Project:** Network Platform Engineering Platform

**Document Type:** Architecture

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

---

# Purpose

The Knowledge Layer is a first-class architectural capability of the Network Platform Engineering Platform.

Its purpose is to capture, organize, preserve and expose engineering knowledge generated throughout the platform lifecycle.

Unlike operational data, which represents the current state of infrastructure, the Knowledge Layer preserves the accumulated engineering experience of the platform.

It enables engineers and AI assistants to understand not only *what* the platform is doing, but also *why* it behaves that way.

---

# Vision

The platform should continuously learn from engineering activities.

Knowledge should not remain trapped inside:

* Engineers' personal notes
* Chat conversations
* Runbooks
* Incident tickets
* Validation reports
* Configuration repositories

Instead, engineering knowledge becomes a managed platform asset.

---

# Architectural Position

The Knowledge Layer is the **Engineering Memory** of the platform.

It receives continuously from every major platform event and capability, not just at the end of a workflow.

```text
Platform API ──────────────────────────────────────────────► Knowledge Layer
                (IntentReceived events, request metadata)        ▲   │
                                                                 │   │
Nautobot ────────────────────────────────────────────────────────┤   │
           (intent changes, inventory updates)                   │   │
                                                                 │   │
Workflow Engine ────────────────────────────────────────────────┤   │
               (workflow outcomes, execution timings)            │   │
                                                                 │   │
Terraform / Ansible ───────────────────────────────────────────┤   │
               (DeploymentCompleted / DeploymentFailed events)   │   │
                                                                 │   │
Validation ────────────────────────────────────────────────────┤   │
           (ValidationPassed / ValidationFailed events)          │   │
                                                                 │   │
Observability ─────────────────────────────────────────────────┤   │
              (metrics, logs, traces, alerts)                    │   │
                                                                 │   │
Git ────────────────────────────────────────────────────────────┤   │
    (runbooks, ADRs, design documents, commit history)           │   │
                                                                 │   │
Incidents / Post-mortems ──────────────────────────────────────┘   │
                                                                     │
                                                                     ▼
                                                       AI Engineering Assistant
                                                                     │
                                                                     ▼
                                                       Improved Engineering Intent
```

The Knowledge Layer does not control the platform.

It is continuously enriched by the platform and continuously improves future intent.

Knowledge and Observability together close the engineering loop.

---

# Responsibilities

The Knowledge Layer is responsible for:

* Preserving engineering knowledge
* Organizing documentation
* Capturing design decisions
* Recording validation outcomes
* Maintaining engineering history
* Supporting semantic search
* Providing context to AI assistants
* Improving engineering consistency

The Knowledge Layer is **not** responsible for:

* Infrastructure provisioning
* Configuration management
* Workflow orchestration
* Validation execution
* Monitoring
* Secret management

---

# Knowledge Sources

Knowledge is collected from multiple platform capabilities.

Examples include:

## Architecture

* Architecture documents
* Reference architectures
* Platform principles
* Design standards

---

## Engineering Decisions

* Architecture Decision Records (ADRs)
* Design reviews
* Trade-off analyses

---

## Platform Operations

* Deployment history
* Workflow execution
* Operational runbooks
* Maintenance procedures

---

## Validation

* Compliance reports
* Connectivity tests
* Service validation
* Infrastructure verification

---

## Observability

* Platform metrics
* Operational trends
* Incident timelines
* Capacity reports

---

## AI Interactions

Where appropriate, summaries of AI-assisted engineering sessions may be captured as reusable knowledge after human review.

The Knowledge Layer stores validated engineering knowledge rather than raw conversations.

**Capture trigger:** an AI-assisted session becomes a candidate for capture when it results in one of: an accepted architecture decision, a diagnosed root cause, a resolved incident, or a reusable troubleshooting procedure. Routine Q&A or in-progress exploration is not captured.

**Capture format:** a short structured record containing — the question/problem, the conclusion reached, the evidence or reasoning that supported it, and links to any artifacts produced (commits, ADRs, validation reports). Not a transcript.

**Who captures it:** the human engineer who reviewed the session, not the AI itself — consistent with ADR-010's principle that AI recommendations are advisory and require human approval before becoming authoritative. This is the same human-in-the-loop gate every other Knowledge source (ADRs, runbooks, incident post-mortems) already goes through in the Knowledge Lifecycle below.

**Where it lives:** as of 2026-07-04, no dedicated storage exists for this — captured summaries live wherever the underlying artifact already lives (e.g. a commit message, an ADR's Context section, [`Current-State-v1.md`](../architecture/archive/Current-State-v1.md)'s "Bugs found and fixed" notes).

> **Update (2026-07-29):** a dedicated Knowledge Capture store now exists — MinIO (`s3://knowledge-capture/`, JSONL) plus a GitLab CI artifact, built for Execution Framework Milestone 4 (see [`Execution-Framework.md`](../architecture/Execution-Framework.md) §6 and [`Future-AI-Integration-Design.md`](Future-AI-Integration-Design.md) §2's GitLab row). It is currently scoped to one record per pipeline run (deployment outcome, commit SHA, pipeline status) — it does not yet capture the AI-assisted-session summaries this section describes (accepted decisions, diagnosed root causes, reusable procedures). Wiring AI-session capture into the same MinIO store, rather than inventing a second one, is the natural next step once that need is real — not yet scoped to a milestone.

---

# Knowledge Lifecycle

Knowledge evolves over time.

```text
Create
   │
   ▼
Review
   │
   ▼
Approve
   │
   ▼
Publish
   │
   ▼
Use
   │
   ▼
Update
   │
   ▼
Archive
```

Knowledge remains version controlled throughout its lifecycle.

---

# Knowledge Categories

Typical knowledge categories include:

* Architecture
* Standards
* ADRs
* Platform Design
* Validation
* Runbooks
* Lessons Learned
* Troubleshooting
* Operational Procedures
* Reference Material

---

# Relationship to AI

AI assistants consume knowledge rather than creating authoritative knowledge.

The Knowledge Layer provides AI with:

* Architectural context
* Engineering standards
* Platform principles
* Previous decisions
* Operational procedures
* Validation history

AI-generated content becomes part of the Knowledge Layer only after human review and approval.

---

# Relationship to Documentation

Documentation is one source of knowledge.

The Knowledge Layer also includes engineering artefacts generated during platform operation.

Examples include:

* Validation reports
* Deployment summaries
* Incident analyses
* Operational metrics
* Lessons learned

Knowledge therefore extends beyond static documentation.

---

# Search and Retrieval

Knowledge should be discoverable through multiple mechanisms.

Examples include:

* Structured navigation
* Metadata
* Tagging
* Semantic search
* Full-text search
* AI-assisted retrieval

The retrieval mechanism is an implementation detail and may evolve over time.

---

# Governance

Knowledge is governed using the same engineering practices as source code.

Changes should be:

* Version controlled
* Peer reviewed
* Traceable
* Auditable

Knowledge should remain accurate, current and maintainable.

---

# Technology Independence

The Knowledge Layer is an architectural capability rather than a specific product.

Potential implementations include:

* Markdown repositories
* Obsidian
* Enterprise wikis
* Vector databases
* Knowledge graphs
* Semantic indexes

Implementation technologies may change without affecting the architectural role of the Knowledge Layer.

---

# Benefits

A dedicated Knowledge Layer provides:

* Consistent engineering practices
* Faster onboarding
* Reduced knowledge loss
* Improved troubleshooting
* Better architectural governance
* Enhanced AI assistance
* Reusable engineering experience
* Continuous organizational learning

---

# Alignment with Platform Principles

The Knowledge Layer supports:

* Single Source of Truth (for engineering knowledge)
* Platform Before Tools
* Everything as Code
* Version Everything
* Closed-Loop Engineering
* Continuous Improvement
* AI Assists, Platform Executes

---

# Future Vision

As the platform evolves, the Knowledge Layer may support:

* Semantic retrieval
* Engineering memory
* AI context generation
* Automated documentation updates
* Knowledge graphs
* Cross-domain relationships
* Engineering recommendations

These capabilities extend the platform without changing the architectural role of the Knowledge Layer.

---

# Summary

The Knowledge Layer transforms engineering knowledge into a managed platform capability.

Rather than allowing architectural decisions, operational experience and validation outcomes to remain isolated across documents, tools and individuals, the platform continuously captures and organizes this information into a reusable engineering asset.

By treating knowledge as a first-class component of the architecture, the platform improves consistency, accelerates engineering workflows and enables AI assistants to provide informed, context-aware guidance while preserving human governance.
