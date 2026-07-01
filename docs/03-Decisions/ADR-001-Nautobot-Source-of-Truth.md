# ADR-001 – Nautobot as the Authoritative Source of Truth

**Status:** Accepted

**Date:** 2026-06-28

**Decision Makers:** Platform Engineering Team

---

# Context

The Network Platform Engineering Platform requires a single authoritative location that represents the desired state (engineering intent) of the managed infrastructure.

Historically, infrastructure information was distributed across multiple locations including:

* Excel spreadsheets
* CSV files
* Terraform variables
* Ansible inventories
* APIC configuration
* Azure Portal
* Engineering documentation

This resulted in several operational challenges:

* Duplicate information
* Configuration drift
* Manual synchronization
* Inconsistent inventories
* Difficult automation
* Limited traceability
* Poor change visibility

The platform requires a single source that represents the desired operational state independently from the automation tools used to implement that state.

---

# Decision

Nautobot shall be the **authoritative Source of Truth (SoT)** for the Network Platform Engineering Platform.

All engineering intent originates from Nautobot.

Terraform, Ansible, validation frameworks and AI agents consume data from Nautobot but do not own the desired state.

---

# Architectural Principle

The platform follows the principle:

> **Engineering Intent lives in Nautobot.**

Execution is delegated to the Platform Control Plane.

Infrastructure reflects the desired state.

Validation confirms operational correctness.

---

# Decision Drivers

The following requirements influenced this decision.

## Single Source of Truth

Engineering data should exist only once.

Duplicate inventories should be avoided.

---

## Vendor Independence

The Source of Truth should not depend on a specific automation tool.

Terraform may change.

Ansible may change.

Cisco APIs may evolve.

Engineering intent should remain independent.

---

## Automation Integration

The platform requires native integration with:

* Terraform
* Ansible
* Python
* REST APIs
* Webhooks
* Validation frameworks

Nautobot provides APIs suitable for these integrations.

---

## Extensibility

The platform is expected to expand beyond Cisco ACI.

Future domains include:

* Cisco Nexus VXLAN EVPN
* Azure Networking
* SD-WAN
* Firewalls
* Kubernetes Networking

The Source of Truth should support multiple infrastructure domains.

---

## Platform Engineering

The platform aims to implement Platform Engineering principles rather than isolated automation scripts.

Nautobot provides a central engineering data model suitable for long-term platform evolution.

---

# Alternatives Considered

## Option 1 — Excel / CSV Files

Advantages

* Simple
* Familiar
* Easy to edit

Disadvantages

* No validation
* No API
* Poor scalability
* Difficult collaboration
* Version control challenges
* No event-driven automation

Decision

Rejected.

Suitable only for small environments.

---

## Option 2 — Terraform Variables

Advantages

* Native to Infrastructure as Code
* Version controlled

Disadvantages

* Represents deployment data rather than engineering intent
* Difficult for operations teams to consume
* Vendor-specific
* Limited support for operational workflows
* Not designed as an enterprise inventory

Decision

Rejected as the primary Source of Truth.

Terraform remains the provisioning engine.

---

## Option 3 — APIC as Source of Truth

Advantages

* Reflects running configuration
* Always current

Disadvantages

* Represents operational state rather than desired intent
* Manual changes become authoritative
* Difficult to distinguish intended configuration from configuration drift
* Vendor specific

Decision

Rejected.

APIC is the managed system, not the engineering authority.

---

## Option 4 — Git Repository

Advantages

* Version control
* Review process
* Traceability

Disadvantages

* Stores code rather than operational inventory
* Limited query capabilities
* No object relationships
* No native inventory model

Decision

Git remains the authoritative source for code, not infrastructure intent.

---

## Option 5 — Nautobot

Advantages

* Purpose-built Source of Truth
* Rich data model
* Extensible
* REST API
* Webhooks
* Plugins
* GraphQL support
* Multi-vendor
* Automation ecosystem
* Relationship modelling

Disadvantages

* Additional platform component
* Operational overhead
* Learning curve

Decision

Accepted.

---

# Consequences

Positive consequences include:

* Centralised engineering intent
* Reduced configuration drift
* Improved automation consistency
* Simplified integrations
* Better inventory management
* Improved auditability
* Event-driven automation
* AI-friendly architecture
* Easier domain expansion

Potential drawbacks include:

* Additional infrastructure to maintain
* Need for data governance
* Requirement to maintain inventory accuracy

These drawbacks are considered acceptable given the long-term architectural benefits.

---

# Platform Workflow

```text
Engineer
     │
     ▼
Nautobot
(Source of Truth)
     │
     ▼
Platform API
     │
     ▼
Workflow Engine
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

Nautobot owns engineering intent.

Infrastructure never becomes the Source of Truth.

---

# Governance

Changes to infrastructure should originate from Nautobot whenever practical.

Emergency production changes may occasionally be performed directly on managed infrastructure.

When this occurs:

1. The operational issue is resolved.

2. The manual change is documented.

3. Nautobot is updated to reflect the approved desired state.

This restores alignment between engineering intent and operational reality.

---

# Relationship to Other Components

| Component       | Responsibility                  |
| --------------- | ------------------------------- |
| Nautobot        | Engineering Intent              |
| Platform API    | Platform abstraction            |
| Workflow Engine | Orchestration                   |
| Terraform       | Infrastructure provisioning     |
| Ansible         | Day-2 operational configuration |
| Validation      | Independent verification        |
| Observability   | Operational visibility          |
| AI Agents       | Engineering assistance          |

Each component has a single well-defined responsibility.

---

# Future Considerations

Future enhancements may include:

* Automated synchronization from approved change requests
* Service catalog integration
* CMDB integration
* Business application modelling
* Dependency mapping
* Digital Twin integration

These enhancements should reinforce Nautobot's role as the authoritative Source of Truth.

---

# Summary

The Platform Engineering Team has decided that Nautobot will serve as the authoritative Source of Truth for the Network Platform Engineering Platform.

Engineering intent is created and maintained in Nautobot.

The Platform Control Plane consumes this intent to execute deterministic infrastructure automation.

Operational state is validated independently and continuously observed, ensuring that the deployed infrastructure remains aligned with the intended design.

This decision establishes the architectural foundation for all subsequent automation, validation, observability and AI-assisted engineering capabilities.
