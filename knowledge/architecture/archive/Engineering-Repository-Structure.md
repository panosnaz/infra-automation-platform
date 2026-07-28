---
type: architecture
domain: platform
status: historical
tags: [repo-structure]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 05 – Engineering Repository Structure

**Project:** Network Platform Engineering Platform

**Document Type:** Engineering Standards

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

> **Superseded:** The top-level repository layout in this document (`network-platform/` with `architecture/`, `adr/`, `nautobot/`, `terraform/`, `ansible/`, etc. as top-level directories) does not reflect the actual repository. [`docs/folder structure`](../folder%20structure) is the authoritative, kept-in-sync layout reference. This document's directory-responsibility descriptions (what each capability owns) remain a useful reference; only the top-level tree diagram below is superseded.

---

# Purpose

This document defines the standard repository structure for the Network Platform Engineering Platform.

The repository is designed to support:

* Human engineers
* AI coding agents
* CI/CD pipelines
* Documentation generation
* Testing
* Infrastructure deployment
* Operational automation
* Validation
* Long-term maintainability

A consistent repository structure reduces cognitive load, improves discoverability and enables AI assistants to navigate the project efficiently.

---

# Design Principles

The repository follows these principles:

* Separate architecture from implementation.
* Separate infrastructure from operations.
* Separate reusable libraries from executable workflows.
* Treat documentation as code.
* Organize by engineering capability rather than technology.
* Keep components loosely coupled.
* Ensure every directory has a single responsibility.

---

# High-Level Repository Layout

```text
network-platform/

├── architecture/
│
├── adr/
│
├── docs/
│
├── diagrams/
│
├── nautobot/
│
├── platform-api/
│
├── workflows/
│
├── terraform/
│
├── ansible/
│
├── validation/
│
├── observability/
│
├── knowledge/
│
├── agents/
│
├── scripts/
│
├── tests/
│
├── .github/
│
├── docker/
│
├── examples/
│
├── tools/
│
└── README.md
```

---

# Directory Responsibilities

## architecture/

Contains all architecture documentation.

Examples:

* Project Charter
* Current State
* Target Architecture
* Technology Architecture
* Security
* Roadmap

This directory contains design decisions, not implementation.

---

## adr/

Architecture Decision Records.

Every significant architectural decision must have an ADR.

Examples:

ADR-001-Nautobot-Source-of-Truth.md

ADR-002-Terraform-Desired-State.md

ADR-003-Ansible-Day2.md

ADR-004-Platform-API.md

---

## docs/

Operational documentation.

Examples:

Installation guides

Developer guides

Runbooks

Troubleshooting

User documentation

---

## diagrams/

Draw.io diagrams

Architecture diagrams

Sequence diagrams

Workflow diagrams

Network topology diagrams

Only source diagram files should be stored here.

Generated images should be exported automatically.

---

## nautobot/

Nautobot-specific code.

Examples:

Plugins

Jobs

Custom Models

API Extensions

Initial Data

Migrations

---

## platform-api/

FastAPI implementation.

Suggested structure:

```text
platform-api/

api/

routers/

services/

models/

schemas/

middleware/

clients/

tests/
```

This service acts as the abstraction layer between consumers and platform components.

---

## workflows/

Workflow orchestration.

Contains:

n8n workflows

Workflow definitions

Approval flows

Notification flows

ServiceNow integrations

No infrastructure logic belongs here.

---

## terraform/

Infrastructure provisioning.

Organized by provider.

Example:

```text
terraform/

providers/

aci/

azure/

modules/

environments/

shared/

examples/
```

Terraform owns desired state.

---

## ansible/

Operational automation.

Suggested layout:

```text
ansible/

playbooks/

roles/

inventories/

collections/

plugins/

group_vars/

host_vars/
```

Typical playbooks:

Health checks

Backups

Operational changes

Data collection

Maintenance

---

## validation/

Independent validation platform.

Example:

```text
validation/

pyats/

catfish/

python/

reports/

testcases/

golden-config/
```

Validation remains independent from deployment.

---

## observability/

Monitoring platform configuration.

Examples:

Prometheus

Grafana

Loki

Dashboards

Alerts

---

## knowledge/

Engineering knowledge base.

Contains:

Architecture notes

Operational knowledge

Standards

Reference material

Research

This directory is intended to synchronize with Obsidian.

---

## agents/

AI agent definitions.

Examples:

Architecture Agent

Terraform Agent

Ansible Agent

Validation Agent

Documentation Agent

Repository Agent

Each agent should have:

Purpose

Responsibilities

Inputs

Outputs

Constraints

Tools

---

## scripts/

Utility scripts.

Examples:

Repository maintenance

Bootstrap

Data migration

Reporting

Small utilities

Business logic should not reside here.

---

## tests/

Platform tests.

Examples:

Unit tests

Integration tests

API tests

End-to-end tests

Validation tests

---

## docker/

Container definitions.

Examples:

Dockerfiles

Docker Compose

Development environments

---

## tools/

Reusable helper utilities.

Examples:

CSV parsers

Intent generators

Code generators

Migration tools

Shared libraries

---

# Documentation Standards

Every directory should include a README.md describing:

* Purpose
* Contents
* Ownership
* Dependencies
* Usage
* Related documentation

---

# Naming Conventions

Directories:

lowercase-with-hyphens

Examples:

platform-api

validation

knowledge

Files:

Descriptive names

Examples:

tenant_generator.py

validate_contracts.py

deploy_aci.yml

No abbreviations unless universally understood.

---

# Branch Strategy

Recommended branches:

main

develop

feature/*

bugfix/*

hotfix/*

release/*

All production changes should be merged through Pull Requests.

---

# Repository Governance

Every Pull Request should include:

* Description
* Linked issue
* Architecture impact
* Testing evidence
* Documentation updates

Changes affecting architecture must reference an ADR when appropriate.

---

# AI-Friendly Repository Practices

The repository is intentionally organized to improve AI-assisted development.

Guidelines include:

* Keep files focused on a single responsibility.
* Prefer many small modules over large monolithic files.
* Use descriptive names.
* Maintain consistent folder structures.
* Document public interfaces.
* Avoid hidden dependencies.
* Include examples for reusable components.

These practices improve retrieval accuracy for AI agents and reduce implementation ambiguity.

---

# Future Expansion

The repository is designed to accommodate future capabilities without restructuring.

Potential additions include:

* Kubernetes support
* Additional cloud providers
* Service Catalog
* Internal Developer Portal
* Event streaming
* Additional infrastructure adapters
* New validation frameworks

New capabilities should integrate into the existing directory hierarchy rather than introducing parallel structures.

---

# Summary

The repository structure reflects the architecture of the platform itself.

Each directory corresponds to a distinct engineering capability with clearly defined ownership and responsibilities.

Maintaining this structure ensures that the platform remains understandable, scalable and maintainable for both human engineers and AI-assisted development.
