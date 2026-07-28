---
type: architecture
domain: platform
status: active
tags: [technology]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 04 – Technology Architecture

**Project:** Network Platform Engineering Platform

**Document Type:** Reference Technology Architecture

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

---

# Purpose

This document defines the reference technology architecture for the Network Platform Engineering Platform.

The purpose of this document is not merely to list technologies, but to explain:

* Why each technology was selected.
* Which architectural capability it provides.
* What alternatives were considered.
* What responsibilities it owns.
* What responsibilities it explicitly does not own.
* Under which conditions it may be replaced.

Technology selections should always support the architectural principles defined in **03-Architecture-Principles.md**.

---

# Technology Selection Philosophy

Technology decisions are guided by the following principles:

* Choose mature, well-supported technologies.
* Prefer open standards.
* Minimize vendor lock-in.
* Prefer API-driven platforms.
* Separate architectural capability from implementation technology.
* Optimize for maintainability over novelty.
* Prefer technologies with strong ecosystems and community support.

---

# Platform Capability Matrix

| Capability             | Selected Technology | Alternatives                             |
| ---------------------- | ------------------- | ---------------------------------------- |
| Source of Truth        | Nautobot            | NetBox, Custom CMDB                      |
| Platform API           | FastAPI             | Flask, Django, Go                        |
| Workflow Orchestration | n8n                 | GitHub Actions, Apache Airflow, Temporal |
| Desired State          | Terraform           | Pulumi, OpenTofu                         |
| Operational Automation | Ansible             | SaltStack, Python                        |
| Validation             | pyATS + Catfish     | Nornir, Custom Python                    |
| Secrets                | HashiCorp Vault     | Azure Key Vault, CyberArk                |
| Policy                 | Open Policy Agent   | Sentinel, Custom Python                  |
| Version Control        | Git                 | None                                     |
| CI/CD                  | GitHub Actions      | GitLab CI, Azure DevOps, Jenkins         |
| Monitoring             | Prometheus          | Zabbix                                   |
| Dashboards             | Grafana             | Kibana                                   |
| Logging                | Loki                | ELK                                      |
| Knowledge Base         | Obsidian + Git      | MkDocs Only                              |
| Vector Memory          | Qdrant              | ChromaDB                                 |
| AI Orchestration       | LangGraph           | CrewAI, AutoGen                          |
| LLM Providers          | OpenAI, Claude      | Self-hosted models                       |

---

# Source of Truth

## Selected Technology

Nautobot

### Architectural Capability

Network Intent Management

### Responsibilities

* Inventory
* IPAM
* Relationships
* Desired Network Intent
* Network Metadata

### Why Selected

Nautobot provides an extensible data model specifically designed for network engineering.

Its plugin architecture allows future expansion without modifying the core platform.

### Alternatives Considered

NetBox

Custom Database

Spreadsheet-based inventory

### Decision

Nautobot provides the strongest foundation for a long-lived engineering platform.

---

# Platform API

## Selected Technology

FastAPI

### Capability

Platform Integration Layer

### Why Selected

* Modern Python
* Automatic OpenAPI
* Async support
* Excellent testing
* Strong typing
* Pydantic integration

### Alternatives

Flask

Django

Go

Node.js

### Decision

FastAPI offers the best balance between simplicity and scalability.

---

# Workflow Orchestration

## Selected Technology

n8n

### Capability

Workflow Coordination

### Responsibilities

* Human approval workflows
* Notifications
* ServiceNow integration
* Teams integration
* Event processing
* Scheduling

### Does Not Own

Infrastructure deployment

Desired state

Validation

### Decision

n8n orchestrates workflows rather than implementing infrastructure logic.

---

# Desired State Management

## Selected Technology

Terraform

### Capability

Infrastructure Provisioning

### Responsibilities

* Cisco ACI provisioning
* Azure networking
* Future providers

### Alternatives

Pulumi

OpenTofu

CloudFormation

### Decision

Terraform remains the industry standard for declarative infrastructure management.

---

# Operational Automation

## Selected Technology

Ansible

### Capability

Operational Automation

### Responsibilities

* Health checks
* Reporting
* Data collection
* Operational changes
* Configuration backups
* Maintenance

### Alternatives

SaltStack

Python

Nornir

### Decision

Ansible excels at Day-2 operations and complements Terraform without overlapping responsibilities.

---

# Validation Platform

## Selected Technologies

pyATS

Catfish

Python

### Capability

Independent Validation

### Responsibilities

* Compliance
* Drift detection
* Connectivity testing
* Configuration validation
* Operational verification

### Decision

Validation remains independent of deployment to provide objective verification.

---

# Secrets Management

## Selected Technology

HashiCorp Vault

### Capability

Centralized Secret Management

### Responsibilities

* Credentials
* Certificates
* Tokens
* Secret rotation
* Audit

### Alternatives

Azure Key Vault

CyberArk

AWS Secrets Manager

---

# Policy Engine

## Selected Technology

Open Policy Agent

### Capability

Policy as Code

### Responsibilities

* Naming standards
* Security rules
* Deployment constraints
* Compliance

### Decision

Policies should remain independent of infrastructure code.

---

# Observability

## Monitoring

Prometheus

## Dashboards

Grafana

## Logging

Loki

### Capability

Platform Observability

### Responsibilities

* Metrics
* Dashboards
* Platform health
* Workflow metrics
* API metrics

---

# Knowledge Platform

## Selected Technologies

Obsidian

Git

MkDocs

### Capability

Engineering Knowledge Management

### Responsibilities

* Architecture documentation
* ADRs
* Standards
* Runbooks
* Operational knowledge

Knowledge is treated as a platform asset rather than project documentation.

---

# AI Platform

## LLM Providers

* OpenAI
* Claude

## Agent Framework

LangGraph

## Memory

Qdrant

## Protocol

Model Context Protocol (MCP)

### Capability

Engineering Assistance

### Responsibilities

* Architecture guidance
* Documentation assistance
* Code generation
* Knowledge retrieval
* Change planning

AI interacts exclusively through the Platform API.

---

# Development Environment

## IDE

Visual Studio Code

## Container Platform

Docker Desktop

## Language

Python

## Version Control

Git

## Testing

pytest

## Formatting

Black

## Linting

Ruff

## Type Checking

mypy

---

# Technology Lifecycle

Technologies are classified according to their maturity within the platform.

| Status       | Description                    |
| ------------ | ------------------------------ |
| Core         | Fundamental platform component |
| Strategic    | Planned long-term investment   |
| Supporting   | Auxiliary capability           |
| Experimental | Under evaluation               |

Examples:

| Technology | Status       |
| ---------- | ------------ |
| Nautobot   | Core         |
| Terraform  | Core         |
| FastAPI    | Core         |
| Ansible    | Core         |
| Vault      | Strategic    |
| n8n        | Strategic    |
| LangGraph  | Experimental |
| AI Agents  | Experimental |

---

# Future Technology Evolution

The platform anticipates future changes without requiring architectural redesign.

Potential future additions include:

* Kubernetes deployment
* Event streaming with Kafka
* Digital Twin integration
* Simulation platforms
* Self-service portal
* Internal Developer Portal
* Additional cloud providers

Technology evolution should preserve architectural capabilities and responsibilities.

---

# Summary

The Network Platform Engineering Platform is designed around architectural capabilities rather than individual products.

Technology selections should evolve as the ecosystem changes, while the underlying architectural principles remain stable.

This approach ensures long-term maintainability, portability and adaptability without compromising the overall platform design.
