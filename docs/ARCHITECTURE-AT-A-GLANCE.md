# Network Platform Engineering Platform

> **Architecture at a Glance**

Version: 1.0

---

# Executive Summary

The Network Platform Engineering Platform is an AI-augmented Platform Engineering solution designed to automate, validate and operate modern network infrastructure through a common engineering framework.

The platform currently targets:

- Cisco ACI
- Cisco Nexus VXLAN EVPN
- Azure Networking

while remaining extensible to additional infrastructure domains.

Unlike traditional automation projects, this platform separates:

- Engineering Intent
- Platform Execution
- Continuous Validation
- Observability
- AI Reasoning

This separation provides deterministic automation while allowing AI to enhance engineering productivity without directly controlling infrastructure.

---

# Platform Vision

Build a reusable engineering platform capable of managing multiple infrastructure domains through a common architecture.

The platform should provide:

- Declarative Infrastructure
- Continuous Validation
- Event-Driven Automation
- AI-Assisted Engineering
- Platform Observability
- Security by Design
- Knowledge-Driven Operations

---

# Core Principles

The platform follows these architectural principles.

✔ Source of Truth Driven

✔ Platform Engineering

✔ Infrastructure as Code

✔ Configuration as Code

✔ Validation First

✔ Security by Design

✔ Observability Everywhere

✔ AI Assists — Platform Executes

✔ Modular Architecture

✔ Domain Independence

✔ Canonical Intent

✔ Many Entry Points — One Execution Path

✔ Event-Driven Backbone

---

# High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                             │
│                                                                 │
│  Portal  •  CLI  •  Jira  •  Git  •  AI Agents  •  REST API    │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
               Platform API  (Intent Translation)
               Auth • Authz • Validation • Normalization
               Policy Enforcement • Canonical Intent
                               │
                               ▼
                    ┌──────────────────┐
                    │  Event Bus       │  ◄── platform backbone
                    └──────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
           Nautobot (SoT)          Workflow Engine
           Engineering Intent      Orchestration
                    │                     │
                    ▼                     ▼
             Canonical Model     ┌────────┴────────┐
             (NetAsCode)         ▼                 ▼
                    │         Terraform         Ansible
                    └────────►  │                 │
                               └────────┬────────┘
                                        ▼
                             Managed Infrastructure
                                        │
                                        ▼
                             Continuous Validation
                                        │
                                        ▼
                              Platform Observability
                                        │
                                        ▼
                              Knowledge & AI Layer
                                        │
                                        ▼
                           Improved Engineering Intent
```

Many entry points.  One canonical execution path.

This creates a closed engineering feedback loop.

---

# Platform Layers

## Layer 1

Engineers

Architects

Operations

---

## Layer 2

Source of Truth

Nautobot

Inventory

Intent

---

## Layer 3

Platform Control Plane

Platform API

Intent Translation

Canonical Intent Model

Event Bus

Workflow Engine

Secrets

Policy

---

## Layer 4

Execution

Terraform

Ansible

Python

---

## Layer 5

Infrastructure

Cisco ACI

Cisco Nexus VXLAN EVPN

Azure

---

## Layer 6

Validation

pyATS

Catfish

Python

---

## Layer 7

Observability

Prometheus

Grafana

Loki

Alertmanager

---

## Layer 8

AI Reasoning

Architecture

Deployment

Validation

Documentation

Operations

Knowledge

---

## Layer 9

Knowledge

Obsidian

Vector Database

MCP

Engineering Documentation

---

# Engineering Flow

```text
Entry Point (Portal • CLI • Jira • Git • AI • REST)
   │
   ▼
Intent Translation (Platform API)
   │
   ▼
Canonical Intent  ─────────────► Event: IntentReceived
   │
   ▼
Nautobot (Source of Truth)  ───► Event: IntentStored
   │
   ▼
Canonical Model (NetAsCode)
   │
   ▼
Execution (Terraform / Ansible)  ──► Event: DeploymentStarted
   │
   ▼
Infrastructure  ────────────────────► Event: DeploymentCompleted
   │
   ▼
Validation  ─────────────────────────► Event: ValidationPassed / Failed
   │
   ▼
Observability  ──────────────────────► Continuous Telemetry
   │
   ▼
Knowledge Layer  ────────────────────► Engineering Memory Updated
   │
   ▼
AI Analysis  ────────────────────────► Recommendations
   │
   ▼
Improved Engineering Intent
```

Everything eventually feeds back into the Source of Truth.

---

# Many Entry Points, One Execution Path

A defining architectural principle of the platform is that the execution path is always the same, regardless of the entry point.

Requests may originate from:

- A self-service portal
- A CLI command
- A Jira ticket
- A Git commit
- An AI engineering assistant
- A REST API call
- A ServiceNow request
- A CI/CD pipeline

Regardless of origin, every request is:

1. Received by the Platform API
2. Authenticated and authorised
3. Translated into Canonical Intent
4. Validated against platform policy
5. Stored in the Source of Truth
6. Published as a platform event
7. Executed through the same Platform Control Plane
8. Validated independently
9. Captured in the Knowledge Layer

No consumer receives special treatment.

No consumer bypasses the Platform API.

This guarantees governance, auditability and operational consistency regardless of how a request originates.

---

# Technology Stack

| Capability | Technology |
|------------|------------|
| Source of Truth | Nautobot |
| IaC | Terraform |
| Configuration | Ansible |
| Data Model | Cisco NetAsCode |
| API | FastAPI |
| Workflow | n8n |
| Validation | pyATS |
| Intent Validation | Catfish |
| Programming | Python |
| Secrets | HashiCorp Vault / Azure Key Vault |
| Monitoring | Prometheus |
| Dashboards | Grafana |
| Logs | Loki |
| Notifications | Microsoft Teams |
| Documentation | Markdown |
| Knowledge | Obsidian |
| AI Memory | Vector Database |
| AI Connectivity | MCP |

---

# Repository Structure

```text
docs/
architecture/
automation/
terraform/
ansible/
python/
validation/
platform-api/
workflows/
knowledge/
```

Each directory is responsible for one engineering capability.

---

# Platform Capabilities

The platform currently supports:

✔ Infrastructure Provisioning

✔ Day-2 Configuration

✔ Continuous Validation

✔ Drift Detection

✔ Event-Driven Automation

✔ AI-Assisted Engineering

✔ Documentation as Code

✔ Knowledge Management

✔ Platform Observability

✔ Secure Automation

---

# Platform Philosophy

The platform separates reasoning from execution.

```text
             AI Reasons
                  │
                  ▼
        Platform Control Plane
                  │
                  ▼
     Deterministic Infrastructure
```

AI provides recommendations.

The platform performs execution.

---

# Closed-Loop Engineering

```text
Engineering Intent
        │
        ▼
Intent Translation  ──────────────► Canonical Intent
        │
        ▼
Source of Truth (Nautobot)
        │
        ▼
Execution  ──────────────────────► Event Published
        │
        ▼
Infrastructure
        │
        ▼
Validation  ─────────────────────► Event Published
        │
        ▼
Observability  ──────────────────► Continuous Telemetry
        │
        ▼
Knowledge Layer  ────────────────► Engineering Memory
        │
        ▼
AI Reasoning  ───────────────────► Recommendations
        │
        ▼
Engineering Improvements
        │
        └──────────────────────────────► Source of Truth
```

Intent → Model → Provision → Operate → Validate → Observe → Learn → Improve → Repeat.

Knowledge and Observability continuously improve future intent.

---

# Supporting Architecture Documents

| Document | Purpose |
|----------|---------|
| 00 | Project Charter |
| 01 | Current State |
| 02 | Target Architecture |
| 03 | Platform Principles |
| 04 | Technology Stack |
| 05 | Repository Structure |
| 06 | Deployment Workflow |
| 07 | Day-2 Operations |
| 08 | Continuous Validation |
| 09 | AI-Augmented Platform |
| 10 | Platform Security |
| 11 | Platform Observability |
| 12 | Platform Roadmap |
| 13 | Platform Lifecycle Management |

Each document provides additional detail for one aspect of the platform.

---

# Long-Term Vision

The long-term objective is to establish a reusable Network Platform Engineering framework capable of supporting multiple infrastructure domains through a unified architecture.

Future domains include:

- Cisco ACI
- Cisco Nexus VXLAN EVPN
- Azure Networking
- SD-WAN
- Firewalls
- Kubernetes Networking
- Hybrid Cloud

The architecture is intentionally modular so that new domains reuse existing platform capabilities rather than introducing separate automation stacks.

---

# Key Architectural Principles

> **Many entry points. One execution path.**

> **Engineering Intent lives in Nautobot.**

> **The Platform API translates every request into Canonical Intent.**

> **The Platform Control Plane executes changes.**

> **Validation proves correctness.**

> **Observability measures operational state.**

> **AI is a platform client, not an execution engine.**

> **Knowledge and Observability continuously improve future intent.**

Together, these capabilities form a governed, closed-loop Platform Engineering ecosystem for modern network infrastructure.