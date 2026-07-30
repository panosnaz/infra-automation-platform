---
type: architecture
domain: platform
status: active
tags: [validation]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 08 – Continuous Validation Strategy

**Project:** Network Platform Engineering Platform

**Document Type:** Architecture Strategy

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

> **Update (2026-07-29):** the Platform API and Workflow Engine (n8n) sections below describe the original Platform v1 validation-trigger model. Per [ADR-016](../adr/ADR-016-Platform-v2-Replacement-Architecture.md) and the [Execution Framework](Execution-Framework.md), validation (pyATS) is now triggered as a GitLab CI stage, not by the Platform API/n8n. The validation principles and tiering described below remain valid.

---

# Purpose

This document defines the validation strategy for the Network Platform Engineering Platform.

Validation ensures that infrastructure behaves according to engineering intent rather than assuming successful deployment implies operational correctness.

Validation is considered an independent engineering capability and operates separately from infrastructure provisioning.

---

# Philosophy

Infrastructure deployment answers:

> **"Was the configuration successfully applied?"**

Validation answers:

> **"Is the platform actually operating as intended?"**

These questions are fundamentally different.

A deployment may complete successfully while still introducing:

- Routing failures
- Policy errors
- Connectivity loss
- Configuration drift
- Software defects

Validation exists to detect these conditions before they become production incidents.

---

# Validation Principles

The platform follows these architectural principles.

## Independent

Validation must never depend on the deployment tool.

Terraform should never validate itself.

Ansible should never validate its own operational changes.

Independent tooling provides objective verification.

---

## Continuous

Validation is an ongoing engineering capability.

Validation executes:

- Before deployment
- After deployment
- On schedule
- After incidents
- After upgrades
- After drift detection

---

## Observable

Every validation produces measurable results.

Examples:

- PASS
- WARNING
- FAILED
- Performance degradation
- Compliance score

Validation results should be retained for historical analysis.

---

## Repeatable

Validation should produce identical results regardless of who executes it.

---

## Extensible

New validation suites should be introduced without redesigning the validation platform.

---

# Validation Lifecycle

```text
Engineering Intent
        │
        ▼
Infrastructure Deployment
        │
        ▼
Continuous Validation
        │
        ▼
Compliance Assessment
        │
        ▼
Observability
        │
        ▼
Operational Feedback
        │
        ▼
Source of Truth
```

Validation is part of the continuous engineering feedback loop.

---

# Validation Categories

The platform validates multiple aspects of the infrastructure.

---

## Configuration Validation

Examples:

- Tenant exists
- VRF exists
- Bridge Domain configuration
- EPG assignments
- Contracts
- L3Out configuration
- BGP configuration

Purpose:

Confirm that intended configuration exists.

---

## Operational Validation

Examples:

- Controller health
- Leaf health
- Spine health
- Interface status
- CPU utilisation
- Memory utilisation
- Resource utilisation

Purpose:

Verify infrastructure health.

---

## Connectivity Validation

Examples:

- Endpoint reachability
- VRF connectivity
- Default gateway reachability
- BGP neighbours
- VXLAN tunnels
- External connectivity
- Azure VPN connectivity

Purpose:

Verify forwarding behaviour.

---

## Policy Validation

Examples:

- Contract enforcement
- EPG isolation
- Security policies
- Route leaking
- Access policies

Purpose:

Verify security intent.

---

## Compliance Validation

Examples:

- Naming conventions
- VLAN allocation
- Firmware baseline
- Object placement
- Engineering standards

Purpose:

Verify organisational compliance.

---

## Drift Validation

Examples:

- Manual APIC modifications
- Deleted objects
- Unexpected contracts
- Missing Bridge Domains
- Configuration drift

Purpose:

Detect differences between desired state and operational state.

---

## Performance Validation

Examples:

- Latency
- Packet loss
- Interface utilisation
- Fabric convergence
- BGP convergence
- Resource consumption

Purpose:

Identify operational degradation.

---

# Validation Triggers

Validation may be initiated by several mechanisms.

## Deployment Trigger

Executed immediately after infrastructure deployment.

---

## Scheduled Trigger

Examples:

- Hourly health checks
- Daily validation
- Weekly compliance reports
- Monthly inventory verification

---

## Event-Driven Trigger

Examples:

- Monitoring alert
- Drift detection
- Git merge
- ServiceNow request
- Platform event
- Failed deployment

---

## Manual Trigger

Engineer-initiated validation.

Used for:

- Troubleshooting
- Maintenance
- Change verification
- Root cause analysis

---

# Validation Framework

The platform uses multiple complementary validation technologies.

## pyATS

Responsibilities:

- Device connectivity
- Operational state collection
- Command execution
- Test execution
- Structured parsing

---

## Catfish

Responsibilities:

- Intent validation
- Declarative assertions
- Topology verification
- Network behaviour validation

---

## Python Validation Libraries

Responsibilities:

- Custom business validation
- API integrations
- Domain-specific checks
- Data processing

---

## Platform API

Responsibilities:

- Validation orchestration
- Result aggregation
- REST API
- Reporting interface

---

# Validation Scope

Validation applies consistently across all supported infrastructure domains.

Current domains:

- Cisco ACI
- Cisco Nexus VXLAN EVPN
- Azure Networking

Future domains:

- SD-WAN
- Firewalls
- Kubernetes Networking
- Hybrid Cloud

---

# Validation Workflow

```text
Validation Trigger
        │
        ▼
Workflow Engine (n8n)
        │
        ▼
Validation Platform
        │
        ▼
pyATS / Catfish / Python
        │
        ▼
Result Aggregation
        │
        ▼
Platform API
        │
        ▼
Dashboards / Notifications
```

---

# Validation Result Model

Every validation produces structured results.

Example fields:

- Validation ID
- Timestamp
- Infrastructure Domain
- Test Suite
- Test Name
- Severity
- Status
- Evidence
- Recommendation
- Execution Time

Possible states:

- PASS
- WARNING
- FAILED
- SKIPPED

---

# Failure Handling

Validation failures should never be ignored.

Possible responses include:

- Notify engineering teams
- Open ServiceNow incident
- Trigger investigation workflow
- Prevent production promotion
- Initiate rollback
- Schedule revalidation

The response depends on severity and business impact.

---

# AI-Assisted Validation

AI agents may assist engineers by:

- Explaining failed validations
- Correlating related failures
- Identifying probable root causes
- Recommending troubleshooting steps
- Suggesting relevant documentation
- Generating executive summaries

AI does **not** determine PASS or FAIL.

Validation outcomes remain deterministic and based on engineering rules.

---

# Validation Maturity Model

## Level 1

Manual validation.

---

## Level 2

Automated post-deployment validation.

---

## Level 3

Continuous scheduled validation.

---

## Level 4

Event-driven validation.

---

## Level 5

Predictive validation using AI-assisted analysis and Digital Twin simulation.

---

# Success Metrics

The validation platform should achieve:

- High automation coverage
- Low false positive rate
- Fast execution time
- Actionable reporting
- Historical trend analysis
- Minimal manual intervention

---

# Future Evolution

Future enhancements include:

- Digital Twin validation
- Synthetic transaction testing
- Predictive analytics
- Self-healing workflows
- Pre-deployment simulation
- AI-generated validation scenarios

These capabilities should extend the existing validation framework without changing its architectural principles.

---

# Summary

Continuous Validation is an independent engineering capability responsible for verifying that infrastructure operates according to engineering intent.

By separating validation from deployment, the platform provides objective assurance that infrastructure is not only successfully deployed but also operationally correct, compliant, healthy and continuously monitored throughout its lifecycle.