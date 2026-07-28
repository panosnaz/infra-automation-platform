---
type: standard
domain: platform
status: active
tags: [glossary]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 03a – Platform Glossary

**Project:** Network Platform Engineering Platform

**Document Type:** Architecture Glossary

**Version:** 1.0

**Status:** Draft

**Owner:** Platform Engineering Team

---

# Purpose

This glossary defines the common architectural vocabulary used throughout the Network Platform Engineering Platform.

The objective is to ensure that engineers, architects, operations teams and AI agents use the same terminology with the same meaning.

Unless explicitly stated otherwise, the definitions contained in this document take precedence over informal interpretations.

---

# A

## AI Agent

A software component that uses Large Language Models (LLMs) and supporting tools to assist engineers with design, analysis, documentation, automation or troubleshooting.

AI agents provide recommendations and reasoning but do not directly modify production infrastructure.

---

## AI Reasoning Plane

The logical layer responsible for AI-assisted engineering activities.

Responsibilities include:

* Architecture recommendations
* Design validation
* Documentation generation
* Root cause analysis
* Knowledge retrieval
* Code generation
* Operational guidance

The AI Reasoning Plane never interacts directly with managed infrastructure.

Infrastructure execution always occurs through the Platform Control Plane.

---

## Architecture Decision Record (ADR)

A document that records an important architectural decision.

Each ADR documents:

* Context
* Decision
* Alternatives
* Consequences
* Rationale

ADRs explain *why* architectural decisions were made.

---

## Automation Workflow

A repeatable sequence of platform activities executed by the Workflow Engine.

Examples include:

* Tenant deployment
* Validation pipeline
* Drift remediation
* Day-2 operational changes

---

# B

## Business Intent

The business outcome requested by an engineer or service owner.

Examples include:

* Deploy a new application environment.
* Create a production tenant.
* Enable external connectivity.

Business intent describes *what* the business requires rather than *how* infrastructure is implemented.

---

# C

## Canonical Engineering Model

The common engineering representation used between Engineering Intent and infrastructure execution.

The Canonical Engineering Model provides a technology-neutral abstraction that can be consumed by multiple automation engines.

Within this platform, Cisco NetAsCode fulfils this role for Cisco ACI.

**Not to be confused with Canonical Intent** (below) — these are two distinct tiers of abstraction sitting on opposite sides of the Source of Truth. See **Canonical Intent** for the contrast.

---

## Canonical Intent

The domain-agnostic, fully validated and policy-checked representation of a request produced by the Platform API's Intent Translation Layer, *before* it is written to Nautobot.

Canonical Intent exists to normalise diverse input formats (natural language, Jira tickets, REST payloads, Git commits, portal forms) into one internal shape, regardless of which infrastructure domain (Cisco ACI, VXLAN EVPN, Azure, future domains) the request ultimately targets.

**Contrast with Canonical Engineering Model:**

| | Canonical Intent | Canonical Engineering Model |
|---|---|---|
| Position | Before Nautobot (Platform API → Nautobot) | After Nautobot (Nautobot → Terraform/Ansible) |
| Scope | Domain-agnostic — one shape for every infrastructure domain | Domain-specific — one model per domain (e.g. NetAsCode for Cisco ACI) |
| Produced by | Platform API (Intent Translation Layer) | The generator (e.g. `platform/python/generate_aci.py`) |
| Example in this platform | Not yet implemented — no schema exists as of 2026-07-04 | NetAsCode YAML (`platform/netascode/aci/tenants.yaml`) |

Both are "canonical" in the sense of being the single normalized shape at their respective tier — but they normalize different things (any-format-request vs. any-Cisco-ACI-object) at different pipeline stages. A platform serving multiple infrastructure domains needs exactly one Canonical Intent shape and one Canonical Engineering Model per domain — never the reverse.

---

## Closed-Loop Engineering

An engineering model in which infrastructure is continuously compared against engineering intent through validation and observability.

Feedback from deployed infrastructure is incorporated into future engineering decisions.

---

## Configuration Drift

A condition where deployed infrastructure differs from the approved engineering intent.

Drift may result from:

* Manual configuration changes
* Failed deployments
* Vendor upgrades
* Operational incidents

---

## Control Plane

See **Platform Control Plane**.

---

# D

## Day-2 Operations

Operational activities performed after initial infrastructure deployment.

Examples include:

* Policy tuning
* BFD updates
* Operational maintenance
* Incident response
* Compliance remediation
* Scheduled operational changes

Day-2 Operations are typically executed through Ansible workflows.

---

## Desired State

The infrastructure configuration that should exist after successful deployment.

Desired State is derived from Engineering Intent.

Desired State should not be confused with Business Intent.

---

## Drift

See **Configuration Drift**.

---

# E

## Engineering Asset

Any artefact created and maintained as part of the Platform Engineering lifecycle.

Examples include:

* Source code
* Terraform modules
* Ansible playbooks
* ADRs
* Documentation
* Validation tests
* Policies
* Runbooks
* Prompt libraries

Engineering Assets should be version controlled.

---

## Engineering Intent

The structured representation of infrastructure requirements maintained within the Source of Truth.

Engineering Intent is sufficiently detailed for platform automation but remains independent of implementation technologies.

Engineering Intent answers:

> What infrastructure should exist?

It does not describe:

> How infrastructure should be deployed.

---

## Engineering Pipeline

The ordered sequence through which engineering intent becomes operational infrastructure.

The platform pipeline consists of:

1. Business Intent
2. Engineering Intent
3. Canonical Engineering Model
4. Platform Execution
5. Validation
6. Observability
7. Continuous Improvement

---

## Event-Driven Automation

Automation initiated by platform events rather than scheduled execution.

Typical events include:

* Deployment completed
* Validation failed
* Monitoring alert
* Drift detected
* Service request approved

---

## Execution Plane

The collection of automation engines responsible for implementing Engineering Intent.

Typical components include:

* Terraform
* Ansible

Execution is coordinated through the Platform Control Plane.

---

# F

## Five-Stage Engineering Pipeline

The core engineering model used throughout the platform.

```text
Business Intent
        │
        ▼
Engineering Intent
        │
        ▼
Canonical Engineering Model
        │
        ▼
Execution
        │
        ▼
Validation
        │
        ▼
Observability
```

Every engineering activity should align with this lifecycle.

---

# G

## Governance

The processes that ensure infrastructure changes are reviewed, approved, validated and auditable.

Governance includes:

* Peer review
* Change approval
* Validation
* Audit logging
* Security review

---

# I

## Infrastructure as Code (IaC)

The practice of defining infrastructure through version-controlled, declarative code rather than manual configuration.

Terraform is the primary Infrastructure as Code technology used by the platform.

---

## Intent-Based Engineering

An engineering approach in which engineers describe the desired business outcome rather than individual infrastructure objects.

The platform determines the required implementation.

---

# K

## Knowledge Layer

The platform capability responsible for storing and retrieving engineering knowledge.

Examples include:

* Documentation
* ADRs
* Standards
* Runbooks
* Prompt libraries
* Design patterns

The Knowledge Layer supports both human engineers and AI agents.

---

# N

## NetAsCode

Cisco's declarative data model for defining Cisco ACI infrastructure.

Within this platform it serves as the Canonical Engineering Model between Engineering Intent and automation execution.

---

## Nautobot

The authoritative Source of Truth for Engineering Intent.

Nautobot stores:

* Inventory
* Relationships
* Service definitions
* Desired engineering state

Nautobot does not execute infrastructure changes.

---

# O

## Observability

The capability to understand platform behaviour through telemetry.

Observability includes:

* Metrics
* Logs
* Traces
* Events
* Audit records

Observability extends beyond infrastructure monitoring to include platform services and automation workflows.

---

# P

## Platform API

The logical interface through which all platform capabilities interact.

The Platform API abstracts implementation details from engineers and automation components.

---

## Platform Capability

A reusable functional responsibility provided by the platform.

Examples include:

* Validation
* Secret Management
* Observability
* Workflow Orchestration
* Knowledge Management

Capabilities remain stable even if implementation technologies change.

---

## Platform Control Plane

The orchestration layer responsible for coordinating infrastructure execution.

Responsibilities include:

* Workflow orchestration
* Governance
* Security
* Auditability
* Execution coordination
* API integration

Infrastructure execution should occur only through the Platform Control Plane.

---

## Platform Engineering

An engineering discipline focused on building reusable internal platforms that improve consistency, automation and developer productivity.

Within this project, Platform Engineering extends beyond software development to include network, cloud and infrastructure automation.

---

# S

## Secret Management

The secure storage and retrieval of credentials, API tokens, certificates and encryption keys.

Secrets should be retrieved dynamically at runtime and never embedded within code repositories.

---

## Source of Truth (SoT)

The authoritative repository that defines Engineering Intent.

The Source of Truth represents what infrastructure should exist rather than what currently exists.

Within this platform, Nautobot serves as the Source of Truth.

---

# T

## Terraform

The declarative infrastructure provisioning engine responsible for creating and managing infrastructure resources.

Terraform owns provisioning.

Terraform does not own Engineering Intent.

---

# V

## Validation

The independent verification that deployed infrastructure satisfies Engineering Intent.

Validation should remain independent of deployment.

Typical validation frameworks include:

* pyATS
* Catfish

---

## Version-Controlled Knowledge

The practice of maintaining engineering documentation alongside source code using Git.

Knowledge evolves through the same review process as software.

---

# W

## Workflow Engine

The orchestration component responsible for coordinating automation activities.

Typical responsibilities include:

* Workflow execution
* Event processing
* Retry logic
* Notifications
* Pipeline orchestration

n8n is the preferred implementation within the current platform architecture.

---

# Glossary Maintenance

This glossary is a living document.

New architectural concepts should be added as the platform evolves.

Whenever a new ADR introduces terminology that does not already exist within this glossary, the glossary should be updated as part of the same change.

Maintaining a consistent vocabulary is essential to preserving a coherent architecture.

---

# Summary

This glossary establishes the shared language of the Network Platform Engineering Platform.

By defining architectural concepts consistently, it enables effective collaboration between engineers, architects, operations teams and AI agents.

The glossary should be read alongside the Platform Principles, ADRs and Architecture Documentation and serves as the canonical reference for architectural terminology used throughout the platform.
