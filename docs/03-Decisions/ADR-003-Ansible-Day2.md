# ADR-003 — Ansible Owns Day-2 Operations

**Status:** Accepted

**Date:** 2026-06-29

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

* ADR-001 — Nautobot as the Source of Truth
* ADR-002 — Terraform Owns Desired State Provisioning

---

# Context

The platform adopts a hybrid Infrastructure as Code (IaC) approach to automate the lifecycle of network infrastructure across Cisco ACI, Cisco Nexus VXLAN EVPN, Microsoft Azure and future infrastructure domains.

While Terraform is the primary provisioning engine, infrastructure management extends far beyond initial deployment.

Operational activities such as maintenance, compliance, troubleshooting, health verification and incident response require procedural workflows that are not well suited to Terraform's declarative model.

Without a clear ownership model, engineers risk using Terraform for operational automation, resulting in:

* Complex Terraform modules
* Frequent state drift
* Manual state manipulation
* Difficult rollback procedures
* Reduced operational agility
* Blurred separation of responsibilities

This ADR establishes the operational ownership model for Day-2 and Day-N activities.

---

# Problem Statement

Who is responsible for infrastructure operations after the initial deployment has been completed?

Should Terraform manage the complete infrastructure lifecycle, or should operational automation be delegated to a dedicated workflow engine?

---

# Decision

Terraform owns infrastructure provisioning.

Ansible owns operational automation.

Terraform is responsible for creating, modifying and removing approved infrastructure resources.

Ansible is responsible for executing repeatable operational procedures throughout the lifetime of the deployed infrastructure.

Operational automation is executed through the Platform Control Plane and coordinated by the Workflow Engine.

---

# Engineering Lifecycle Ownership

The platform distinguishes between multiple operational phases.

| Lifecycle Phase                             | Primary Owner                               |
| ------------------------------------------- | ------------------------------------------- |
| Day-0 – Initial Infrastructure Provisioning | Terraform                                   |
| Day-1 – Initial Service Configuration       | Terraform (with optional Ansible bootstrap) |
| Day-2 – Operational Changes                 | Ansible                                     |
| Day-N – Continuous Operations               | Ansible                                     |

This separation provides clear ownership throughout the infrastructure lifecycle.

---

# Responsibilities

## Terraform Responsibilities

Terraform owns declarative infrastructure provisioning.

Typical responsibilities include:

* Cisco ACI Tenants
* VRFs
* Bridge Domains
* Application Profiles
* Endpoint Groups
* Contracts
* Azure VNets
* Azure Route Tables
* Azure Firewalls
* Azure Load Balancers
* Azure Application Gateways
* Infrastructure lifecycle management
* Desired state reconciliation

Terraform determines **what infrastructure should exist**.

---

## Ansible Responsibilities

Ansible owns procedural operational automation.

Typical responsibilities include:

* Configuration backups
* Configuration collection
* BFD policy updates
* Interface descriptions
* Operational tuning
* Certificate rotation
* Password rotation
* Health checks
* Compliance remediation
* Maintenance windows
* Incident automation
* Rolling configuration updates
* Validation execution
* Configuration audits
* Software upgrade workflows
* Operational reporting

Ansible determines **how operational work is performed**.

---

# Responsibility Matrix

| Capability                | Terraform | Ansible |
| ------------------------- | --------- | ------- |
| Create Infrastructure     | ✓         |         |
| Modify Desired State      | ✓         |         |
| Destroy Infrastructure    | ✓         |         |
| Operational Configuration |           | ✓       |
| Maintenance               |           | ✓       |
| Compliance                |           | ✓       |
| Health Checks             |           | ✓       |
| Configuration Collection  |           | ✓       |
| Configuration Backup      |           | ✓       |
| Incident Response         |           | ✓       |
| Rolling Changes           |           | ✓       |
| Operational Reporting     |           | ✓       |
| Validation Trigger        |           | ✓       |

Ownership is intentionally exclusive wherever practical.

---

# Platform Workflow

Every operational workflow follows the same architectural pattern.

```text
Engineer
      │
      ▼
Nautobot
      │
      ▼
Platform API
      │
      ▼
Workflow Engine (n8n)
      │
      ├───────────────┐
      ▼               ▼
Terraform         Ansible
      │               │
      └───────┬───────┘
              ▼
Managed Infrastructure
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

The Platform Control Plane selects the appropriate execution engine based on the requested engineering activity.

---

# Why Terraform Is Not Used for Day-2 Operations

Terraform is designed to manage declarative infrastructure state.

It is not intended to execute procedural operational workflows.

Typical limitations include:

* Sequential operational procedures
* Interactive maintenance activities
* Incident response workflows
* Health verification
* Configuration backups
* Temporary operational changes
* Conditional execution
* Multi-step remediation

Attempting to implement these activities in Terraform introduces unnecessary complexity and increases operational risk.

---

# Why Ansible Is Used for Day-2 Operations

Ansible is procedural, agentless and well suited for operational automation.

It excels at:

* Executing ordered tasks
* Conditional logic
* Runtime decision making
* Multi-device workflows
* Operational maintenance
* Configuration collection
* Validation
* Compliance automation

These characteristics make Ansible the preferred automation engine for Day-2 operations.

---

# Integration with Validation

Every Ansible workflow should trigger independent validation.

Typical workflow:

```text
Run Playbook
      │
      ▼
Infrastructure Updated
      │
      ▼
Validation Pipeline
      │
      ▼
Observability
      │
      ▼
Knowledge Repository Updated
```

Operational success is determined by successful validation rather than playbook completion alone.

---

# Integration with the Platform Control Plane

Ansible does not execute independently.

All playbooks are orchestrated through the Platform Control Plane.

Responsibilities include:

* Authentication
* Authorization
* Secret retrieval
* Approval workflows
* Scheduling
* Audit logging
* Notifications
* Event handling
* Workflow coordination

This preserves governance and ensures operational consistency across all infrastructure domains.

---

# Future Considerations

The operational model defined by this ADR applies to all supported infrastructure technologies.

Current targets include:

* Cisco ACI
* Cisco Nexus VXLAN EVPN
* Microsoft Azure Networking

Future platforms may include:

* Kubernetes
* VMware
* AWS
* Palo Alto Networks
* F5 BIG-IP
* Linux
* Windows Server

The architectural principle remains unchanged:

Terraform provisions infrastructure.

Ansible operates infrastructure.

---

# Consequences

## Positive

* Clear separation of responsibilities.
* Simplified Terraform modules.
* Reduced infrastructure drift.
* Improved operational flexibility.
* Easier maintenance workflows.
* Consistent Day-2 operating model.
* Better integration with validation and observability.
* Reusable operational automation across multiple platforms.

## Trade-Offs

* Two automation engines must be maintained.
* Engineers require familiarity with both declarative and procedural automation.
* Workflow orchestration becomes a critical platform capability.

These trade-offs are acceptable because they provide a cleaner, more scalable architecture.

---

# Alignment with Platform Principles

This decision directly supports the following Platform Principles:

* Single Responsibility
* Separation of Responsibilities
* Platform Before Tools
* Engineering Intent Before Configuration
* Validation First
* Closed-Loop Engineering
* Event-Driven Automation
* API-First Architecture
* Security by Design
* Human Governance

---

# Summary

Terraform and Ansible are complementary technologies within the Network Platform Engineering Platform.

Terraform owns declarative infrastructure provisioning and desired state management.

Ansible owns procedural operational automation throughout the infrastructure lifecycle.

This separation creates a scalable, maintainable and governable operating model that supports both initial deployments and long-term infrastructure operations while remaining consistent across all supported technology domains.
