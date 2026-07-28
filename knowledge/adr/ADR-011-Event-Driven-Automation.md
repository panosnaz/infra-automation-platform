---
type: adr
domain: platform
status: active
tags: [event-driven]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# ADR-011 — Event-Driven Automation

**Status:** Accepted

**Date:** 2026-06-30

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-002 — Terraform Owns Desired State Provisioning
- ADR-003 — Ansible Owns Day-2 Operations
- ADR-004 — Platform API
- ADR-005 — Workflow Orchestration
- ADR-006 — Platform Control Plane
- ADR-007 — Cisco NetAsCode as the Canonical Engineering Model
- ADR-008 — Validation as an Independent Platform Capability
- ADR-009 — Knowledge Layer as the Engineering Memory of the Platform
- ADR-010 — AI as an Engineering Assistant
- ADR-014 — Technical Policy Enforcement (OPA)
- ADR-015 — Deployment Approval as a Distinct Capability from Technical Policy

---

# Context

Traditional infrastructure automation relies heavily on manually executed workflows or scheduled jobs.

Examples include:

- Nightly compliance checks
- Scheduled configuration backups
- Periodic drift detection
- Manual deployment execution

While scheduled automation remains valuable for recurring operational tasks, it is not sufficient for a modern Platform Engineering model.

The platform should react to engineering events as they occur, enabling faster feedback, reduced operational latency and improved automation consistency.

---

# Problem Statement

How should automation workflows be initiated across the platform?

Should workflows primarily rely on manual execution and scheduled jobs, or should the platform respond automatically to engineering events?

---

# Decision

The platform shall adopt an **Event-Driven Automation** architecture.

Platform capabilities publish events whenever significant engineering activities occur.

Interested platform components subscribe to these events and execute the appropriate workflows.

Automation is initiated by platform events rather than direct component-to-component coupling.

---

# Event Bus as Platform Backbone

The Event Bus is the asynchronous backbone of the platform.

Every major platform state change is represented as a named event.

Event publishers do not know or care who is listening.

Event subscribers declare their interest and react independently.

This complete decoupling is the source of platform extensibility — a new subscriber can be added without modifying any publisher.

## Event Bus Technology Selection: Deferred

This ADR decides that the platform *shall* be event-driven and defines the event contract (named events, publishers, subscribers below). It intentionally does **not** select a transport technology yet.

Kafka, RabbitMQ, and webhooks are all viable candidates and are shown together in `03c-Platform-Control-Plane.md`'s diagram as *options under consideration*, not a decision. The choice is deferred until the Platform API, Canonical Intent, and Workflow Engine exist to generate real event volume and delivery-guarantee requirements to evaluate against — selecting a transport before any producer or consumer exists would be premature technology lock-in. This is unlike every other ADR in this series, which commits to one named technology; readers should not infer a decision has been made here.

## Named Platform Events

| Event | Published By | Subscribed By |
|---|---|---|
| `IntentSubmitted` | Platform API — Intent Lifecycle (`SubmitIntent`, after Technical Policy allows and Nautobot persistence, [ADR-014](ADR-014-Policy-Enforcement.md)) | Audit, Knowledge |
| `DeploymentRequested` | Platform API — Deployment Lifecycle (`RequestDeployment` reaching `ACCEPTED`, whether immediately or after Approval Workflow resolves a `PENDING_APPROVAL` rest, [ADR-015](ADR-015-Deployment-Approval.md)) | Workflow Engine |
| `DeploymentPlanned` | Workflow Engine | Approval Service |
| `DeploymentStarted` | Workflow Engine | Observability |
| `DeploymentCompleted` | Workflow Engine / Terraform | Validation, Knowledge, Observability |
| `DeploymentFailed` | Workflow Engine / Terraform | Notification, Knowledge, Observability |
| `ValidationPassed` | Validation | Knowledge, Observability, Notification |
| `ValidationFailed` | Validation | Knowledge, Observability, Notification, Remediation |
| `DriftDetected` | Validation | Workflow Engine, Observability, Notification |
| `SecretRotated` | Vault | Workflow Engine |
| `KnowledgeUpdated` | Knowledge Layer | AI, Observability |
| `AIRecommendationPublished` | AI Layer | Platform API (as a new entry point) |

---

# Architectural Principles

Event-driven automation shall follow these principles:

- Components publish events.
- Components subscribe to events.
- Components remain loosely coupled.
- Events are immutable.
- Events describe facts, not commands.
- Workflows remain idempotent.
- Automation remains observable.
- Human approval remains part of governed workflows.

> **Elevated to a platform-wide principle (2026-07-05):** "Events describe facts, not commands" and "events are published only after the underlying state transition is durably committed" are formalized with full rationale and worked examples in [Platform Specification 03 — Platform Execution Model](../11-Specifications/03-Platform-Execution-Model-Specification.md) §3. That document is authoritative for event-timing semantics; this ADR establishes that the platform is event-driven at all.

> **Event renamed 2026-07-05:** `IntentReceived` was renamed to `IntentSubmitted` to match the `SubmitIntent` operation ([Platform Specification 02](../11-Specifications/02-Platform-API-Specification.md)) that produces it, and to avoid ambiguity now that Intent Lifecycle and Deployment Lifecycle are explicitly separate (ADR-014 / ADR-015).

---

# Event Flow

```text
Engineer
      │
      ▼
Engineering Intent
      │
      ▼
Platform API
      │
      ▼
Platform Control Plane
      │
      ▼
Event Published
      │
      ▼
Workflow Engine
      │
      ▼
Execution
      │
      ▼
Validation
      │
      ▼
Knowledge Layer
      │
      ▼
Observability
```

Each platform capability reacts independently to relevant events.

---

# Event Categories

The platform may publish events in several domains.

## Intent Events

Examples:

- Tenant Requested
- VRF Requested
- Network Service Requested
- Change Approved

---

## Deployment Events

Examples:

- Deployment Started
- Deployment Completed
- Deployment Failed
- Rollback Initiated

---

## Validation Events

Examples:

- Validation Passed
- Validation Failed
- Compliance Failed
- Connectivity Failed

---

## Operational Events

Examples:

- Configuration Drift Detected
- Device Added
- Device Removed
- Backup Completed

---

## Security Events

Examples:

- Secret Rotated
- Certificate Expired
- Unauthorized Access Detected

---

## Knowledge Events

Examples:

- ADR Created
- Runbook Updated
- Validation Report Published

---

# Responsibilities

Platform components publish events describing changes in state.

Examples include:

- Platform API
- Workflow Engine
- Terraform
- Ansible
- Validation Framework
- Observability Platform

Subscribers determine whether action is required.

---

# Loose Coupling

Components communicate through events rather than direct dependencies.

Instead of:

```text
Terraform
     │
     ▼
Ansible
```

The preferred model is:

```text
Terraform
     │
     ▼
Deployment Completed Event
     │
     ▼
Ansible Workflow
```

This reduces coupling and improves extensibility.

---

# Workflow Independence

Each workflow should be independently deployable.

Examples include:

- Infrastructure Provisioning
- Day-2 Configuration
- Validation
- Compliance
- Documentation Generation
- Notification
- Knowledge Update

Workflows may evolve independently without affecting publishers.

---

# Idempotency

Event-driven workflows must be idempotent.

Receiving the same event multiple times should not create inconsistent infrastructure state.

Each workflow should safely determine whether execution is required.

---

# Observability

Every event should be observable.

The platform should record:

- Event ID
- Event Type
- Timestamp
- Publisher
- Subscriber
- Workflow Status
- Execution Duration
- Result

These records support troubleshooting, auditing and operational analytics.

---

# Security Considerations

Events must not expose sensitive information.

Examples of prohibited event payloads include:

- Passwords
- API Keys
- Private Keys
- Tokens
- Certificates

Event consumers retrieve sensitive information from the centralized Secrets Management capability when required.

---

# Human Governance

Not every event should trigger automatic execution.

Examples requiring approval include:

- Production deployments
- Security policy changes
- Network segmentation changes
- Infrastructure deletion

The platform may pause workflow execution pending human approval.

---

# Example Engineering Workflow

```text
Engineer
      │
      ▼
Create Tenant in Nautobot
      │
      ▼
Intent Updated Event
      │
      ▼
Workflow Engine
      │
      ▼
Generate NetAsCode Model
      │
      ▼
Provision Infrastructure (Terraform)
      │
      ▼
Deployment Completed Event
      │
      ▼
Ansible Day-2 Configuration
      │
      ▼
Validation
      │
      ▼
Validation Passed Event
      │
      ▼
Knowledge Layer Updated
      │
      ▼
Observability Dashboard Updated
```

The workflow is coordinated through events rather than tightly coupled integrations.

---

# Benefits

An event-driven architecture provides:

- Loose coupling
- Faster automation
- Improved scalability
- Independent platform capabilities
- Easier extensibility
- Better observability
- Improved resilience
- Simplified integration of new services

---

# Trade-Offs

The platform accepts additional complexity in exchange for flexibility.

Trade-offs include:

- Event lifecycle management
- Workflow coordination
- Event schema governance
- Monitoring distributed workflows

These are acceptable given the architectural benefits.

---

# Alignment with Platform Principles

This decision supports:

- Platform Before Tools
- API-First Architecture
- Separation of Responsibilities
- Closed-Loop Engineering
- Validation First
- Security by Design
- AI as an Engineering Assistant
- Continuous Improvement

---

# Future Considerations

Future enhancements may include:

- Event replay
- Dead-letter queues
- Workflow retry policies
- Distributed event buses
- Cross-domain event routing
- Predictive automation
- AI-assisted workflow optimization

These enhancements extend the event-driven model without changing the underlying architectural principles.

---

# Summary

The Network Platform Engineering Platform adopts an Event-Driven Automation architecture to coordinate platform capabilities through loosely coupled events.

Rather than relying solely on manual execution or scheduled tasks, platform components publish events describing changes in engineering state.

Subscribers react to these events by executing governed workflows, enabling scalable, observable and resilient automation while preserving human oversight and architectural separation of responsibilities.