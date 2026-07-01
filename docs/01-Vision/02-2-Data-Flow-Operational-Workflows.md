---

# Data Flow & Operational Workflows

This chapter describes how information moves through the platform from engineering intent to deployed infrastructure and back again through continuous validation and observability.

A key architectural principle is that infrastructure is **not** manipulated directly by users or AI agents.

Every change follows controlled workflows through the Platform Control Plane.

---

# Engineering Workflow Overview

The platform implements a closed-loop engineering lifecycle.

```text
Business Intent
        │
        ▼
Nautobot (Source of Truth)
        │
        ▼
Platform API
        │
        ▼
Workflow Orchestrator (n8n)
        │
        ▼
Intent Generation
        │
        ▼
Git Repository
        │
        ▼
Policy Validation (OPA)
        │
        ▼
CI/CD Pipeline
        │
        ▼
Terraform Plan
        │
        ▼
Approval
        │
        ▼
Terraform Apply
        │
        ▼
Cisco ACI
        │
        ▼
Validation
        │
        ▼
Observability
        │
        ▼
Closed Loop Feedback
        │
        ▼
Nautobot
```

This workflow ensures that every infrastructure change is version-controlled, validated, observable and auditable.

---

# Day-0 / Day-1 Provisioning Workflow

Day-0 and Day-1 activities are responsible for provisioning infrastructure that does not yet exist.

Typical examples include:

- New Tenant
- New VRF
- New Bridge Domain
- New EPG
- New Contract
- New L3Out
- New Application Profile
- Azure Network Infrastructure
- VXLAN EVPN Fabric Components

## Workflow

1. Engineer updates the desired intent in Nautobot.
2. Nautobot becomes the authoritative representation of the desired configuration.
3. The Platform API retrieves the requested objects.
4. n8n orchestrates the deployment workflow.
5. Intent Generation creates deployment artifacts.
6. Generated artifacts are committed into Git.
7. CI/CD performs:
   - syntax validation
   - policy validation
   - Terraform plan
8. Engineers review the Terraform plan.
9. Approved changes are applied.
10. Validation confirms successful deployment.
11. Platform status is updated.
12. Observability begins monitoring the deployed infrastructure.

No infrastructure deployment occurs outside this workflow.

---

# Day-2 Operational Workflow

Day-2 activities operate on existing infrastructure.

Examples include:

- Operational reporting
- Health checks
- Configuration backups
- BFD configuration
- Firmware validation
- Inventory collection
- Fault analysis
- Compliance reporting
- Scheduled maintenance
- Non-destructive configuration adjustments

## Workflow

```text
Scheduled Event
      │
      ▼
Ansible
      │
      ▼
Infrastructure
      │
      ▼
Results
      │
      ▼
Platform API
      │
      ▼
Nautobot
```

Terraform is intentionally not involved in routine operational tasks.

---

# Change Management Workflow

Every infrastructure modification follows a controlled lifecycle.

```text
Request

↓

Nautobot

↓

Platform API

↓

Git Commit

↓

Pull Request

↓

Peer Review

↓

Policy Validation

↓

Terraform Plan

↓

Approval

↓

Deployment

↓

Validation

↓

Production
```

Every deployment remains traceable from request to implementation.

---

# Validation Workflow

Validation exists independently of deployment.

A successful deployment does not automatically indicate a correct deployment.

Validation verifies:

- Infrastructure state
- Connectivity
- Routing
- Contracts
- Endpoint reachability
- Configuration compliance
- Operational health

## Validation Pipeline

```text
Terraform Apply

↓

pyATS

↓

Catfish

↓

Custom Validation

↓

Compliance Report

↓

Platform API

↓

Nautobot
```

---

# Drift Detection Workflow

The platform continuously compares deployed infrastructure with intended infrastructure.

```text
Infrastructure

↓

Configuration Collection

↓

State Comparison

↓

Drift Detection

↓

Platform API

↓

Nautobot

↓

Alert
```

Examples of drift include:

- Manual APIC changes
- Missing objects
- Unexpected policies
- Incorrect contracts
- Modified Bridge Domains

---

# Closed-Loop Engineering

The platform is intentionally designed as a feedback system rather than a deployment engine.

Every deployment generates operational feedback.

Every validation generates compliance data.

Every monitoring event contributes operational insight.

The platform continuously reconciles:

Desired State

versus

Actual State

This feedback enables engineers to identify inconsistencies before they become operational incidents.

---

# AI-Assisted Workflow

Artificial Intelligence is treated as an engineering assistant rather than an infrastructure administrator.

AI Agents never communicate directly with Cisco ACI, Terraform or Ansible.

Instead they consume the Platform API.

## AI Workflow

```text
Engineer

↓

AI Assistant

↓

Platform API

↓

Nautobot

↓

Platform Services

↓

Response
```

Examples include:

- Architecture assistance
- Deployment planning
- Documentation generation
- Configuration explanation
- Impact analysis
- Root cause investigation
- Knowledge retrieval

Infrastructure execution always remains under platform governance.

---

# Event-Driven Automation

Not every platform activity should require human intervention.

The platform supports event-driven automation using n8n.

Typical events include:

- New tenant approved
- Git merge completed
- Terraform deployment completed
- Validation failure
- Drift detected
- Platform health degradation
- Compliance violation

These events trigger predefined workflows such as:

- Notifications
- ServiceNow updates
- Teams messages
- Validation jobs
- Documentation updates

---

# Failure Handling

The platform assumes failures will occur.

Each workflow must provide clear failure handling.

Examples include:

- Failed Terraform plan
- Policy validation failure
- pyATS validation failure
- Drift detection alert
- Platform API unavailable

Failures should result in:

- Workflow termination
- Clear error reporting
- Audit logging
- Notification
- No partial infrastructure changes

---

# Platform Interaction Matrix

| Component | Primary Interaction |
|------------|---------------------|
| Engineers | Platform API |
| AI Agents | Platform API |
| Platform API | Nautobot |
| n8n | Platform API |
| Terraform | Git |
| CI/CD | Git |
| Validation | Infrastructure |
| Observability | Infrastructure |
| Drift Detection | Infrastructure |
| Nautobot | Platform Database |

Direct communication between unrelated components should be avoided wherever possible.

---

# Design Philosophy

Every workflow in the platform follows the same engineering pattern:

**Intent → Governance → Deployment → Validation → Observation → Feedback**

This pattern is independent of the underlying infrastructure technology.

Whether the managed domain is Cisco ACI, Cisco Nexus VXLAN EVPN or Azure Networking, the engineering lifecycle remains identical.

This consistency enables the platform to evolve without redesign as new infrastructure domains are introduced.