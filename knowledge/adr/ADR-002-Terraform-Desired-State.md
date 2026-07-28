---
type: adr
domain: platform
status: active
tags: [terraform]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# ADR-002 – Terraform as the Declarative Provisioning Engine

**Status:** Accepted

**Date:** 2026-06-28

**Decision Makers:** Platform Engineering Team

---

# Context

The Network Platform Engineering Platform requires a reliable, repeatable and deterministic mechanism to provision infrastructure.

The platform manages multiple infrastructure domains, beginning with:

* Cisco ACI
* Cisco Nexus VXLAN EVPN
* Azure Networking

Infrastructure provisioning must satisfy the following requirements:

* Declarative
* Repeatable
* Idempotent
* Version controlled
* Auditable
* Testable
* Scalable

The platform also distinguishes between **engineering intent** and **infrastructure implementation**.

Engineering intent belongs in Nautobot.

Infrastructure provisioning is a separate responsibility.

---

# Decision

Terraform is adopted as the **declarative infrastructure provisioning engine** for the platform.

Terraform consumes engineering intent from the Platform Control Plane and provisions the required infrastructure.

Terraform does **not** become the authoritative Source of Truth.

---

# Architectural Principle

The platform follows the principle:

> **Nautobot owns intent. Terraform owns provisioning.**

Terraform describes **how** infrastructure should be created.

Nautobot describes **what** the organisation wants.

---

# Decision Drivers

The following requirements influenced this decision.

## Declarative Infrastructure

Infrastructure should be defined as code.

Engineers describe the desired infrastructure rather than issuing imperative commands.

Terraform naturally supports this model.

---

## Idempotent Execution

Repeated deployments should produce the same infrastructure state.

Terraform provides built-in state reconciliation.

---

## Version Control

Infrastructure definitions should be maintained in Git.

Every infrastructure change becomes reviewable and auditable.

---

## Provider Ecosystem

Terraform supports multiple infrastructure providers.

Examples include:

* Cisco ACI
* Azure
* VMware
* AWS
* Kubernetes

This aligns with the platform's multi-domain vision.

---

## Reusable Modules

Infrastructure should be constructed from reusable modules.

Examples:

* Tenant modules
* VRF modules
* Bridge Domain modules
* Application Profile modules

This promotes consistency and maintainability.

---

# Alternatives Considered

## Option 1 — Direct API Calls

Advantages

* Maximum flexibility
* No additional abstraction

Disadvantages

* High development effort
* Difficult to maintain
* No state management
* No planning capability
* Increased implementation complexity

Decision

Rejected.

---

## Option 2 — Python Provisioning Scripts

Advantages

* Flexible
* Familiar to engineers

Disadvantages

* Imperative programming model
* No built-in state management
* Increased maintenance burden
* Reinvention of infrastructure lifecycle management

Decision

Rejected.

Python remains appropriate for supporting automation, not primary provisioning.

---

## Option 3 — Ansible

Advantages

* Simple
* Agentless
* Operational flexibility

Disadvantages

* Better suited to configuration management
* Limited infrastructure state management
* Less suitable for large declarative infrastructure provisioning

Decision

Rejected as the primary provisioning engine.

Ansible remains responsible for Day-2 operational configuration.

---

## Option 4 — Terraform

Advantages

* Declarative
* Idempotent
* State-aware
* Mature ecosystem
* Modular
* Version controlled
* Plan-before-apply workflow
* Strong multi-provider support

Disadvantages

* State management complexity
* Learning curve
* Provider limitations

Decision

Accepted.

---

# Relationship with Cisco NetAsCode

Terraform modules should consume Cisco NetAsCode (NaC) data models wherever possible.

The platform deliberately separates:

Engineering Intent

↓

Cisco NetAsCode Data Model

↓

Terraform Modules

↓

Cisco APIC

This separation reduces coupling between engineering intent and infrastructure implementation.

---

# Relationship with Platform Components

| Component       | Responsibility                           |
| --------------- | ---------------------------------------- |
| Nautobot        | Engineering Intent                       |
| Platform API    | Converts intent into deployment requests |
| Workflow Engine | Coordinates execution                    |
| Cisco NetAsCode | Canonical ACI data model                 |
| Terraform       | Infrastructure provisioning              |
| Ansible         | Operational configuration                |
| Validation      | Independent verification                 |

Each component performs one clearly defined responsibility.

---

# Platform Workflow

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
Cisco NetAsCode YAML
     │
     ▼
Terraform
     │
     ▼
Cisco APIC
     │
     ▼
Validation
```

Terraform transforms declarative models into deployed infrastructure.

---

# Responsibilities of Terraform

Terraform is responsible for:

* Infrastructure provisioning
* Infrastructure lifecycle
* Resource dependencies
* Resource creation
* Resource modification
* Resource deletion
* State reconciliation

Terraform is **not** responsible for:

* Operational configuration
* Continuous validation
* Incident response
* Monitoring
* Source of Truth
* Documentation
* AI reasoning

These responsibilities belong elsewhere in the platform.

---

# State Management

Terraform state represents:

> **What Terraform believes has been deployed.**

Terraform state is **not** the Source of Truth.

Terraform state should be:

* Protected
* Versioned where appropriate
* Securely stored
* Backed up
* Locked during execution

Recommended backends include:

* Azure Storage
* Terraform Cloud
* Remote state with locking

---

# Drift

Infrastructure drift may occur through:

* Emergency production changes
* Vendor upgrades
* Manual intervention

The platform addresses drift through:

* Validation
* Observability
* Drift detection
* Controlled reconciliation

Terraform should reconcile approved infrastructure changes.

Operational drift should be analysed before remediation.

---

# Governance

Terraform execution occurs only through the Platform Control Plane.

Engineers should not execute production Terraform manually.

Typical workflow:

Engineering Intent

↓

Approval

↓

Workflow Engine

↓

Terraform Plan

↓

Review

↓

Terraform Apply

↓

Validation

This ensures deterministic, governed deployments.

---

# Consequences

Positive outcomes include:

* Repeatable deployments
* Infrastructure consistency
* Modular architecture
* Improved auditability
* Easier testing
* Multi-domain extensibility

Potential drawbacks include:

* State management complexity
* Provider limitations
* Module maintenance
* Upgrade planning

These are considered acceptable trade-offs.

---

# Future Considerations

Future enhancements may include:

* Automated plan review
* AI-assisted plan explanation
* Policy as Code enforcement
* Digital Twin simulation
* Multi-environment promotion
* Drift analytics

These capabilities strengthen Terraform's role without changing its responsibility.

---

# Summary

Terraform has been selected as the declarative infrastructure provisioning engine for the Network Platform Engineering Platform.

Terraform converts approved engineering intent into deterministic infrastructure deployments while remaining independent of the Source of Truth.

By separating engineering intent from infrastructure provisioning, the platform achieves clearer responsibilities, stronger governance and greater long-term maintainability.
