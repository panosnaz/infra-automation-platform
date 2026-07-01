## Platform Component Architecture

This chapter describes the major components that compose the Network Platform Engineering Platform.

Each component has a clearly defined responsibility.

A fundamental architectural principle of this platform is that **every capability has a single owner**.

No component should duplicate responsibilities owned by another component.

---

# Platform Overview

The platform consists of two major architectural domains.

```text
═══════════════════════════════════════════════════════════════

                PLATFORM CONTROL PLANE

═══════════════════════════════════════════════════════════════

Users

↓

Platform API (FastAPI)

↓

Workflow Orchestration (n8n)

↓

Nautobot (Source of Truth)

↓

Intent Generation

↓

Version Control

↓

Policy Validation

↓

CI/CD

↓

Deployment Engines

↓

Validation

↓

Observability

↓

Closed Loop Feedback

═══════════════════════════════════════════════════════════════

             MANAGED INFRASTRUCTURE

═══════════════════════════════════════════════════════════════

Cisco ACI

Cisco Nexus VXLAN EVPN

Azure Networking

Future Infrastructure Domains
```

---

# Platform Control Plane

The Platform Control Plane represents the engineering platform itself.

It is responsible for translating engineering intent into infrastructure deployment.

Infrastructure devices are not considered part of the Platform Control Plane.

The Platform Control Plane is composed of independent services that collaborate through APIs.

---

# Source of Truth

## Technology

Nautobot

---

## Purpose

Nautobot is the authoritative Source of Truth for the entire platform.

It represents the desired business intent rather than the deployed infrastructure.

Every infrastructure deployment originates from Nautobot.

---

## Responsibilities

Nautobot owns:

* Tenants
* VRFs
* Bridge Domains
* EPGs
* Contracts
* L3Outs
* Application Models
* Device Inventory
* Interface Inventory
* IPAM
* Prefixes
* VLAN Pools
* Route Targets
* Relationships between objects

---

## Does NOT own

Nautobot does NOT:

* Deploy infrastructure
* Execute Terraform
* Execute Ansible
* Perform validation
* Store secrets
* Enforce policies
* Monitor infrastructure

---

## Interfaces

Consumes:

* Platform API

Produces:

* Intent Data

---

# Platform API

## Technology

FastAPI

---

## Purpose

The Platform API acts as the single integration point for every external consumer.

No external system should communicate directly with Terraform, Git, Ansible or infrastructure.

---

## Responsibilities

The Platform API:

* Receives requests
* Validates requests
* Queries Nautobot
* Invokes workflows
* Returns status
* Aggregates platform information

---

## Consumers

* Engineers
* Self-Service Portal
* AI Agents
* ServiceNow
* ChatOps
* Automation

---

## Does NOT own

* Infrastructure deployment
* Secrets
* Validation
* Policy
* Desired state

---

## Example APIs

POST /tenant

POST /application

POST /deploy

POST /validate

GET /status

GET /inventory

---

# Workflow Orchestration

## Technology

n8n

---

## Purpose

Coordinates workflows between platform services.

n8n never performs infrastructure deployment itself.

---

## Responsibilities

* Human approvals
* Notifications
* ServiceNow integration
* Teams notifications
* Git operations
* Scheduling
* Workflow coordination

---

## Does NOT own

* Desired state
* Infrastructure configuration
* Validation
* Infrastructure inventory

---

# Intent Generation Layer

## Technologies

Python

Pydantic

Jinja2

Cisco NetAsCode (optional)

---

## Purpose

Translate business intent into deployment artifacts.

Intent Generation converts Nautobot data into machine-consumable configuration.

---

## Outputs

Terraform

YAML

JSON

Ansible Variables

Documentation

---

## Design Principle

Infrastructure models should be generated rather than manually written.

---

# Version Control

## Technologies

GitHub

GitLab

---

## Purpose

Maintain complete history of engineering intent.

---

## Responsibilities

* Version history
* Pull Requests
* Reviews
* Rollback
* Audit Trail

---

# Policy Engine

## Technology

Open Policy Agent

---

## Purpose

Ensure every deployment complies with engineering standards.

---

## Responsibilities

Validate:

* Naming conventions
* VLAN ranges
* VRF placement
* Security standards
* Deployment constraints

---

## Does NOT own

Infrastructure deployment.

---

# Secrets Management

## Technologies

HashiCorp Vault

Azure Key Vault

CyberArk

---

## Purpose

Provide centralized credential management.

---

## Responsibilities

Store:

* APIC credentials
* Cloud credentials
* Terraform secrets
* API tokens
* Certificates

---

## Design Principle

No credentials exist inside Git.

---

# CI/CD Platform

## Technologies

GitHub Actions

GitLab CI

Azure DevOps

Jenkins

---

## Responsibilities

Generate

Validate

Plan

Approve

Deploy

Verify

---

## Pipeline

```
Intent

↓

Generate

↓

Policy Validation

↓

Terraform Plan

↓

Approval

↓

Terraform Apply

↓

Validation

↓

Success
```

---

# Deployment Engine

## Technology

Terraform

---

## Purpose

Terraform owns desired infrastructure state.

Terraform is the only component responsible for provisioning infrastructure.

---

## Responsibilities

Deploy:

Cisco ACI

Azure Networking

Future Providers

---

## Does NOT own

Operations

Monitoring

Validation

Secrets

Workflow

---

## Design Principle

Infrastructure changes should originate from Git.

Manual infrastructure changes should be minimized.

---

# Operational Automation

## Technology

Ansible

---

## Purpose

Execute operational tasks after infrastructure exists.

---

## Responsibilities

Health Checks

Configuration Backups

Reporting

Data Collection

Maintenance

Operational Changes

Fault Collection

---

## Does NOT own

Desired infrastructure state.

Provisioning.

Platform inventory.

---

# Validation Platform

## Technologies

pyATS

Catfish

Python

---

## Purpose

Independently verify platform correctness.

Validation must remain independent from deployment.

---

## Responsibilities

Pre-deployment validation

Post-deployment validation

Compliance

Intent verification

Configuration verification

Operational verification

---

# Drift Detection

## Purpose

Detect differences between:

Desired State

Actual Infrastructure

---

## Responsibilities

Detect:

Manual APIC changes

Configuration drift

Policy violations

Missing objects

Unexpected configuration

---

## Outputs

Compliance Reports

Drift Reports

Platform Events

---

# Observability

## Technologies

Prometheus

Grafana

Loki

ELK

---

## Responsibilities

Collect:

Platform metrics

Deployment metrics

API latency

Terraform statistics

Validation results

Workflow metrics

Infrastructure health

---

# AI & Engineering Assistant Layer

## Technologies

OpenAI

Claude

LangGraph

MCP Servers

---

## Purpose

Provide engineering assistance without direct infrastructure access.

---

## Responsibilities

Architecture guidance

Change planning

Documentation generation

Code generation

Root cause analysis

Knowledge retrieval

Platform assistance

---

## Design Principle

AI Agents never communicate directly with infrastructure.

Every action flows through the Platform API.

---

# Managed Infrastructure

The platform intentionally separates itself from managed infrastructure.

Current supported domains:

* Cisco ACI
* Cisco Nexus VXLAN EVPN
* Azure Networking

Future infrastructure domains should integrate through deployment adapters without modifying the platform architecture.

---

# Closed-Loop Feedback

Every deployment generates operational feedback.

Validation, observability and drift detection continuously compare actual infrastructure with intended infrastructure.

Detected deviations are reported back into the Platform Control Plane.

This enables continuous reconciliation between engineering intent and operational reality.

Closed-loop feedback is a foundational capability of the platform rather than an optional feature.
