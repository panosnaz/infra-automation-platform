---
type: adr
domain: platform
status: historical
tags: [workflow, n8n]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# ADR-005 — Workflow Orchestration

**Status:** Accepted

**Date:** 2026-06-29

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-002 — Terraform Owns Desired State Provisioning
- ADR-003 — Ansible Owns Day-2 Operations
- ADR-004 — Platform API as the Unified Platform Interface

---

# Context

The Network Platform Engineering Platform consists of multiple independent services responsible for engineering intent, infrastructure provisioning, operational automation, validation, observability, knowledge management and AI assistance.

Executing engineering activities requires coordinating these services in a predictable, auditable and repeatable manner.

Examples include:

- Provisioning a new Cisco ACI tenant
- Deploying a VXLAN EVPN fabric
- Creating Azure networking resources
- Running compliance validation
- Performing Day-2 maintenance
- Responding to operational events

Each workflow may involve multiple platform components and execution engines.

Without centralized workflow orchestration, execution logic becomes fragmented across scripts, pipelines and automation tools, resulting in inconsistent behavior and duplicated logic.

---

# Problem Statement

How should complex engineering workflows be coordinated across multiple platform capabilities?

Should individual tools orchestrate one another directly, or should workflow execution be managed by a dedicated orchestration capability?

---

# Decision

The platform shall implement a centralized Workflow Orchestration capability.

All engineering workflows shall be coordinated through the Platform Control Plane using a workflow engine.

The workflow engine is responsible for coordinating execution.

Individual automation tools remain responsible only for performing their assigned tasks.

---

# Responsibilities

The Workflow Orchestration capability owns:

- Workflow execution
- Task sequencing
- Dependency resolution
- Conditional execution
- Parallel execution
- Retry logic
- Timeout handling
- Scheduling
- Event processing
- Notifications
- Human approval steps
- Workflow state tracking

The workflow engine does not own:

- Infrastructure intent
- Infrastructure provisioning
- Device configuration
- Validation logic
- Monitoring
- **Business logic**
- **Policy enforcement**
- **Intent translation or normalisation**
- **Canonical Intent generation**

Business logic is the exclusive responsibility of the Platform API.

The workflow engine receives a Canonical Intent from the Event Bus and orchestrates execution.

It does not decide what the intent means or whether it is valid.

These remain the responsibility of dedicated platform components.

---

# Architectural Position

The workflow engine operates inside the Platform Control Plane.

```text
Users
     │
     ▼
Platform API
     │
     ▼
Platform Control Plane
     │
     ▼
Workflow Engine
     │
     ├──────────────┐
     ▼              ▼
Terraform      Ansible
     │              │
     ├──────────────┤
     ▼              ▼
Validation    Observability
     │
     ▼
Knowledge Layer
```

The workflow engine coordinates execution but does not perform infrastructure changes itself.

---

# Standard Workflow Lifecycle

Every workflow follows the same lifecycle.

```text
Request
   │
   ▼
Validation
   │
   ▼
Approval (if required)
   │
   ▼
Execution
   │
   ▼
Validation
   │
   ▼
Observability
   │
   ▼
Knowledge Capture
   │
   ▼
Workflow Complete
```

This lifecycle provides consistency across all automation domains.

---

# Workflow Categories

The platform supports several workflow types.

## Provisioning

Examples:

- New tenant
- New VRF
- Azure Landing Zone
- VXLAN Fabric Deployment

Primary execution engine:

Terraform

---

## Operational

Examples:

- Maintenance
- BFD updates
- Interface changes
- Configuration backup

Primary execution engine:

Ansible

---

## Validation

Examples:

- pyATS validation
- Catfish verification
- Compliance checks
- Connectivity testing

Primary execution engine:

Validation Frameworks

---

## Event-Driven

Examples:

- Monitoring alerts
- Drift detection
- Secret rotation
- Incident response

Primary execution engine:

Workflow Engine coordinating one or more automation tools.

---

# Human-in-the-Loop

Not every workflow should execute automatically.

The orchestration layer supports:

- CAB approval
- Manual approval
- Emergency override
- Change window enforcement
- Peer review
- Operational checkpoints

Automation enhances engineering judgement rather than replacing it.

---

# Event-Driven Execution

The workflow engine responds to platform events.

Typical events include:

- Engineering request submitted
- Pull request approved
- Terraform completed
- Ansible playbook finished
- Validation failed
- Compliance violation detected
- Infrastructure drift detected
- Monitoring alert received
- Secret rotated
- Scheduled maintenance window

Events initiate workflows without requiring manual intervention.

---

# Error Handling

The orchestration layer standardizes workflow error handling.

Capabilities include:

- Automatic retries
- Rollback initiation
- Failure notifications
- Escalation
- Audit logging
- Workflow suspension
- Manual intervention

This behavior remains consistent regardless of the execution engine.

---

# Technology Independence

Workflow orchestration is an architectural capability.

Current implementation:

- n8n

Future implementations could include:

- Temporal
- Camunda
- Kestra
- StackStorm
- Apache Airflow
- Custom Python services

Changing the implementation must not alter the architecture.

---

# Integration with Platform Components

| Component | Interaction |
|------------|-------------|
| Platform API | Receives requests |
| Nautobot | Supplies engineering intent |
| Cisco NetAsCode | Generates canonical models |
| Terraform | Executes provisioning tasks |
| Ansible | Executes operational tasks |
| Validation Framework | Performs independent verification |
| Observability Platform | Supplies telemetry |
| Knowledge Layer | Stores workflow outcomes |
| AI Layer | Provides recommendations |

The workflow engine coordinates these interactions without duplicating their responsibilities.

---

# Benefits

Centralized workflow orchestration provides:

- Consistent execution
- Reduced coupling
- Reusable workflows
- Standardized governance
- Better auditability
- Improved error handling
- Event-driven automation
- Easier platform evolution
- Clear separation of responsibilities

---

# Trade-Offs

The workflow engine introduces:

- Additional platform infrastructure
- Workflow lifecycle management
- Operational monitoring requirements
- Workflow version management

These trade-offs are justified by the significant gains in consistency, governance and maintainability.

---

# Alignment with Platform Principles

This decision supports:

- Platform Before Tools
- Separation of Responsibilities
- Event-Driven Automation
- Closed-Loop Engineering
- API-First Architecture
- Security by Design
- Technology Independence
- Human Governance
- Modularity

---

# Future Considerations

Future enhancements may include:

- AI-generated workflows
- Dynamic workflow composition
- Multi-site orchestration
- Multi-cloud orchestration
- Workflow simulation
- Policy-as-Code integration
- Workflow analytics
- Self-healing automation

These enhancements build upon the orchestration capability without changing its architectural role.

---

# Summary

The Workflow Orchestration capability coordinates all engineering workflows within the Network Platform Engineering Platform.

It provides a consistent execution model across provisioning, operations, validation and event-driven automation while maintaining clear separation between orchestration and execution.

By centralizing workflow coordination within the Platform Control Plane, the platform achieves greater consistency, governance, scalability and maintainability while remaining independent of any specific orchestration technology.