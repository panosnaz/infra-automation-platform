# 03b – Reference Architecture

**Project:** Network Platform Engineering Platform

**Document Type:** Reference Architecture

**Version:** 1.0

**Status:** Draft

**Owner:** Platform Engineering Team

> **Implementation Status:** This document describes the reference (target) architecture. For what is actually built and running today, see [`../01-Vision/01-Current-State.md`](../01-Vision/01-Current-State.md). As of 2026-07-04, the Entry Points/Platform API Intent Translation/Event Bus/Workflow Engine/Knowledge & AI layers below are **not implemented**. Nautobot, the NetAsCode generator, Terraform, Ansible, and pyATS are implemented and proven; they currently run independently of the Platform Control Plane shown here.

---

# Purpose

This document describes the reference architecture of the Network Platform Engineering Platform.

Unlike the Target Architecture document, which describes the future vision, this document explains **how the platform is logically organised** and how its components collaborate to transform engineering intent into validated, observable infrastructure.

It serves as the primary architectural reference for:

* Platform Engineers
* Network Engineers
* Cloud Engineers
* Automation Engineers
* Operations Teams
* AI Agents
* Future Contributors

---

# Scope

This reference architecture applies to all supported infrastructure domains.

Initially:

* Cisco ACI
* Cisco Nexus VXLAN EVPN
* Microsoft Azure Networking

Future domains should integrate by reusing the same architectural layers rather than creating new automation stacks.

---

# Architectural Vision

The platform is designed around a simple engineering philosophy:

> Engineers define intent.
>
> The platform determines implementation.

Rather than interacting directly with infrastructure technologies, engineers interact with a common engineering platform.

The platform provides:

* A single Source of Truth
* A common engineering model
* Standardised automation
* Independent validation
* Continuous observability
* AI-assisted engineering

---

# High-Level Reference Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                  ENTRY POINTS                                       │
│                                                                     │
│  Portal • CLI • Jira • ServiceNow • Git • AI Agents • REST API   │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     PLATFORM API                                     │
│                 INTENT TRANSLATION LAYER                             │
│                                                                     │
│ Auth • Authz • Request Validation • Intent Normalisation             │
│ Policy Enforcement • Canonical Intent Generation • Event Publishing   │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│               EVENT BUS  (asynchronous backbone)                    │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  ENGINEERING INTENT LAYER                            │
│                                                                     │
│                     Nautobot (Source of Truth)                       │
│                                                                     │
│ Inventory • Services • Relationships • Desired Intent               │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     PLATFORM CONTROL PLANE                           │
│                                                                     │
│ Workflow Engine (n8n) • Orchestration Only • No Business Logic        │
│ Governance • RBAC • Approval Workflows • Secret Management           │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 CANONICAL ENGINEERING MODEL                          │
│                                                                     │
│                Cisco NetAsCode (Canonical Model)                     │
└──────────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ Terraform               │     │ Ansible                 │
│ Declarative Deployment  │     │ Day-2 Operations        │
└─────────────────────────┘     └─────────────────────────┘
                    │                       │
                    └───────────┬───────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  MANAGED INFRASTRUCTURE                              │
│                                                                     │
│ Cisco ACI • Nexus VXLAN EVPN • Azure                               │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│               CONTINUOUS VALIDATION  (event-driven)                 │
│                                                                     │
│ pyATS • Catfish • Custom Validation Pipelines                        │
│ Subscribes to DeploymentCompleted • Publishes ValidationPassed/Failed │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│              OBSERVABILITY  (continuous • cross-cutting)             │
│                                                                     │
│ Prometheus • Grafana • Loki • Alertmanager                           │
│ Spans API • Workflow • Execution • Infrastructure • Validation       │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│              KNOWLEDGE & AI LAYER  (Engineering Memory)             │
│                                                                     │
│ Obsidian • MCP • Vector DB • Claude • ChatGPT                        │
│ Receives from Deployment • Validation • Observability • Runbooks     │
└──────────────────────────────────────────────────────────────────────┘
```

---

# Core Architectural Concepts

The architecture is built around eight core concepts.

| Concept                  | Purpose                                                   |
| ------------------------ | --------------------------------------------------------- |
| Entry Points             | Multiple channels into the platform (Portal, CLI, AI ...) |
| Intent Translation       | Normalise all inputs into a Canonical Intent Model        |
| Canonical Intent         | The internal language of the platform                     |
| Engineering Intent       | Define what the business requires (Nautobot)              |
| Canonical Model          | Represent intent in a technology-neutral format           |
| Platform Control Plane   | Coordinate all platform execution                         |
| Execution Engines        | Deploy and operate infrastructure                         |
| Validation               | Independently verify correctness                          |
| Observability            | Continuously monitor operational reality (cross-cutting)  |

Each concept is independent.

Each concept has a single responsibility.

**Canonical Intent vs. Canonical Model — these are not the same tier.** Canonical Intent is produced *before* Nautobot and is domain-agnostic (one shape regardless of target infrastructure). Canonical Model (e.g. NetAsCode) is produced *after* Nautobot and is domain-specific (one model per infrastructure domain — ACI, VXLAN EVPN, Azure each need their own). See the **Canonical Intent** glossary entry in [`03a-Platform-Glossary.md`](03a-Platform-Glossary.md) for the full contrast table. As of 2026-07-04, only the domain-specific tier (NetAsCode) has a working implementation; Canonical Intent has no schema yet.

---

# Architectural Layers

The platform is divided into logical layers.

Each layer communicates only with adjacent layers through well-defined interfaces.

```text
Entry Points
(Portal • CLI • Jira • Git • AI • REST)
      │
      ▼
Intent Translation
(Platform API)
      │
      ▼
Canonical Intent
      │
      ▼
Engineering Intent
(Nautobot)
      │
      ▼
Canonical Model
(NetAsCode)
      │
      ▼
Execution
(Terraform / Ansible)
      │
      ▼
Infrastructure
      │
      ▼
Validation
      │
      ▼
Observability (continuous • cross-cutting)
      │
      ▼
Knowledge & AI
```

This layered approach minimises coupling and simplifies long-term evolution.

---

# Platform Control Plane vs Execution Plane

The platform separates two distinct planes of operation.

This separation is a fundamental architectural principle.

## Platform Control Plane

Owns business logic.

| Component | Responsibility |
|---|---|
| Platform API | Authentication, Authorisation, Intent Translation |
| Platform API | Request Validation, Policy Enforcement |
| Platform API | Canonical Intent Generation, Event Publishing |
| Nautobot | Engineering Intent Storage |
| NetAsCode Generator | Canonical Model Generation |
| Event Bus | Asynchronous event backbone |
| Workflow Engine (n8n) | Orchestration only — reacts to events, no business logic |

## Execution Plane

Owns delivery.

| Component | Responsibility |
|---|---|
| Terraform | Infrastructure provisioning (desired state) |
| Ansible | Day-2 operations |
| pyATS / Catfish | Independent validation |
| HashiCorp Vault | Secret retrieval |
| Notification Services | Engineers and stakeholders |

The Control Plane decides **what** happens.

The Execution Plane decides **how** it happens.

---

# Many Entry Points, One Execution Path

A defining architectural principle is that the execution path is always identical regardless of the request origin.

Entry points include:

* Self-service Portal
* CLI
* Jira ticket transitions
* Git commits / Pull Requests
* AI Engineering Assistants
* REST API
* ServiceNow
* CI/CD pipelines

Every request passes through the same canonical execution path:

```text
Entry Point (any)
     │
     ▼
Platform API (Intent Translation)
     │
     ▼
Canonical Intent ──► Event Published (IntentReceived)
     │
     ▼
Nautobot ──► Event Published (IntentStored)
     │
     ▼
Workflow Engine ──► Event Subscription
     │
     ▼
Execution (Terraform / Ansible) ──► Event Published (DeploymentCompleted)
     │
     ▼
Validation ──► Event Published (ValidationPassed / Failed)
     │
     ▼
Knowledge Layer ──► Engineering Memory Updated
```

No consumer bypasses the Platform API.

No consumer receives special treatment.

---

# End-to-End Engineering Flow

Every infrastructure change follows the same engineering lifecycle.

```text
Business Requirement
        │
        ▼
Engineer updates Nautobot
        │
        ▼
Platform API validates request
        │
        ▼
Workflow Engine starts execution
        │
        ▼
Cisco NetAsCode model generated
        │
        ▼
Terraform or Ansible selected
        │
        ▼
Infrastructure updated
        │
        ▼
Validation pipeline executes
        │
        ▼
Observability confirms health
        │
        ▼
Knowledge repository updated
```

This workflow remains consistent regardless of the infrastructure domain.

---

# Separation of Responsibilities

Every major component owns one responsibility.

| Component            | Owns                        |
| -------------------- | --------------------------- |
| Nautobot             | Engineering Intent          |
| Platform API         | Platform abstraction        |
| Workflow Engine      | Orchestration               |
| Cisco NetAsCode      | Canonical Engineering Model |
| Terraform            | Infrastructure Provisioning |
| Ansible              | Operational Configuration   |
| Validation Framework | Independent Verification    |
| Observability Stack  | Operational Visibility      |
| Knowledge Layer      | Engineering Knowledge       |
| AI Layer             | Engineering Assistance      |

No responsibility should be duplicated across multiple components.

---

# Engineering Principles in Action

The reference architecture directly implements the Platform Principles.

| Platform Principle            | Architectural Implementation |
| ----------------------------- | ---------------------------- |
| Single Source of Truth        | Nautobot                     |
| Intent Before Configuration   | Engineering Intent Layer     |
| Canonical Engineering Model   | Cisco NetAsCode              |
| Platform Control Plane        | Platform API + n8n           |
| Validation First              | pyATS / Catfish              |
| Closed-Loop Engineering       | Validation + Observability   |
| Engineering Assets as Code    | Git Repository               |
| API First                     | Platform API                 |
| Security by Design            | Vault + RBAC + Audit         |
| AI Assists, Platform Executes | AI Layer + Control Plane     |

---

# Architectural Characteristics

The platform is intentionally designed to be:

* Intent-driven
* Declarative
* Modular
* Event-driven
* Observable
* Secure
* Extensible
* Vendor-aware but not vendor-locked
* AI-augmented
* Governed

These characteristics influence every architectural decision.

---

# Design Goals

The architecture aims to achieve the following long-term outcomes:

1. A single engineering workflow across multiple infrastructure domains.
2. Consistent deployment and operational practices.
3. Reusable automation components.
4. Independent validation of every infrastructure change.
5. Continuous operational feedback.
6. Centralised engineering knowledge.
7. AI-assisted engineering without bypassing governance.
8. A platform that evolves by extension rather than redesign.

---

# Reference Architecture Principles

This document should be read alongside:

* `03-Platform-Principles.md`
* `03a-Platform-Glossary.md`
* Architecture Decision Records (ADRs)

Together, these documents define both **how the platform is organised** and **why it has been designed in this manner**.

# Platform Layers

The Network Platform Engineering Platform is organised into logical architectural layers.

Each layer has a single responsibility and exposes well-defined interfaces to adjacent layers.

No layer should bypass another unless explicitly documented.

The following sections describe each layer in detail.

---

# Layer 1 — Engineering Experience Layer

## Purpose

Provide a consistent interface for engineers and service consumers.

This layer represents **where engineering begins**.

Users should never need to understand the implementation details of Cisco ACI, VXLAN EVPN or Azure networking.

## Consumers

* Network Engineers
* Cloud Engineers
* Platform Engineers
* Operations Teams
* Service Owners
* AI Assistants

## Responsibilities

* Capture engineering intent
* Service requests
* Change requests
* Engineering review
* Platform documentation
* Design guidance

## Interfaces

Communicates only with the Engineering Intent Layer.

---

# Layer 2 — Engineering Intent Layer

## Purpose

Maintain the authoritative representation of desired infrastructure.

This layer contains the engineering model of the organisation.

## Primary Component

Nautobot

## Responsibilities

* Inventory
* Services
* Tenants
* VRFs
* Applications
* Relationships
* Metadata
* Desired engineering state

This layer does **not** deploy infrastructure.

It simply answers:

> What should exist?

---

# Layer 3 — Platform Control Plane

## Purpose

Coordinate every platform activity.

The Platform Control Plane is the heart of the platform.

Nothing reaches infrastructure without passing through this layer.

## Primary Components

* Platform API
* n8n Workflow Engine
* Authentication
* RBAC
* Approval workflows
* Audit logging
* Secret retrieval
* Event processing

## Responsibilities

* Workflow orchestration
* Policy enforcement
* Authentication
* Authorization
* Governance
* Notifications
* Job scheduling
* Event routing

## Why it exists

Without a Control Plane, every platform component would integrate directly with every other component.

The result would be:

* Tight coupling
* Duplicate logic
* Difficult maintenance
* Inconsistent execution

The Control Plane eliminates these problems.

---

# Layer 4 — Canonical Engineering Model

## Purpose

Provide a common engineering language understood by every automation engine.

Rather than allowing Terraform and Ansible to invent independent models, both consume a single engineering representation.

## Primary Component

Cisco NetAsCode

## Responsibilities

* Normalize engineering intent
* Provide reusable schemas
* Vendor abstraction
* Validation before execution
* Reusable object definitions

This layer represents the bridge between engineering and automation.

---

# Layer 5 — Execution Layer

## Purpose

Translate engineering models into infrastructure changes.

Execution engines never decide *what* should be deployed.

They only determine *how* to deploy approved engineering intent.

The platform deliberately separates provisioning from operational configuration.

---

## Terraform

### Responsibilities

* Infrastructure provisioning
* Initial deployment
* Lifecycle management
* Declarative state
* Resource dependency management

Typical examples:

* Tenant creation
* VRFs
* Bridge Domains
* Application Profiles
* Azure VNets
* Azure Firewalls
* Route Tables

---

## Ansible

### Responsibilities

* Day-2 operations
* Operational configuration
* Maintenance
* Compliance
* Operational workflows
* Incident automation

Typical examples:

* BFD policies
* Interface descriptions
* Configuration adjustments
* Operational maintenance
* Health checks
* Configuration collection

Terraform and Ansible complement rather than replace each other.

---

# Layer 6 — Infrastructure Layer

## Purpose

Represent the managed infrastructure.

Infrastructure is intentionally placed beneath the automation platform.

It does not own engineering intent.

Examples include:

Cisco ACI

Cisco Nexus VXLAN EVPN

Azure

Future domains may include:

* SD-WAN
* Kubernetes
* VMware
* AWS
* Palo Alto
* F5

Infrastructure remains an implementation target.

---

# Layer 7 — Validation Layer

## Purpose

Provide independent verification that infrastructure satisfies engineering intent.

Validation remains independent from deployment.

Deployment success does not imply infrastructure correctness.

## Primary Components

* pyATS
* Catfish
* Python validation libraries

## Validation Categories

Infrastructure Validation

Configuration Validation

Connectivity Validation

Service Validation

Compliance Validation

Performance Validation

Security Validation

Validation results are returned to the Platform Control Plane.

---

# Layer 8 — Observability Layer

## Purpose

Provide continuous operational visibility.

Observability extends beyond infrastructure monitoring.

The platform observes:

Infrastructure

Automation

Validation

Workflows

Platform APIs

AI interactions

Knowledge services

## Primary Components

Prometheus

Grafana

Loki

Alertmanager

Future:

OpenTelemetry

Jaeger

Tempo

---

# Layer 9 — Knowledge Layer

## Purpose

Preserve institutional engineering knowledge.

Knowledge should remain independent of individual engineers.

## Primary Components

Obsidian

Git

Vector Database

MCP Server

Markdown Documentation

Architecture Diagrams

Runbooks

Prompt Library

Standards

Lessons Learned

The Knowledge Layer continuously grows alongside the platform.

---

# Layer 10 — AI Engineering Layer

## Purpose

Assist engineers throughout the engineering lifecycle.

AI does not execute infrastructure changes.

AI provides reasoning.

Execution remains the responsibility of the Platform Control Plane.

Typical AI capabilities include:

Architecture reviews

Terraform generation

Ansible generation

Validation analysis

Incident analysis

Documentation

Design recommendations

Knowledge retrieval

Operational guidance

Root cause analysis

---

# Platform Integration Pattern

Every platform capability follows the same integration model.

```text
Capability
      │
      ▼
Platform API
      │
      ▼
Workflow Engine
      │
      ▼
Execution Engine
      │
      ▼
Validation
      │
      ▼
Observability
```

This pattern should be reused whenever new platform capabilities are introduced.

---

# Component Interaction Matrix

| Layer              | Owns                        | Never Owns               |
| ------------------ | --------------------------- | ------------------------ |
| Engineering Intent | Desired State               | Infrastructure           |
| Control Plane      | Orchestration               | Device Configuration     |
| Canonical Model    | Engineering Representation  | Workflow Logic           |
| Terraform          | Infrastructure Provisioning | Operations               |
| Ansible            | Operations                  | Source of Truth          |
| Validation         | Verification                | Deployment               |
| Observability      | Telemetry                   | Automation               |
| Knowledge          | Documentation               | Infrastructure           |
| AI                 | Reasoning                   | Infrastructure Execution |

The architecture deliberately assigns exactly one responsibility to each layer.

---

# Data Ownership

One of the most important architectural principles is that data ownership is never ambiguous.

| Data                      | Owner                |
| ------------------------- | -------------------- |
| Engineering Intent        | Nautobot             |
| Canonical Model           | Cisco NetAsCode      |
| Terraform State           | Terraform            |
| Operational Configuration | Infrastructure       |
| Validation Results        | Validation Framework |
| Metrics                   | Prometheus           |
| Logs                      | Loki                 |
| Dashboards                | Grafana              |
| Documentation             | Git Repository       |
| Architecture Decisions    | ADR Repository       |
| Knowledge                 | Obsidian             |
| Secrets                   | Vault                |
| Workflow Definitions      | n8n                  |

Every piece of platform data has one authoritative owner.

This prevents conflicting sources of truth and simplifies governance.

---

# Layer Independence

Each architectural layer should be independently replaceable.

For example:

Terraform may eventually become OpenTofu.

n8n could become another orchestration engine.

Grafana could be replaced.

The AI platform may evolve.

These implementation changes should not require redesigning the overall architecture.

The reference architecture therefore describes capabilities rather than products.

# Engineering Lifecycle

The platform follows a deterministic engineering lifecycle.

Every infrastructure change, regardless of technology domain, progresses through the same stages.

```text
Business Requirement
        │
        ▼
Engineering Intent
        │
        ▼
Engineering Review
        │
        ▼
Platform Approval
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
Continuous Improvement
```

This lifecycle provides a consistent engineering experience while ensuring governance, repeatability and continuous feedback.

---

# End-to-End Deployment Workflow

The following sequence illustrates how a new infrastructure service is deployed.

## Step 1 — Business Requirement

A business or application team requests a new service.

Examples include:

* New ACI Tenant
* New Azure Landing Zone
* New VXLAN EVPN Tenant
* New Application Environment

The request focuses on the required business outcome rather than implementation details.

---

## Step 2 — Engineering Intent

A Platform Engineer translates the request into Engineering Intent.

This information is captured within Nautobot.

Examples include:

* Tenant
* VRFs
* Bridge Domains
* Contracts
* Service metadata
* Ownership
* Tags
* Environment
* Security classification

At this stage no infrastructure has been modified.

---

## Step 3 — Platform Validation

Before execution, the Platform Control Plane performs validation.

Typical checks include:

* Schema validation
* Mandatory attributes
* Naming standards
* Policy compliance
* Duplicate detection
* Dependency analysis

Only valid engineering intent proceeds to execution.

---

## Step 4 — Canonical Engineering Model

Engineering Intent is translated into the Canonical Engineering Model.

For Cisco ACI this is Cisco NetAsCode.

The canonical model becomes the single input for all automation engines.

---

## Step 5 — Workflow Orchestration

The Platform Control Plane determines:

* Required automation engine
* Execution order
* Dependencies
* Approvals
* Secrets
* Target environment

The workflow engine coordinates the execution.

---

## Step 6 — Infrastructure Execution

Execution engines perform infrastructure changes.

Examples include:

Terraform:

* Tenant creation
* VRFs
* Application Profiles
* Bridge Domains

Ansible:

* BFD configuration
* Operational tuning
* Day-2 policies
* Configuration adjustments

Execution remains deterministic and repeatable.

---

## Step 7 — Continuous Validation

Immediately after deployment, validation begins.

Validation is independent of deployment.

Examples include:

Infrastructure validation

Connectivity validation

Contract validation

Policy validation

Routing validation

Health validation

Application reachability

Validation results are returned to the Platform Control Plane.

---

## Step 8 — Observability

The Observability Layer continuously monitors:

Infrastructure

Automation

Validation

Platform services

Workflow execution

API performance

Operational health

Observability continues throughout the platform lifecycle.

---

## Step 9 — Knowledge Capture

Every engineering activity generates knowledge.

Examples include:

Deployment history

Lessons learned

Validation reports

Architecture decisions

Operational runbooks

AI conversations

Engineering documentation

Knowledge becomes reusable for future engineering work.

---

## Step 10 — Continuous Improvement

Operational feedback drives future improvements.

Examples include:

Improved automation

Updated standards

Better validation

New platform capabilities

Additional AI skills

Architecture refinement

The platform continuously evolves without changing its architectural foundations.

---

# Day-2 Operational Workflow

Infrastructure deployment is only the beginning of the lifecycle.

Operational activities continue throughout the life of the platform.

Typical Day-2 activities include:

Policy changes

BFD updates

Maintenance

Incident response

Compliance remediation

Configuration tuning

Operational automation follows the same lifecycle:

```text
Operational Request
        │
        ▼
Engineering Intent
        │
        ▼
Platform Approval
        │
        ▼
Ansible Workflow
        │
        ▼
Validation
        │
        ▼
Observability
        │
        ▼
Knowledge Update
```

---

# Validation Lifecycle

Validation is continuous rather than a one-time activity.

The platform performs validation:

Before deployment

During deployment

Immediately after deployment

Scheduled validation

On-demand validation

Event-driven validation

Typical validation triggers include:

Infrastructure deployment

Monitoring alerts

Configuration drift

Policy changes

Software upgrades

Security events

---

# Drift Management

The platform distinguishes three categories of drift.

## Engineering Drift

Engineering Intent differs from approved business requirements.

Detected during engineering review.

---

## Infrastructure Drift

Infrastructure differs from the deployed declarative state.

Detected through validation and reconciliation.

---

## Operational Drift

Running infrastructure differs from approved operational policies.

Detected through operational validation and compliance checks.

Each drift category follows a different remediation workflow.

---

# Event-Driven Automation

Platform events trigger automation workflows.

Examples include:

Deployment completed

Deployment failed

Validation passed

Validation failed

Monitoring alert

Ticket created

CAB approval

Emergency maintenance

Secrets rotated

AI recommendation approved

The Workflow Engine coordinates all event processing.

---

# Closed-Loop Engineering

The platform continuously compares Engineering Intent with operational reality.

```text
Intent
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
Analysis
   │
   ▼
Improvement
   │
   └────────────► Updated Intent
```

This feedback loop enables continuous engineering improvement.

---

# Platform Feedback Loops

Multiple feedback loops exist simultaneously.

## Validation Feedback

Validation results improve automation quality.

---

## Operational Feedback

Operational incidents improve platform workflows.

---

## Knowledge Feedback

Lessons learned improve engineering documentation.

---

## AI Feedback

Successful engineering patterns improve AI recommendations.

---

## Architecture Feedback

Experience drives future architectural improvements.

---

# Lifecycle Responsibilities

| Stage                    | Primary Owner             |
| ------------------------ | ------------------------- |
| Business Requirement     | Service Owner             |
| Engineering Intent       | Platform Engineer         |
| Platform Validation      | Platform Control Plane    |
| Canonical Model          | Cisco NetAsCode           |
| Workflow Orchestration   | n8n                       |
| Infrastructure Execution | Terraform / Ansible       |
| Validation               | pyATS / Catfish           |
| Observability            | Prometheus / Grafana      |
| Knowledge Capture        | Git + Obsidian            |
| Continuous Improvement   | Platform Engineering Team |

Clear ownership simplifies governance and accountability.

---

# Success Criteria

A platform change is considered successful only when:

✓ Engineering Intent has been approved.

✓ Infrastructure deployment completed successfully.

✓ Validation passed.

✓ No policy violations exist.

✓ Observability confirms operational health.

✓ Audit records have been generated.

✓ Documentation has been updated where applicable.

✓ Knowledge has been retained.

Successful deployment is therefore defined by **business correctness**, not simply infrastructure creation.

---

# Engineering Maturity Model

The architecture supports progressive organisational maturity.

| Level   | Characteristics                  |
| ------- | -------------------------------- |
| Level 1 | Manual deployments               |
| Level 2 | Infrastructure as Code           |
| Level 3 | Platform Control Plane           |
| Level 4 | Continuous Validation            |
| Level 5 | Closed-Loop Engineering          |
| Level 6 | AI-Assisted Platform Engineering |

The objective of this platform is to operate consistently at **Level 6** while preserving governance and engineering oversight.

---

# Summary

The engineering lifecycle transforms infrastructure deployment into a governed, repeatable and continuously improving process.

Rather than viewing automation as a one-time deployment activity, the platform treats infrastructure as a living engineering system.

Every deployment contributes to:

* Better automation
* Better validation
* Better observability
* Better documentation
* Better AI assistance
* Better engineering practices

This lifecycle is the operational realization of the Platform Principles and provides the foundation for long-term platform evolution.
