---
type: architecture
domain: platform
status: historical
tags: [control-plane]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# Platform Control Plane

**Document Type:** Reference Architecture

**Status:** Draft v1.0

**Owner:** Platform Engineering

> **Implementation Status:** This document describes the target Platform Control Plane. For what is actually built and running today, see [`../01-Vision/01-Current-State.md`](../01-Vision/01-Current-State.md). As of 2026-07-04, the Intent Translation Layer, Canonical Intent, Event Bus, and Workflow Engine described below are **not implemented** — the working vertical slice bypasses this control plane entirely via direct CLI invocation of Terraform/Ansible/pyATS.

---

# Purpose

The Platform Control Plane is the engineering brain of the Network Platform Engineering Platform.

It is responsible for transforming engineering requests into validated, governed and canonical engineering intent before any infrastructure automation begins.

The Control Plane **never provisions infrastructure directly**.

Its responsibility is to make engineering decisions.

Infrastructure execution is delegated to the Execution Plane.

---

# Core Principle

> **Many Entry Points**
>
> ↓
>
> **One Canonical Intent**
>
> ↓
>
> **One Execution Path**

Regardless of whether a request originates from:

- AI Assistant
- Jira
- ServiceNow
- Self-Service Portal
- REST API
- Git Pull Request
- CLI

every request follows exactly the same internal engineering workflow.

---

# Platform Control Plane Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ENGINEERING REQUESTS                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ Engineer │ AI │ Jira │ ServiceNow │ Portal │ REST │ Git │ CLI │ MCP Tools   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
═══════════════════════════════════════════════════════════════════════════════════════
                          PLATFORM CONTROL PLANE
═══════════════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│ Platform API (FastAPI)                                                      │
│─────────────────────────────────────────────────────────────────────────────│
│ • Authentication                                                            │
│ • Authorization (RBAC)                                                      │
│ • Request Validation                                                        │
│ • API Versioning                                                            │
│ • Audit Logging                                                             │
│ • Rate Limiting                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Intent Translation Layer                                                    │
│─────────────────────────────────────────────────────────────────────────────│
│ • Parse requests                                                            │
│ • Normalize formats                                                         │
│ • Apply engineering defaults                                                │
│ • Resolve dependencies                                                      │
│ • Validate naming                                                           │
│ • Build Canonical Intent                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Policy & Intent Validation                                                  │
│─────────────────────────────────────────────────────────────────────────────│
│ • Schema Validation                                                         │
│ • OPA Policy Enforcement                                                    │
│ • Business Rules                                                            │
│ • Environment Constraints                                                   │
│ • Approval Requirements                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Canonical Engineering Model                                                 │
│─────────────────────────────────────────────────────────────────────────────│
│ Cisco NetAsCode                                                             │
│                                                                             │
│ Tenant                                                                      │
│ VRF                                                                         │
│ Bridge Domain                                                               │
│ EPG                                                                         │
│ Contract                                                                    │
│ L3Out                                                                       │
│ Relationships                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Nautobot                                                                    │
│─────────────────────────────────────────────────────────────────────────────│
│ Authoritative Source of Truth                                               │
│                                                                             │
│ • Inventory                                                                 │
│ • IPAM                                                                      │
│ • Tenants                                                                   │
│ • VRFs                                                                      │
│ • VLANs                                                                     │
│ • Relationships                                                             │
│ • Custom Models                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Event Publication                                                           │
│─────────────────────────────────────────────────────────────────────────────│
│ DeploymentRequested                                                         │
│ DeploymentApproved                                                          │
│ ValidationRequested                                                         │
│ DriftDetected                                                               │
│ KnowledgeUpdated                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
═══════════════════════════════════════════════════════════════════════════════════════
                                 EVENT BUS
═══════════════════════════════════════════════════════════════════════════════════════

Candidates under consideration (not yet decided — see ADR-011): Kafka │ RabbitMQ │ Webhooks

                                      │
                                      ▼
═══════════════════════════════════════════════════════════════════════════════════════
                              EXECUTION PLANE
═══════════════════════════════════════════════════════════════════════════════════════

n8n

↓

Terraform

↓

Cisco ACI / VXLAN EVPN

↓

Ansible

↓

Validation

↓

Observability

↓

Knowledge Layer
```

---

# Responsibilities

The Platform Control Plane is responsible for:

- Receiving engineering requests
- Translating requests into engineering intent
- Validating engineering intent
- Applying platform policies
- Resolving engineering relationships
- Maintaining the authoritative Source of Truth
- Publishing platform events
- Coordinating governance

It is **not** responsible for infrastructure provisioning.

---

# Intent Translation Layer

The Intent Translation Layer is one of the most important architectural capabilities.

Different clients communicate using different formats.

Examples include:

- Natural language
- Jira tickets
- ServiceNow forms
- REST requests
- Portal forms
- Git pull requests

The Translation Layer converts every request into a single Canonical Engineering Model.

No client communicates directly with Nautobot or Terraform.

---

# Canonical Intent

Canonical Intent is the internal language of the platform.

Every deployment originates from a Canonical Intent object.

The Canonical Intent contains:

- Desired topology
- Relationships
- Policies
- Environment
- Ownership
- Business metadata

All downstream systems consume the same engineering model.

---

# Event Publication

Once Canonical Intent has been validated and persisted in Nautobot, the Platform Control Plane publishes an event.

Examples include:

- DeploymentRequested
- DeploymentApproved
- ValidationRequested
- DriftDetected
- KnowledgeUpdated
- IncidentRaised

The Control Plane does not invoke Terraform directly.

Execution begins only after an event has been published.

---

# Separation of Responsibilities

## Control Plane

Owns engineering decisions.

Examples include:

- Intent translation
- Policy enforcement
- Naming standards
- Dependency resolution
- Approval logic
- Canonical model generation

## Execution Plane

Owns infrastructure implementation.

Examples include:

- Workflow orchestration
- Terraform execution
- Ansible automation
- Validation
- Notifications

Business logic should never be implemented inside workflow definitions.

---

# Many Entry Points, One Execution Path

Every engineering request eventually follows the same lifecycle.

```text
Engineer / AI / Jira / Portal / REST

↓

Platform API

↓

Intent Translation

↓

Policy Validation

↓

Canonical Engineering Model

↓

Nautobot

↓

DeploymentRequested Event

↓

Workflow Engine

↓

Terraform

↓

Infrastructure

↓

Validation

↓

Observability

↓

Knowledge Layer
```

---

# Architectural Benefits

This architecture provides several important benefits:

- Single Source of Truth
- Technology-independent clients
- Reusable workflows
- Consistent governance
- Centralized policy enforcement
- Event-driven automation
- Reduced workflow complexity
- Easier platform evolution
- Support for multiple request channels
- Clear separation between engineering decisions and infrastructure execution

---

# Key Design Principle

> The Platform Control Plane owns **engineering intent**.
>
> The Execution Plane owns **engineering implementation**.

This separation enables the platform to evolve independently of the underlying automation technologies while ensuring every infrastructure change follows a consistent, governed, and repeatable engineering process.