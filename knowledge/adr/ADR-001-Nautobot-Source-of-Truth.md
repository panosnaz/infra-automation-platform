---
type: adr
domain: platform
status: active
tags: [nautobot, source-of-truth]
owner: platform-engineering-team
last_updated: 2026-07-28
---

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

Nautobot shall be the **authoritative Source of Truth (SoT)** for the Network Platform Engineering Platform's **network inventory and topology** — tenants, VRFs, prefixes, interfaces, devices, bridge domains, and other objects that fit Nautobot's native DCIM/IPAM data model.

All network-domain engineering intent originates from Nautobot. Terraform, Ansible, validation frameworks and AI agents consume data from Nautobot but do not own the desired network state.

> **Scope clarification (2026-07-28, see [ADR-019](ADR-019-Three-Truths-Principle.md)):** this ADR governs which system owns *network inventory and topology*. It does not claim Nautobot is the sole authority for *business intent* (why a change was requested, what outcome it serves) or *non-network-shaped state* (security policies, cloud WAF rules, NAC posture policies). Those concerns are addressed separately by ADR-019's "Three Truths" principle. Nothing in this ADR prevents a future intent layer from sitting above Nautobot — it only requires that Nautobot remain the authoritative source for the network objects downstream automation consumes.

---

# Architectural Principle

The platform follows the principle:

> **Engineering Intent lives in Nautobot.**

Execution is delegated to the Platform Control Plane.

Infrastructure reflects the desired state.

Validation confirms operational correctness.

## Mandatory Sequence

The following sequence is mandatory and must never be violated.

```text
Business Request (any entry point)
        │
        ▼
Platform API (Intent Translation)
        │
        ▼
Canonical Intent
        │
        ▼
Nautobot (Source of Truth)  ◄── engineering intent is written here
        │
        ▼
NetAsCode Generator
        │
        ▼
Canonical Model (YAML)
        │
        ▼
Terraform / Ansible
        │
        ▼
Infrastructure
```

The reverse path — Terraform modifying or reading back into Nautobot as a source of truth — is explicitly prohibited.

Terraform provisions infrastructure.

Nautobot owns intent.

These responsibilities must never merge.

---

# Amendment (2026-07-04) — Brownfield Onboarding Exception

**Context:** the lab's Nautobot instance is populated via the `nautobot-ssot` ACI sync job, which reads *from* the live APIC *into* Nautobot — the reverse of the Mandatory Sequence above. As of 2026-07-04, 3 of the 4 tenants in the lab (`common`, `infra`, `mgmt`) arrived this way; only one (`web-tenant`) was authored forward through the intended pipeline. This amendment resolves the apparent contradiction between that reality and the Mandatory Sequence.

## Brownfield

Existing infrastructure may be discovered and imported into Nautobot using discovery or SSoT synchronization tooling (e.g. `nautobot-ssot` ACI, discovery jobs, import scripts).

The purpose of this path is exclusively to:

- Bootstrap inventory
- Populate relationships
- Establish an initial Source of Truth for infrastructure that predates the platform

This process is **exceptional and administrative** — it is an onboarding activity, not an ongoing operating model. It is how infrastructure *enters* platform management, not how it stays synchronized once it is under management.

## Transition to Managed State

Once brownfield objects have been imported, they become managed by the platform. From that point forward, the Mandatory Sequence — Platform API → Canonical Intent → Nautobot → NetAsCode → Terraform → Infrastructure — is the only authoritative direction for those objects.

There is no ambiguity about *when* this transition happens: an object is platform-managed from the moment it is first referenced by a forward-authored Canonical Intent (in the current lab, this is why `web-tenant` is platform-managed and the SSoT-imported system tenants are not).

## Managed State

Once an object is declared platform-managed:

- Reverse synchronization must never overwrite intent for that object.
- Infrastructure must not become authoritative for that object.
- Drift on that object is *reported*, never silently *imported* back into Nautobot.
- Drift is resolved exclusively through forward intent (a new Canonical Intent correcting the divergence), never by re-running SSoT sync over it.

Reverse synchronization may continue to run for visibility into *unmanaged* objects (infrastructure the platform doesn't yet own), but it must not modify any object already under platform management.

This preserves Nautobot as the authoritative Source of Truth for everything the platform manages, while still providing a practical, honest path for onboarding infrastructure that already exists — which every real deployment of this platform will need on day one.

> **Terminology note (2026-07-05):** "platform-managed" here is a **provenance** fact — permanent, set once, answering "was this object's desired state ever authored via forward intent?" Do not confuse this with `ExecutionState.lifecycle_state = stable` ([Platform Specification 03](../11-Specifications/03-Platform-Execution-Model-Specification.md)), an **execution-convergence** fact that is reversible (`stable` ⇄ `drifted`) and answers a completely different question: "does the live infrastructure currently match what was last validated?" An object can be platform-managed and `drifted` at the same time.

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

> **Extensibility boundary (2026-07-28):** domains whose objects fit Nautobot's DCIM/IPAM model (network inventory, topology, IPAM — e.g. ACI, EVPN) should use Nautobot as their SoT. Domains whose objects do not fit that model (firewall security policies, cloud WAF rules, NAC posture policies) may require their own domain-specific SoT, with the platform's orchestration layer coordinating across SoTs. This ADR does not mandate that *every* future domain must store its state in Nautobot — only that Nautobot is the SoT for network-shaped objects. See [ADR-019](ADR-019-Three-Truths-Principle.md) for the full multi-domain SoT design principle.

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
| Nautobot        | Network inventory and topology SoT |
| NetAsCode YAML  | Git-committed desired-state artifact (generated from Nautobot) |
| Platform API    | Platform abstraction (legacy v1; replaced by MCP Server in v2) |
| MCP Server (future) | Business-operation entry point; thin, never orchestrates |
| Intent Layer (future) | Business intent — *why* a change was requested (see ADR-019) |
| Workflow Engine | Orchestration (GitLab CI in Platform v2) |
| Terraform       | Infrastructure provisioning     |
| Ansible         | Day-2 operational configuration |
| Validation      | Independent verification        |
| Observability   | Operational visibility          |
| AI Agents       | Engineering assistance and reasoning |

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
