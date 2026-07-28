---
type: standard
domain: platform
status: active
tags: [principles]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 03 – Platform Principles

**Project:** Network Platform Engineering Platform

**Document Type:** Architecture Principles

**Version:** 2.0

**Status:** Draft

**Owner:** Platform Engineering Team

---

# Purpose

This document defines the architectural principles that govern the design, implementation, operation and future evolution of the Network Platform Engineering Platform.

These principles are intentionally technology-agnostic and represent the enduring philosophy of the platform rather than implementation choices.

Technologies will evolve.

Products will change.

Automation frameworks will mature.

Artificial Intelligence capabilities will expand.

The architectural principles defined in this document should remain stable and guide every future architectural decision.

Every new capability, integration, workflow, automation or technology introduced into the platform should be evaluated against these principles.

---

# Platform Philosophy

The platform is founded on one simple idea:

> **Engineers define intent.**
>
> **The platform determines implementation.**

Infrastructure should never become the primary engineering interface.

Instead, engineers describe the desired business outcome, while the platform translates that intent into deterministic, validated and observable infrastructure changes.

This separation enables:

* Reduced operational complexity
* Technology independence
* Consistent engineering workflows
* Long-term maintainability
* Multi-domain scalability

The platform is therefore treated as an engineering product rather than a collection of automation scripts.

---

# Platform Vision

The long-term objective is to build a reusable Platform Engineering capability capable of managing multiple infrastructure domains through a common operating model.

The initial implementation targets:

* Cisco ACI
* Cisco Nexus VXLAN EVPN
* Azure Networking

Future domains should integrate into the platform by reusing existing capabilities rather than introducing domain-specific automation stacks.

---

# Architectural Philosophy

The platform is designed around five fundamental concepts.

```text
Engineering Intent
        │
        ▼
Canonical Engineering Model
        │
        ▼
Platform Execution
        │
        ▼
Continuous Validation
        │
        ▼
Observability
        │
        ▼
Continuous Improvement
```

Every platform capability exists to strengthen one or more stages of this engineering lifecycle.

---

# Foundational Principles

These principles define the immutable architectural foundations of the platform.

---

# Principle 1 — Single Source of Truth

There shall be exactly one authoritative Source of Truth for engineering intent.

The Source of Truth defines:

* Desired business intent
* Inventory
* Relationships
* Ownership
* Service definitions
* Network intent
* Infrastructure metadata

The Source of Truth does **not** represent the deployed infrastructure.

It represents the infrastructure that **should exist**.

For this platform, Nautobot fulfils this responsibility.

## Rationale

Multiple Sources of Truth inevitably result in:

* Configuration drift
* Duplicate inventories
* Inconsistent automation
* Operational confusion
* Difficult troubleshooting

Every platform capability should consume data from the Source of Truth rather than maintaining its own independent inventory.

---

# Principle 2 — Intent Before Configuration

The platform manages engineering intent rather than device configuration.

Engineers should express **what** they require.

The platform determines **how** the infrastructure is implemented.

For example:

Instead of requesting:

> Create Tenant X, VRF Y, Bridge Domain Z and Contract A.

The engineer expresses:

> Deploy a new Finance application environment.

The platform translates this intent into the required infrastructure objects.

## Rationale

Intent-based engineering:

* Reduces complexity
* Simplifies user interaction
* Enables abstraction
* Improves portability
* Decouples business requirements from implementation details

---

# Principle 3 — Canonical Engineering Data Model

The platform shall maintain a single canonical engineering model between intent and execution.

This model represents the platform's implementation language.

For Cisco ACI, the canonical model is Cisco NetAsCode.

## Canonical Intent

Before engineering intent reaches the Source of Truth, it passes through the Intent Translation Layer.

Diverse input formats — natural language, Jira tickets, REST payloads, Git commits, portal forms — are normalised into a **Canonical Intent Model**.

The Canonical Intent Model is the internal language of the platform.

It is technology-neutral, fully validated and policy-compliant before it reaches Nautobot.

The engineering pipeline therefore becomes:

```text
Business Intent (any format)
        │
        ▼
Intent Translation
(Platform API)
        │
        ▼
Canonical Intent
(validated • normalised • policy-checked)
        │
        ▼
Engineering Intent
(Nautobot)
        │
        ▼
Canonical Model
(Cisco NetAsCode)
        │
        ▼
Execution
(Terraform / Ansible)
```

Neither Terraform nor Ansible should define independent engineering models.

Both automation engines consume the same canonical model.

## Rationale

A shared engineering model provides:

* Consistency
* Reduced duplication
* Easier maintenance
* Simplified testing
* Vendor abstraction

---

# Principle 4 — Separation of Responsibilities

Every platform capability shall have exactly one clearly defined responsibility.

Responsibilities must never overlap.

Examples include:

| Capability      | Responsibility              |
| --------------- | --------------------------- |
| Nautobot        | Engineering Intent          |
| Platform API    | Platform abstraction        |
| Workflow Engine | Orchestration               |
| Cisco NetAsCode | Canonical engineering model |
| Terraform       | Infrastructure provisioning |
| Ansible         | Day-2 operations            |
| Validation      | Independent verification    |
| Observability   | Operational visibility      |
| AI Agents       | Engineering reasoning       |

Each component should perform one responsibility exceptionally well rather than many responsibilities poorly.

## Rationale

Clear ownership simplifies:

* Maintenance
* Testing
* Documentation
* Platform evolution
* Team responsibilities
* AI reasoning

---

# Principle 5 — Platform Control Plane

All infrastructure execution shall be coordinated through a common Platform Control Plane.

Individual platform components should never communicate directly unless explicitly required.

Instead, execution flows through a governed orchestration layer.

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
Workflow Engine
     │
     ├──────────────┐
     ▼              ▼
Terraform      Ansible
     │              │
     └──────┬───────┘
            ▼
 Infrastructure
```

The Platform Control Plane provides:

* Governance
* Orchestration
* Security
* Auditability
* Standardised execution
* Extensibility

## Rationale

Without a Control Plane, platform components become tightly coupled.

As the number of integrations increases, complexity grows exponentially.

The Platform Control Plane ensures every infrastructure change follows a consistent, observable and governed execution path.

---

# Summary of Foundational Principles

The first five principles establish the architectural foundations upon which every other capability is built.

They define:

* Where engineering intent lives
* How engineering intent is represented
* How responsibilities are divided
* How execution is coordinated
* How the platform remains maintainable over time

All subsequent engineering, operational and AI capabilities inherit these foundational principles.

# Engineering Principles

The following principles define how engineering activities are performed throughout the platform lifecycle.

These principles apply equally to infrastructure deployment, operational changes, validation, documentation and future platform capabilities.

---

# Principle 6 — The Five-Stage Engineering Pipeline

Every infrastructure change shall follow the same engineering pipeline.

The platform deliberately separates engineering activities into distinct stages.

```text
Business Requirement
        │
        ▼
Engineering Intent
(Nautobot)
        │
        ▼
Canonical Engineering Model
(Cisco NetAsCode)
        │
        ▼
Platform Execution
(Terraform / Ansible)
        │
        ▼
Continuous Validation
(pyATS / Catfish)
        │
        ▼
Observability
(Prometheus / Grafana / Loki)
        │
        ▼
Engineering Feedback
```

Each stage performs one responsibility.

No stage should bypass another.

The engineering pipeline forms the backbone of the platform architecture.

## Rationale

Separating engineering activities into independent stages provides:

* Deterministic execution
* Independent validation
* Easier troubleshooting
* Better observability
* Clear ownership
* AI-friendly workflows
* Simplified future expansion

---

# Principle 7 — Validation Before Trust

Infrastructure deployment does not imply infrastructure correctness.

Every infrastructure change shall be validated independently before being considered successful.

Validation should confirm:

* Infrastructure correctness
* Operational correctness
* Policy compliance
* Business intent
* Service availability
* Connectivity
* Security posture

Validation should remain independent from deployment.

Deployment tools should never validate their own work.

## Validation Types

Examples include:

* Configuration validation
* Network connectivity testing
* API validation
* Intent validation
* Compliance validation
* Performance validation
* Security validation

## Rationale

Independent validation increases engineering confidence and reduces operational risk.

---

# Principle 8 — Closed-Loop Engineering

The platform shall continuously compare engineering intent with operational reality.

Every deployment produces feedback.

Every validation produces feedback.

Every operational event produces feedback.

Knowledge and Observability continuously improve future intent.

This feedback continuously improves the engineering lifecycle.

```text
Intent
   │
   ▼
Model (Canonical Intent → Nautobot → NetAsCode)
   │
   ▼
Provision (Terraform / Ansible)  ──► Event Published
   │
   ▼
Operate (Infrastructure)
   │
   ▼
Validate  ────────────────────► Event Published
   │
   ▼
Observe (Continuous Telemetry)  ───► Knowledge Layer
   │
   ▼
Learn (Knowledge • AI Analysis)
   │
   ▼
Improve
   │
   └───────────────────► Updated Intent
```

Intent → Model → Provision → Operate → Validate → Observe → Learn → Improve → Repeat.

The platform continuously evolves based on observed operational behaviour.

## Rationale

Infrastructure changes over time.

Closed-loop engineering ensures the platform detects divergence before it impacts production services.

---

# Principle 9 — Event-Driven Automation

Automation should react to engineering events whenever practical.

The platform should avoid relying solely on scheduled execution.

The Event Bus is the asynchronous backbone of the platform.

It decouples producers from consumers, enabling loosely coupled, independently scalable automation.

Examples of platform events include:

* IntentReceived
* DeploymentRequested
* DeploymentPlanned
* DeploymentStarted
* DeploymentCompleted
* DeploymentFailed
* ValidationPassed
* ValidationFailed
* DriftDetected
* SecretRotated
* KnowledgeUpdated
* AIRecommendationPublished

Each event should trigger an appropriate workflow through the Platform Control Plane.

Event publishers do not know or care who is listening.

Event subscribers declare their interest and react independently.

## Rationale

Event-driven automation provides:

* Faster response
* Reduced manual intervention
* Improved scalability
* Better orchestration
* More intelligent workflows

---

# Principle 10 — Engineering Assets as Code

Every engineering artefact should be managed as code wherever practical.

Engineering assets include:

* Infrastructure
* Configuration
* Policies
* Validation tests
* Documentation
* ADRs
* Runbooks
* Workflow definitions
* API specifications
* Prompt libraries
* AI knowledge
* Standards

Every engineering asset should be:

* Version controlled
* Peer reviewed
* Auditable
* Reproducible
* Recoverable

## Rationale

Engineering knowledge should evolve with the same discipline as software.

---

# Platform Principles

These principles define how the platform itself should evolve.

---

# Principle 11 — API First

Every platform capability shall expose a well-defined API.

Platform components communicate through documented interfaces.

Direct database access between components is prohibited.

Examples include:

* REST APIs
* GraphQL
* Webhooks
* Message queues
* Event streams

APIs should remain stable and versioned.

## Rationale

API-first architecture enables:

* Loose coupling
* Independent evolution
* Easier testing
* Better integrations
* AI interoperability

---

# Principle 12 — Platform Before Tools

The platform is the product.

Individual technologies are implementation details.

Engineers interact with platform capabilities rather than individual tools.

Examples:

Engineers request:

> Deploy a new tenant.

The platform determines whether Terraform, Ansible or another automation engine performs the work.

Technology choices should never leak into user workflows.

## Rationale

Technologies change.

Platform capabilities remain.

---

# Principle 13 — Technology Independence

The architecture shall remain independent of specific implementation technologies.

Future replacement of any individual technology should require minimal architectural change.

Examples:

Terraform could eventually be replaced.

Ansible could evolve.

Workflow engines may change.

Monitoring platforms may change.

The overall platform architecture should remain stable.

## Rationale

Technology independence protects long-term maintainability.

---

# Principle 14 — Modular Platform Architecture

Every platform capability should be independently deployable, maintainable and testable.

Modules should have:

* Clear responsibilities
* Minimal dependencies
* Stable interfaces
* Independent lifecycle

Examples include:

* Platform API
* Workflow Engine
* Validation Framework
* Observability
* Knowledge Layer
* AI Services

## Rationale

Modularity simplifies:

* Development
* Testing
* Upgrades
* Troubleshooting
* Future expansion

---

# Principle 15 — Scalability by Design

The platform shall scale without architectural redesign.

Scalability includes:

### Infrastructure

Additional network domains

### Engineers

Additional engineering teams

### Automation

Additional workflows

### AI

Additional AI agents

### Knowledge

Larger documentation repositories

### Geographic Expansion

Additional regions

### Cloud Providers

Additional infrastructure domains

Scalability should be achieved by extending existing platform capabilities rather than introducing new platform architectures.

## Rationale

A Platform Engineering solution should grow through extension, not replacement.

---

# Summary of Engineering and Platform Principles

The Engineering Principles define **how engineering work is performed**.

The Platform Principles define **how the platform itself evolves**.

Together they ensure that:

* Engineering remains deterministic.
* Automation remains reusable.
* Validation remains independent.
* Platform capabilities remain modular.
* Future technologies integrate without architectural redesign.

These principles transform the platform from a collection of automation tools into a long-lived engineering product.

# Many Entry Points, One Execution Path

One of the most important Platform Engineering principles is that the execution path is always identical, regardless of where the request originates.

The platform accepts requests from:

* A self-service portal
* A CLI command
* A Jira ticket transition
* A Git commit or Pull Request
* An AI engineering assistant
* A REST API call
* A ServiceNow request
* A CI/CD pipeline trigger

Regardless of origin, every request follows the same path:

```text
Entry Point (any)
     │
     ▼
Platform API
(Authentication • Authorisation • Intent Translation)
(Validation • Normalisation • Policy Enforcement)
(Canonical Intent Generation • Event Publishing)
     │
     ▼
Nautobot (Source of Truth)
     │
     ▼
Workflow Engine (Orchestration)
     │
     ▼
Execution (Terraform / Ansible)
     │
     ▼
Validation
     │
     ▼
Knowledge & Observability
```

No consumer receives special treatment.

No consumer bypasses the Platform API.

This guarantees governance, auditability and operational consistency regardless of how a request originates.

# Operational Principles

The following principles define how the platform is operated, secured, governed and continuously improved throughout its lifecycle.

These principles ensure that automation remains safe, observable, maintainable and aligned with organisational governance.

---

# Principle 16 — Security by Design

Security shall be embedded into every architectural layer of the platform.

Security is a platform capability rather than an afterthought.

Every platform component should follow the principle of least privilege.

Examples include:

* Identity-based authentication
* Role-Based Access Control (RBAC)
* Centralised secret management
* Audit logging
* API authentication
* Encryption in transit
* Encryption at rest
* Policy enforcement

Secrets must never be stored inside:

* Source code
* Terraform modules
* Ansible playbooks
* Documentation
* Git repositories

Secrets should be retrieved dynamically from an approved secret management platform.

## Rationale

Security should be designed into the platform rather than added after implementation.

---

# Principle 17 — Human Governance

Automation assists engineering.

Automation does not replace engineering judgement.

High-impact infrastructure changes should remain subject to appropriate governance.

Typical governance activities include:

* Architecture review
* Peer review
* Change approval
* CAB processes where required
* Validation
* Post-implementation review

Engineers remain accountable for infrastructure decisions.

The platform should reduce repetitive work rather than remove engineering responsibility.

## Rationale

Infrastructure automation should increase engineering quality without reducing operational control.

---

# Principle 18 — Observability Everywhere

Every platform capability should produce operational telemetry.

Observability extends beyond infrastructure monitoring.

The platform should provide visibility into:

* Infrastructure
* Automation
* APIs
* Workflows
* Validation
* AI interactions
* Platform services

Examples include:

* Metrics
* Logs
* Traces
* Events
* Audit records
* Workflow history
* Deployment history

Observability should support both operational troubleshooting and continuous improvement.

## Rationale

Infrastructure cannot be effectively operated if it cannot be observed.

---

# Principle 19 — Knowledge as a Platform Asset

Engineering knowledge is a first-class platform capability.

Knowledge should evolve alongside the platform.

Examples include:

* Architecture documentation
* Standards
* ADRs
* Runbooks
* Troubleshooting guides
* Lessons learned
* Platform patterns
* Prompt libraries
* AI context
* Design decisions

Knowledge should be:

* Version controlled
* Searchable
* Reviewable
* Reusable
* Continuously maintained

Knowledge should never depend upon individual engineers.

Institutional knowledge belongs to the platform.

## Rationale

Engineering organisations become stronger when knowledge becomes a shared platform asset.

---

# Principle 20 — AI Assists, Platform Executes

Artificial Intelligence is an engineering capability.

Artificial Intelligence is **not** an infrastructure execution engine.

AI is a platform client.

Like a portal, a CLI or a Jira ticket, AI interacts with the platform exclusively through the Platform API.

AI may propose, generate and recommend.

The Platform API translates AI intent into a Canonical Intent Model.

The Platform Control Plane executes.

AI should support engineers by providing:

* Architectural recommendations
* Design reviews
* Validation analysis
* Documentation generation
* Root cause analysis
* Operational guidance
* Knowledge retrieval
* Workflow recommendations

Infrastructure execution remains the responsibility of the Platform Control Plane.

```text
AI Engineering Assistant
     │
     ▼
Platform API
(same entry point as Portal • CLI • Jira • Git)
     │
     ▼
Canonical Intent
     │
     ▼
Workflow Engine
     │
     ▼
Terraform / Ansible
     │
     ▼
Infrastructure
```

AI must never bypass:

* Governance
* Validation
* Security
* Approval workflows
* Platform APIs

## Rationale

Separating reasoning from execution creates a platform that is both innovative and operationally trustworthy.

---

# Architecture Decision Checklist

Before introducing a new technology, workflow or capability, evaluate it against the following questions.

## Source of Truth

□ Does it preserve a single Source of Truth?

---

## Engineering Intent

□ Does it reinforce intent-based engineering?

---

## Canonical Model

□ Does it reuse the Canonical Engineering Model?

---

## Platform Control Plane

□ Does it integrate through the Platform Control Plane?

---

## Responsibilities

□ Does it avoid duplicating existing responsibilities?

---

## APIs

□ Is it API-first?

---

## Modularity

□ Can it operate independently?

---

## Validation

□ Can it be validated independently?

---

## Observability

□ Is it observable?

---

## Security

□ Does it follow Security by Design?

---

## Governance

□ Does it preserve Human Governance?

---

## Knowledge

□ Can it be documented and reused?

---

## AI

□ Can AI reason about it without directly controlling it?

---

## Scalability

□ Will it scale with the rest of the platform?

---

## Platform Vision

□ Does it strengthen the Platform Engineering model rather than introducing a separate automation solution?

If the answer to any of these questions is **No**, the proposal should be reviewed before implementation.

---

# Relationship to Other Architecture Documents

This document defines the architectural principles that govern the platform.

The principles described here are realised through the supporting architecture documentation.

| Document                           | Relationship                                                     |
| ---------------------------------- | ---------------------------------------------------------------- |
| 00 – Project Charter               | Defines the business objectives                                  |
| 01 – Current State                 | Describes the existing environment                               |
| 02 – Target Architecture           | Defines the target architecture                                  |
| 04 – Technology Stack              | Maps principles to technologies                                  |
| 05 – Repository Structure          | Organises implementation artefacts                               |
| 06 – Deployment Workflow           | Applies the engineering principles                               |
| 07 – Day-2 Operations              | Defines operational workflows                                    |
| 08 – Validation Strategy           | Implements Validation First                                      |
| 09 – AI Agent Architecture         | Implements AI Assists, Platform Executes                         |
| 10 – Security Architecture         | Implements Security by Design                                    |
| 11 – Observability                 | Implements Observability Everywhere                              |
| 12 – Roadmap                       | Describes future platform evolution                              |
| 13 – Platform Lifecycle Management | Governs long-term platform evolution                             |
| ADRs                               | Record architectural decisions that comply with these principles |

---

# Summary

The principles defined in this document form the constitutional foundation of the Network Platform Engineering Platform.

They intentionally separate:

* Engineering intent from implementation.
* Reasoning from execution.
* Provisioning from operations.
* Deployment from validation.
* Platform capabilities from implementation technologies.

Together, these principles establish a reusable Platform Engineering model that is:

* Intent-driven
* Deterministic
* Observable
* Secure
* Modular
* Extensible
* AI-augmented
* Governed

Every future architectural decision, automation workflow, AI capability and technology selection should reinforce these principles.

The objective is not simply to automate infrastructure.

The objective is to build a long-lived engineering platform capable of evolving with future technologies while preserving a consistent operating model and engineering experience.

---

# Platform Constitution

The philosophy of the platform can be summarised in five statements:

> **Engineers define intent.**

> **The platform determines implementation.**

> **Validation proves correctness.**

> **Observability reveals reality.**

> **AI augments engineering.**

Together, these principles establish a governed, closed-loop Platform Engineering ecosystem for modern network infrastructure.
