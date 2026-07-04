# ADR-007 — Cisco NetAsCode as the Canonical Engineering Model

**Status:** Accepted

**Date:** 2026-06-29

**Decision Makers:** Platform Engineering Team

> **Naming clarification:** "NetAsCode" refers to the canonical engineering model (this ADR's subject) — a YAML schema describing tenants/VRFs/bridge domains, produced by `platform/python/generate_aci.py`. It is unrelated to the `netascode/aci` Terraform provider name. The platform's Terraform implementation ([`ADR-002`](ADR-002-Terraform-Desired-State.md)) uses the `CiscoDevNet/aci` provider, chosen during Phase 3 implementation for broader version compatibility with APIC 6.2(1g). The provider is simply the tool that consumes NetAsCode YAML; it does not itself need to be "the NetAsCode provider."

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-002 — Terraform Owns Desired State Provisioning
- ADR-003 — Ansible Owns Day-2 Operations
- ADR-004 — Platform API as the Unified Platform Interface
- ADR-005 — Workflow Orchestration
- ADR-006 — Platform Control Plane as the Single Orchestration Layer

---

# Context

The Network Platform Engineering Platform manages multiple infrastructure domains using a common engineering workflow.

Current target domains include:

- Cisco ACI
- Cisco Nexus VXLAN EVPN
- Microsoft Azure Networking

Each infrastructure technology exposes different APIs, configuration models and operational semantics.

Without a common engineering representation, automation tools become tightly coupled to vendor-specific implementations.

For example:

- Terraform modules become platform-specific.
- Ansible playbooks contain vendor-specific logic.
- Validation pipelines require custom data models.
- AI assistants must understand multiple infrastructure schemas.
- Engineering intent becomes fragmented.

To provide a consistent engineering experience, the platform requires a canonical engineering representation that separates business intent from implementation details.

---

# Problem Statement

How should engineering intent be represented so that it remains independent of execution technologies and vendor-specific implementations?

Should Terraform modules and Ansible playbooks define the engineering model, or should a canonical engineering model exist between intent and execution?

---

# Decision

The platform shall adopt Cisco NetAsCode as the Canonical Engineering Model for supported Cisco infrastructure domains.

Engineering intent captured in Nautobot shall be translated into the NetAsCode model before infrastructure execution.

Terraform, Ansible, validation frameworks and future automation components consume this canonical representation rather than engineering intent directly.

NetAsCode is scoped to **one specific tier** of the platform's two-tier canonical abstraction: it is the domain-specific Canonical Engineering Model (Cisco ACI only), produced *after* Nautobot. It is not, and is not intended to be, the domain-agnostic Canonical Intent produced *before* Nautobot by the Platform API's Intent Translation Layer. See the **Canonical Intent** glossary entry in [`03a-Platform-Glossary.md`](../02-Architecture/03a-Platform-Glossary.md) for the full contrast. When VXLAN EVPN, Azure, or other domains are added, each gets its own Canonical Engineering Model — NetAsCode does not generalize across domains, by design.

---

# Why a Canonical Engineering Model

A canonical engineering model provides a stable abstraction layer between engineering intent and execution.

Instead of coupling automation directly to infrastructure technologies, engineering intent is normalized into a consistent representation.

This separation enables:

- Technology independence
- Consistent automation
- Reusable workflows
- Simplified validation
- AI-assisted engineering
- Easier platform evolution

---

# Architectural Position

The Canonical Engineering Model sits between Engineering Intent and infrastructure execution.

```text
Engineering Intent
(Nautobot)
        │
        ▼
Platform API
        │
        ▼
Platform Control Plane
        │
        ▼
Cisco NetAsCode
(Canonical Engineering Model)
        │
        ├───────────────┐
        ▼               ▼
Terraform         Ansible
        │               │
        └───────┬───────┘
                ▼
Infrastructure
```

All execution engines consume the canonical engineering model.

---

# Responsibilities

The Canonical Engineering Model owns:

- Engineering normalization
- Vendor-supported schemas
- Resource relationships
- Validation before execution
- Object consistency
- Reusable engineering definitions

It does not own:

- Engineering intent
- Workflow orchestration
- Infrastructure provisioning
- Operational automation
- Validation execution
- Monitoring

---

# Translation Pipeline

Engineering intent follows a deterministic translation process.

```text
Business Requirement
        │
        ▼
Nautobot
(Source of Truth)
        │
        ▼
Canonical Engineering Model
(NetAsCode)
        │
        ▼
Terraform / Ansible
        │
        ▼
Infrastructure
```

The engineering model acts as the contract between intent and execution.

---

# Benefits

Using Cisco NetAsCode provides:

- Vendor-supported engineering schemas
- Consistent resource modeling
- Reduced duplicate logic
- Easier code generation
- Simplified validation
- Reusable templates
- Better interoperability
- Cleaner automation

Most importantly, engineering intent remains independent of execution technologies.

---

# Interaction with Terraform

Terraform consumes the canonical engineering model to provision infrastructure.

Terraform does not determine engineering intent.

Terraform does not implement business logic.

Terraform translates approved engineering models into infrastructure resources.

---

# Interaction with Ansible

Ansible consumes the canonical engineering model when operational workflows require knowledge of intended infrastructure.

Operational playbooks remain independent of Nautobot data structures.

The canonical model provides the common engineering language.

---

# Interaction with Validation

Validation frameworks compare operational state with the canonical engineering model.

This enables:

- Configuration validation
- Policy validation
- Connectivity validation
- Compliance verification
- Drift detection

Validation becomes independent of the execution engine.

---

# Interaction with AI

AI assistants reason about engineering intent using the canonical engineering model.

Rather than learning multiple vendor-specific APIs, AI systems operate against a consistent engineering representation.

Typical AI activities include:

- Architecture reviews
- Design recommendations
- Configuration generation
- Validation analysis
- Drift analysis
- Documentation generation

The canonical model simplifies AI reasoning while reducing implementation-specific complexity.

---

# Technology Independence

Cisco NetAsCode is the current implementation of the Canonical Engineering Model for Cisco infrastructure.

Future infrastructure domains may require additional canonical models.

Examples include:

- Azure Verified Modules
- Kubernetes Custom Resource Definitions
- VMware object models
- Cloud provider reference architectures

The architectural principle remains unchanged:

Engineering intent must be translated into a canonical engineering representation before execution.

---

# Benefits to the Platform

The Canonical Engineering Model enables:

- Loose coupling
- Vendor abstraction
- Reusable automation
- Independent validation
- AI-assisted engineering
- Consistent workflows
- Easier onboarding
- Reduced maintenance effort

---

# Trade-Offs

Introducing a canonical engineering model requires:

- Translation logic
- Schema lifecycle management
- Version compatibility
- Additional testing

These responsibilities are acceptable because they significantly improve maintainability and architectural consistency.

---

# Alignment with Platform Principles

This decision supports:

- Intent Before Configuration
- Single Source of Truth
- Platform Before Tools
- Separation of Responsibilities
- Technology Independence
- API-First Architecture
- Modularity
- Closed-Loop Engineering
- AI as an Engineering Assistant

---

# Future Considerations

Future enhancements may include:

- Support for additional infrastructure domains
- Automatic model generation
- Schema validation pipelines
- Versioned engineering models
- AI-assisted model creation
- Model visualization
- Cross-domain engineering relationships

These enhancements extend the Canonical Engineering Model while preserving its architectural role.

---

# Summary

The Network Platform Engineering Platform adopts Cisco NetAsCode as the Canonical Engineering Model for Cisco infrastructure domains.

Engineering intent captured in Nautobot is translated into this common engineering representation before infrastructure execution.

Terraform, Ansible, validation frameworks and AI assistants interact with the canonical model rather than vendor-specific implementations.

This architectural decision decouples engineering intent from execution technologies, improves maintainability, simplifies automation and establishes a stable engineering foundation that can evolve as the platform grows.