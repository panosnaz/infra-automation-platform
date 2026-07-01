# ADR-004 — Platform Control Plane as the Single Orchestration Layer

**Status:** Accepted

**Date:** 2026-06-29

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

* ADR-001 — Nautobot as the Source of Truth
* ADR-002 — Terraform Owns Desired State Provisioning
* ADR-003 — Ansible Owns Day-2 Operations

---

# Context

The Network Platform Engineering Platform integrates multiple technologies to automate infrastructure provisioning, operations, validation and lifecycle management.

Core platform components include:

* Nautobot
* Cisco NetAsCode
* Terraform
* Ansible
* Validation Frameworks
* Observability Platform
* Secret Management
* AI Engineering Assistants

Without a common orchestration layer, every component would require direct integrations with multiple other components.

For example:

```text
Terraform
   ├── Nautobot
   ├── Vault
   ├── Validation
   ├── Grafana
   ├── AI
   └── Notification Services

Ansible
   ├── Nautobot
   ├── Vault
   ├── Validation
   ├── Grafana
   ├── AI
   └── Notification Services
```

As the platform grows, the number of integrations increases rapidly, leading to:

* Tight coupling
* Duplicate logic
* Inconsistent security
* Difficult maintenance
* Limited scalability
* Increased testing complexity

A central orchestration capability is therefore required.

---

# Problem Statement

How should independent platform capabilities collaborate without becoming tightly coupled?

Should automation components communicate directly with one another, or should all execution be coordinated through a common orchestration layer?

---

# Decision

The platform shall implement a single Platform Control Plane responsible for coordinating all infrastructure execution.

No automation component shall directly orchestrate another component outside the Control Plane.

All execution workflows pass through the Platform Control Plane.

The Platform Control Plane becomes the authoritative execution coordinator for the platform.

---

# Responsibilities

The Platform Control Plane owns orchestration, not infrastructure.

Its responsibilities include:

* Workflow orchestration
* API mediation
* Authentication
* Authorization
* RBAC enforcement
* Approval workflows
* Secret retrieval
* Event routing
* Audit logging
* Job scheduling
* Retry logic
* Notifications
* Workflow state management
* Execution coordination

The Control Plane deliberately avoids infrastructure-specific logic.

---

# Architectural Position

The Platform Control Plane sits between Engineering Intent and infrastructure execution.

```text
Engineers
     │
     ▼
Nautobot
(Source of Truth)
     │
     ▼
Platform API
     │
     ▼
Platform Control Plane
     │
     ▼
Cisco NetAsCode
     │
     ▼
Terraform / Ansible
     │
     ▼
Infrastructure
     │
     ▼
Validation
     │
     ▼
Observability
```

Every infrastructure action passes through this architectural path.

---

# Why Direct Integrations Are Prohibited

Direct communication between automation components introduces unnecessary coupling.

For example:

```text
Terraform
     │
     ├────► Vault
     ├────► pyATS
     ├────► Grafana
     ├────► AI
     └────► Notification Service

Ansible
     │
     ├────► Vault
     ├────► pyATS
     ├────► Grafana
     ├────► AI
     └────► Notification Service
```

This architecture results in:

* Repeated authentication logic
* Duplicate error handling
* Multiple audit implementations
* Inconsistent approval mechanisms
* Divergent operational workflows

Instead, all coordination occurs through the Control Plane.

---

# Standard Execution Pattern

Every platform workflow follows the same execution model.

```text
Request
    │
    ▼
Platform API
    │
    ▼
Platform Control Plane
    │
    ▼
Execution Engine
    │
    ▼
Validation
    │
    ▼
Observability
    │
    ▼
Knowledge Capture
```

This pattern applies consistently across all platform capabilities.

---

# Workflow Orchestration

The Platform Control Plane coordinates all execution activities.

Examples include:

* Infrastructure provisioning
* Day-2 operations
* Validation pipelines
* Compliance checks
* Drift remediation
* Secret retrieval
* Maintenance windows
* Scheduled automation
* Event-driven workflows
* AI-approved engineering tasks

The workflow engine determines execution order and dependency management.

---

# Event Processing

The Control Plane is responsible for processing platform events.

Typical events include:

* Service request submitted
* Deployment approved
* Deployment completed
* Validation failed
* Drift detected
* Monitoring alert
* Secret rotated
* Change window opened
* AI recommendation approved

Each event may trigger one or more workflows.

---

# Governance

All execution inherits governance from the Platform Control Plane.

Governance capabilities include:

* RBAC
* Approval workflows
* Audit logging
* Change tracking
* Policy enforcement
* Execution history
* Workflow traceability

Individual automation tools should not implement independent governance mechanisms.

---

# Integration with Platform Components

## Nautobot

Provides Engineering Intent.

Never executes infrastructure.

---

## Cisco NetAsCode

Provides the Canonical Engineering Model.

Never orchestrates workflows.

---

## Terraform

Executes declarative provisioning.

Never coordinates external workflows.

---

## Ansible

Executes procedural operational automation.

Never owns orchestration.

---

## Validation Framework

Verifies infrastructure independently.

Never initiates deployments.

---

## Observability Platform

Provides telemetry and operational visibility.

Never controls execution.

---

## AI Engineering Layer

Provides recommendations, analysis and engineering assistance.

Never executes infrastructure directly.

All AI-initiated actions require approval through the Platform Control Plane.

---

# Technology Independence

The Platform Control Plane represents an architectural capability rather than a specific product.

The current implementation may include:

* Platform API
* n8n
* Python services
* Event bus
* Secret management integration

Future implementations may replace individual technologies without changing the architecture.

The Control Plane remains a stable architectural concept regardless of implementation.

---

# Benefits

Implementing a central Control Plane provides:

* Loose coupling
* Consistent governance
* Reusable workflows
* Centralised security
* Standardised integrations
* Simplified testing
* Improved observability
* Easier platform evolution
* Better AI integration
* Reduced operational complexity

---

# Trade-Offs

Introducing a Platform Control Plane also introduces additional responsibilities.

These include:

* Workflow management
* Platform availability
* API lifecycle management
* Event processing
* Operational monitoring

These responsibilities are acceptable because they centralise complexity rather than distributing it across every platform component.

---

# Alignment with Platform Principles

This decision directly supports:

* Single Responsibility
* Platform Before Tools
* API-First Architecture
* Separation of Responsibilities
* Event-Driven Automation
* Closed-Loop Engineering
* Security by Design
* Human Governance
* Technology Independence
* Modularity

---

# Future Considerations

The Platform Control Plane is expected to evolve as the platform grows.

Future capabilities may include:

* Policy-as-Code
* Event streaming
* Self-service portals
* Service catalog integration
* AI-assisted workflow generation
* Multi-site orchestration
* Multi-cloud orchestration
* Dynamic approval policies
* Advanced scheduling
* Workflow analytics

These enhancements extend the Control Plane without altering its architectural role.

---

# Summary

The Platform Control Plane is the central orchestration capability of the Network Platform Engineering Platform.

It separates engineering intent from execution, enforces governance, coordinates workflows and provides a consistent execution model across all supported infrastructure domains.

By preventing direct orchestration between platform components, this decision creates a modular, scalable and maintainable architecture that can evolve over time while preserving a consistent operating model.

The Platform Control Plane is therefore the architectural backbone of the platform and the primary mechanism through which all infrastructure automation is executed.
