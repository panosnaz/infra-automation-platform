---

# Technology Selection Rationale

Technology choices within this platform are driven by architectural responsibilities rather than popularity.

Every selected technology has a clearly defined purpose and should only be replaced if another technology better fulfills the same architectural capability.

---

# Source of Truth

## Selected Technology

Nautobot

## Why Nautobot

Nautobot was selected because it provides:

- Extensible data model
- Strong network domain support
- IPAM
- Inventory
- Relationships
- Plugin ecosystem
- REST API
- GraphQL API
- Excellent automation integration

Unlike spreadsheets or static YAML repositories, Nautobot represents a living engineering database.

---

# Platform API

## Selected Technology

FastAPI

## Why FastAPI

FastAPI provides:

- High performance
- Automatic API documentation
- Strong typing
- Pydantic integration
- Easy testing
- Modern Python ecosystem

FastAPI serves as the abstraction layer between engineering consumers and implementation services.

---

# Workflow Orchestration

## Selected Technology

n8n

## Why n8n

n8n is responsible for workflow orchestration rather than infrastructure deployment.

It enables:

- Human approvals
- Notifications
- ServiceNow integration
- Microsoft Teams integration
- Scheduled workflows
- Event-driven automation

Infrastructure logic remains outside n8n.

---

# Desired State Management

## Selected Technology

Terraform

## Why Terraform

Terraform provides:

- Declarative infrastructure
- State management
- Planning capability
- Drift awareness
- Provider ecosystem

Terraform owns desired infrastructure state.

No other platform component should duplicate this responsibility.

---

# Operational Automation

## Selected Technology

Ansible

## Why Ansible

Ansible excels at:

- Agentless execution
- Operational tasks
- Data collection
- Reporting
- Configuration backups
- Health checks

Ansible intentionally does not own infrastructure provisioning.

---

# Validation

## Selected Technologies

pyATS

Catfish

Custom Python

## Why

Validation should remain independent of deployment.

Using independent validation increases confidence that deployments actually achieved their intended outcomes.

---

# Secrets

## Selected Technology

HashiCorp Vault

## Why

Centralized credential management

Secret rotation

Audit logging

Dynamic credentials

Least privilege

---

# Policy

## Selected Technology

Open Policy Agent

## Why

Engineering standards should exist independently of deployment tools.

Policy should determine whether infrastructure is permitted before deployment occurs.

---

# Version Control

## Selected Technology

Git

## Why

Every infrastructure change should be version controlled.

Git provides:

- Audit history
- Rollback
- Pull Requests
- Peer review
- CI/CD integration

---

# AI Layer

## Selected Technologies

OpenAI

Claude

LangGraph

MCP Servers

## Why

AI assists engineers rather than replacing engineering workflows.

AI should consume platform services instead of interacting directly with infrastructure.

---

# Scalability

The platform is designed to scale in four independent dimensions.

---

## Infrastructure Scale

Additional infrastructure domains can be added without redesign.

Examples include:

Cisco ACI

Cisco Nexus VXLAN EVPN

Azure Networking

SD-WAN

Firewalls

Kubernetes Networking

Cloud Networking

---

## Team Scale

Multiple engineering teams should collaborate through the same platform.

Examples include:

Network Engineering

Cloud Engineering

Platform Engineering

Security Engineering

Operations

---

## Automation Scale

Automation workflows should remain modular.

Adding a new workflow should not require redesigning existing workflows.

---

## Technology Scale

Individual technologies may be replaced while preserving architectural responsibilities.

For example:

Terraform may eventually be replaced.

FastAPI may eventually be replaced.

n8n may eventually be replaced.

The architecture should remain valid.

---

# Architectural Trade-offs

Every architecture involves compromises.

The following trade-offs are accepted.

---

## Additional Components

The platform contains more components than a simple automation repository.

This increases operational complexity.

However it significantly improves maintainability, scalability and governance.

---

## Initial Learning Curve

Engineers must understand:

Nautobot

Terraform

Ansible

Git

CI/CD

Validation

Platform APIs

This learning investment enables long-term operational simplicity.

---

## Strong Governance

The platform intentionally discourages manual infrastructure changes.

This increases deployment consistency at the cost of reducing direct administrative flexibility.

---

# Architectural Guardrails

The following rules should not be violated.

---

## Rule 1

Nautobot remains the only Source of Truth.

---

## Rule 2

Terraform owns desired infrastructure state.

---

## Rule 3

Ansible owns operational automation.

---

## Rule 4

Validation remains independent.

---

## Rule 5

Infrastructure APIs are never exposed directly to users.

---

## Rule 6

Secrets never exist inside Git repositories.

---

## Rule 7

Every deployment passes through Git.

---

## Rule 8

Every deployment is validated.

---

## Rule 9

Every deployment is observable.

---

## Rule 10

AI agents interact only through the Platform API.

---

# Future Evolution

The architecture intentionally anticipates future capabilities.

Potential future additions include:

- Self-Service Portal
- Service Catalog
- ChatOps
- Event Streaming
- Digital Twin
- Simulation
- Change Risk Analysis
- AI Change Review
- Knowledge Graph
- Automated Documentation
- Capacity Planning
- Compliance Dashboards

These capabilities should integrate into the Platform Control Plane without redesigning existing services.

---

# Architecture Summary

The Network Platform Engineering Platform is designed as an engineering control plane rather than an automation framework.

Infrastructure becomes one managed domain within the platform rather than the central focus.

The architecture emphasizes:

- Intent over configuration
- Platform over scripts
- Governance over manual execution
- Validation over assumption
- APIs over direct integration
- Engineering capabilities over individual technologies

These principles ensure that the platform can evolve to support new technologies, new engineering teams and new operational requirements while maintaining a consistent operating model.

This document serves as the architectural baseline for all implementation work and should be reviewed before introducing new platform capabilities or modifying existing responsibilities.