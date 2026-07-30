---
type: runbook
domain: cisco_aci
status: active
tags: [ansible, day2]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 07 – Day-2 Operations Strategy

**Project:** Network Platform Engineering Platform

**Document Type:** Operational Strategy

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

> **Update (2026-07-29):** the "Workflow Orchestration: n8n" and "Platform API" references below describe the original Platform v1 model. Day-2 operations (`ansible-playbook verify-tenants.yml`/`day2-epg.yml`) are proven and unchanged; per [ADR-016](../adr/ADR-016-Platform-v2-Replacement-Architecture.md), their *trigger* is now a GitLab CI `ansible_configure` stage (see [`Execution-Framework.md`](../architecture/Execution-Framework.md)), not the Platform API/n8n.

---

# Purpose

This document defines the operational strategy for Day-2 activities within the Network Platform Engineering Platform.

The objective is to establish a clear separation between infrastructure provisioning and ongoing operational management.

The platform distinguishes between:

* **Day-0 / Day-1** – Provisioning infrastructure and desired state
* **Day-2** – Operating, maintaining, validating and optimizing existing infrastructure

This separation improves maintainability, governance and operational flexibility.

---

# Day-2 Philosophy

Infrastructure provisioning and infrastructure operations have different objectives.

Provisioning focuses on creating infrastructure that matches the desired intent.

Operations focus on maintaining infrastructure that already exists.

Day-2 activities should be:

* Repeatable
* Idempotent where practical
* Non-destructive
* Auditable
* Observable
* Independently testable

Operational automation should never replace infrastructure provisioning.

---

# Architectural Responsibilities

| Capability                   | Owner                |
| ---------------------------- | -------------------- |
| Desired Infrastructure State | Terraform            |
| Operational Automation       | Ansible              |
| Source of Truth              | Nautobot             |
| Workflow Orchestration       | n8n                  |
| Validation                   | pyATS / Catfish      |
| Observability                | Prometheus / Grafana |
| Policy Enforcement           | OPA                  |
| Secrets Management           | Vault                |

Each capability owns a distinct responsibility.

Responsibilities should not overlap.

---

# Categories of Day-2 Operations

The platform groups Day-2 activities into several operational domains.

---

## Operational Configuration

Examples include:

* BFD enablement
* Interface adjustments
* NTP updates
* SNMP configuration
* Syslog configuration
* DNS updates
* AAA configuration
* Banner updates

These activities modify operational behaviour without redesigning infrastructure.

---

## Health Checks

Routine health verification includes:

* Controller availability
* Leaf and Spine health
* Interface status
* Fabric faults
* Resource utilisation
* CPU
* Memory
* Disk usage

Health checks should execute on a scheduled basis.

---

## Validation

Operational validation confirms that the deployed infrastructure behaves as intended.

Examples:

* Endpoint reachability
* Contract enforcement
* Routing verification
* BGP neighbour status
* VXLAN overlay health
* L3Out validation
* Azure connectivity

Validation remains independent of deployment workflows.

---

## Drift Detection

The platform continuously compares:

Desired State

versus

Operational State

Examples include:

* Manual APIC modifications
* Missing objects
* Incorrect policies
* Unexpected contracts
* VLAN inconsistencies

Detected drift should trigger notifications and reconciliation workflows.

---

## Inventory Collection

The platform continuously collects operational metadata.

Examples include:

* Software versions
* Hardware inventory
* Serial numbers
* Licenses
* Fabric topology
* Module inventory

Inventory supports lifecycle management and reporting.

---

## Compliance

Compliance verifies adherence to engineering standards.

Examples:

* Naming conventions
* VLAN allocation
* VRF assignment
* Security policy
* Firmware baseline
* Configuration standards

Compliance reporting should be automated.

---

## Backup and Recovery

Operational backups include:

* Controller configuration
* Running configuration
* Policy exports
* Tenant exports
* Terraform state backups
* Documentation snapshots

Backups should be scheduled and version controlled where appropriate.

---

## Reporting

The platform generates operational reports including:

* Platform health
* Validation results
* Compliance status
* Drift reports
* Capacity utilisation
* Change history
* Firmware inventory

Reports should be accessible through dashboards and APIs.

---

# Operational Workflow

The standard Day-2 workflow is:

```text
Scheduled Event / Platform Event
                │
                ▼
        Workflow Orchestrator
                │
                ▼
     Operational Automation
                │
                ▼
      Managed Infrastructure
                │
                ▼
 Operational Data Collection
                │
                ▼
 Validation Platform
                │
                ▼
 Platform API
                │
                ▼
     Nautobot / Dashboards
```

---

# Trigger Types

Day-2 workflows may be initiated by several trigger mechanisms.

## Scheduled

Examples:

* Daily health checks
* Weekly compliance reports
* Monthly inventory collection
* Nightly backups

---

## Event-Driven

Examples:

* Validation failure
* Drift detected
* New deployment completed
* Platform alert
* ServiceNow request
* Git merge

---

## Manual

Examples:

* Maintenance activities
* Emergency diagnostics
* Ad-hoc reporting
* Root cause analysis

Manual execution should remain fully auditable.

---

# Operational Principles

Day-2 automation should follow these principles.

## Principle 1

Operations must not redefine infrastructure intent.

---

## Principle 2

Operational changes should preserve the Source of Truth.

---

## Principle 3

Infrastructure configuration should remain reproducible.

---

## Principle 4

Every operational action should be logged.

---

## Principle 5

Operational automation should minimise manual intervention.

---

## Principle 6

Validation should occur after significant operational changes.

---

## Principle 7

Operational data should enrich the Source of Truth whenever appropriate.

---

# AI-Assisted Operations

AI assistants may support Day-2 engineers by providing:

* Operational summaries
* Fault analysis
* Configuration explanations
* Runbook recommendations
* Impact analysis
* Documentation lookup
* Root cause investigation

AI agents must never execute infrastructure changes directly.

Execution always occurs through approved platform workflows.

---

# Day-2 Use Cases

Typical operational scenarios include:

### Health Monitoring

Daily verification of controller, leaf and spine health.

---

### Firmware Assessment

Identification of devices requiring software upgrades.

---

### Contract Verification

Validation that contracts continue to enforce expected traffic policies.

---

### VXLAN EVPN Validation

Verification of BGP EVPN neighbours, VTEPs and overlay health.

---

### Azure Connectivity Validation

Verification of VPN, ExpressRoute and Application Gateway connectivity.

---

### Operational Backups

Scheduled export of controller policies and configuration.

---

### Capacity Reporting

Collection of utilisation metrics for proactive capacity planning.

---

### Compliance Audits

Automated verification against engineering standards.

---

# Integration with Day-0 / Day-1

The platform intentionally separates provisioning from operations.

| Day-0 / Day-1            | Day-2                  |
| ------------------------ | ---------------------- |
| Provision infrastructure | Operate infrastructure |
| Create tenants           | Monitor tenants        |
| Create VRFs              | Validate VRFs          |
| Create Bridge Domains    | Verify Bridge Domains  |
| Create Contracts         | Test Contracts         |
| Create L3Outs            | Monitor L3Out health   |
| Terraform                | Ansible                |

Both workflows share:

* Nautobot
* Platform API
* Workflow Orchestrator
* Validation
* Observability

---

# Success Criteria

A mature Day-2 capability should provide:

* Minimal manual intervention
* Continuous validation
* Continuous compliance
* Automated reporting
* Centralised visibility
* Drift awareness
* Repeatable operational procedures

---

# Future Evolution

The Day-2 platform is expected to expand to include:

* Predictive maintenance
* Capacity forecasting
* AI-assisted diagnostics
* Automated remediation
* Digital Twin validation
* Change impact simulation
* Self-healing workflows

These capabilities should build upon the existing operational framework without changing the underlying architecture.

---

# Summary

Day-2 Operations extend the value of the platform beyond infrastructure provisioning.

By separating operational automation from infrastructure provisioning, the platform maintains clear ownership boundaries while enabling continuous validation, monitoring and optimisation of managed environments.

This operational model supports Cisco ACI today while remaining applicable to future domains such as Cisco Nexus VXLAN EVPN, Azure Networking and additional infrastructure platforms.
