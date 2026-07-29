---
type: architecture
domain: platform
status: active
tags: [charter]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 00 – Project Charter

**Project:** Network Platform Engineering Platform
**Status:** Draft v1.0
**Owner:** Platform Engineering Team
**Document Type:** Project Charter
**Last Updated:** June 2026

> **Update (2026-07-29):** references to the Platform API and n8n below describe the original Platform v1 charter. Per [ADR-016](../adr/ADR-016-Platform-v2-Replacement-Architecture.md), the Platform API is replaced by the MCP Server + Nautobot + GitLab; see [`Platform-v2-Reference-Architecture.md`](Platform-v2-Reference-Architecture.md) and [`Execution-Framework.md`](Execution-Framework.md) for the current architecture and build status. The charter's mission, scope, and objectives below remain valid.

---

# 1. Executive Summary

## Purpose

The purpose of this project is to design and implement a modern **Network Platform Engineering** platform that enables declarative, repeatable, validated and governed deployment and operation of enterprise network infrastructure.

The platform is intended to evolve beyond simple infrastructure automation into a reusable engineering platform capable of managing multiple network domains through a common architecture.

Initially the platform will focus on Cisco ACI, but it is intentionally designed to support additional domains including Cisco Nexus VXLAN EVPN, Azure Networking and future infrastructure technologies.

Rather than building individual automation scripts, the objective is to build an extensible platform composed of independent services with clearly defined responsibilities.

---

# 2. Vision

Create a platform where network infrastructure is managed using engineering principles rather than manual configuration.

The platform should provide:

* A single authoritative Source of Truth.
* Declarative infrastructure deployment.
* Automated operational workflows.
* Continuous validation.
* Drift detection.
* Policy enforcement.
* Closed-loop feedback.
* AI-assisted engineering workflows.

The platform should allow engineers to describe **intent**, while the platform determines **how** to safely implement that intent.

---

# 3. Problem Statement

Enterprise network automation often evolves into collections of scripts that:

* duplicate configuration logic,
* lack governance,
* have inconsistent data models,
* provide little validation,
* are difficult to extend,
* tightly couple automation to individual technologies.

Cisco ACI introduces additional complexity due to its object hierarchy and relationships between tenants, VRFs, bridge domains, EPGs, contracts and external connectivity.

As additional infrastructure domains are introduced, independent automation solutions become increasingly difficult to maintain.

The project aims to replace isolated automation with a unified platform.

---

# 4. Objectives

The platform shall:

* Establish Nautobot as the authoritative Source of Truth.
* Implement declarative infrastructure deployment.
* Separate desired-state management from operational automation.
* Support multiple infrastructure domains.
* Enable repeatable deployments.
* Provide policy enforcement.
* Provide continuous validation.
* Detect configuration drift.
* Enable AI-assisted workflows.
* Maintain full auditability.

---

# 5. Scope

## Initial Scope

* Cisco ACI
* Nautobot
* Terraform
* Ansible
* FastAPI
* Git
* Docker
* Validation
* Observability

## Future Scope

* Cisco Nexus VXLAN EVPN
* Azure Networking
* Additional network domains
* Service Catalog
* Self-Service Portal
* AI Agents
* Event-Driven Automation
* ChatOps

---

# 6. Out of Scope

The platform will not initially provide:

* Multi-tenant SaaS capabilities
* Billing
* Capacity planning
* End-user portals
* Replacement of enterprise ITSM platforms
* Replacement of monitoring platforms

---

# 7. Guiding Principles

## Source of Truth

There shall be exactly one authoritative Source of Truth.

Nautobot owns network intent.

No infrastructure platform becomes the Source of Truth.

---

## Declarative Infrastructure

Infrastructure shall be managed using desired-state principles.

The platform describes **what** should exist.

Automation determines **how** to create it.

---

## Separation of Responsibilities

Infrastructure deployment and operational automation are different responsibilities.

Terraform owns infrastructure state.

Ansible owns operational automation.

Validation is independent.

---

## Platform over Scripts

The objective is not to automate individual tasks.

The objective is to build reusable platform capabilities.

---

## API First

Every platform capability should expose APIs.

Components communicate through APIs rather than direct database access.

---

## Modular Architecture

Each capability should be independently deployable.

Examples include:

* Validation
* Secrets
* Observability
* Platform API
* Workflow Engine

---

## Security by Design

Secrets must never be stored in source code.

Authentication and authorization must be implemented consistently across the platform.

---

## Validation First

Infrastructure changes should be validated before deployment and verified after deployment.

Validation is not optional.

---

## Everything as Code

Where practical:

* Infrastructure as Code
* Policy as Code
* Documentation as Code
* Validation as Code
* Workflow as Code

---

# 8. Architectural Principles

The platform separates responsibilities into distinct layers.

## Source of Truth

Responsible for:

* Network intent
* Inventory
* IPAM
* Relationships

Technology:

* Nautobot

---

## Intent Generation

Responsible for:

* Translating business intent into deployment artifacts.

Technologies:

* Python
* Pydantic
* Jinja2

---

## Desired State

Responsible for deploying infrastructure.

Technology:

* Terraform

---

## Operational Automation

Responsible for:

* Health checks
* Reporting
* Backups
* Day-2 tasks

Technology:

* Ansible

---

## Validation

Responsible for:

* Pre-deployment validation
* Post-deployment validation
* Compliance
* Drift detection

Technologies:

* pyATS
* Catfish

---

## Platform API

Responsible for exposing platform services through a stable interface.

Technology:

* FastAPI

---

## Workflow Orchestration

Responsible for orchestrating workflows between systems.

Technology:

* n8n

---

## Observability

Responsible for collecting platform metrics.

Technologies:

* Prometheus
* Grafana

---

# 9. Success Criteria

The project is considered successful when:

* Infrastructure can be deployed repeatably.
* Configuration is generated from intent.
* Manual infrastructure changes are minimized.
* Drift is detected automatically.
* Validation is automated.
* Platform components are loosely coupled.
* Engineers interact primarily with the Source of Truth rather than infrastructure APIs.

---

# 10. Non-Goals

The project does not attempt to eliminate engineers.

Instead, it enables engineers to:

* focus on architecture,
* reduce repetitive work,
* improve consistency,
* increase deployment confidence.

---

# 11. High-Level Platform Concept

```text
Users
        │
        ▼
Platform API
        │
        ▼
Workflow Engine
        │
        ▼
Nautobot (Source of Truth)
        │
        ├───────────────┬──────────────┬───────────────┐
        │               │              │               │
        ▼               ▼              ▼               ▼
Intent        Operations      Validation      Observability
Generation     Automation
        │               │              │
        └───────────────┴──────────────┘
                        │
                        ▼
              Infrastructure Domains
        ├── Cisco ACI
        ├── Cisco Nexus VXLAN EVPN
        ├── Azure Networking
        └── Future Platforms
                        │
                        ▼
                Closed-Loop Feedback
                        │
                        ▼
                     Nautobot
```

---

# 12. Long-Term Vision

The long-term objective is to create a reusable engineering platform capable of managing multiple infrastructure domains through a common operating model.

The platform should eventually support:

* self-service infrastructure provisioning,
* AI-assisted change planning,
* automated validation,
* policy-driven governance,
* event-driven automation,
* continuous compliance,
* multi-domain orchestration.

The platform should evolve without fundamental architectural redesign as new technologies and infrastructure domains are introduced.

---

# 13. Project Philosophy

This project is not intended to build "another automation repository."

It is intended to build a maintainable engineering platform whose principles remain valid as technologies evolve.

Individual tools may change over time.

The architectural principles defined in this document should remain stable and guide future design decisions.
