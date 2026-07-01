# ADR-008 — Validation as an Independent Platform Capability

**Status:** Accepted

**Date:** 2026-06-29

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-002 — Terraform Owns Desired State Provisioning
- ADR-003 — Ansible Owns Day-2 Operations
- ADR-004 — Platform API as the Unified Platform Interface
- ADR-005 — Workflow Orchestration
- ADR-006 — Platform Control Plane as the Single Orchestration Layer
- ADR-007 — Cisco NetAsCode as the Canonical Engineering Model

---

# Context

Provisioning infrastructure successfully does not guarantee that the infrastructure behaves as intended.

Examples include:

- Resources successfully created but incorrectly configured
- Routing established but traffic failing
- Contracts deployed but applications unreachable
- Policies configured but non-compliant
- Infrastructure healthy while business services remain unavailable

Traditional Infrastructure as Code pipelines often terminate after successful execution.

The Network Platform Engineering Platform extends the engineering lifecycle by introducing independent validation as a core architectural capability.

Validation confirms that deployed infrastructure satisfies engineering intent before changes are considered complete.

---

# Problem Statement

How should the platform determine whether infrastructure changes have achieved the intended engineering outcome?

Should deployment success be considered sufficient, or should an independent validation capability verify the resulting infrastructure state?

---

# Decision

The platform shall implement Validation as an independent platform capability.

Validation shall execute independently of the infrastructure provisioning and operational automation engines.

Infrastructure deployment is not considered successful until validation confirms that engineering intent has been achieved.

---

# Architectural Position

Validation sits after infrastructure execution and before operational acceptance.

```text
Engineering Intent
        │
        ▼
Canonical Engineering Model
        │
        ▼
Terraform / Ansible
        │
        ▼
Infrastructure
        │
        ▼
Validation
        │
        ▼
Observability
        │
        ▼
Knowledge Layer
```

Validation provides the bridge between deployment and operational confidence.

---

# Responsibilities

The Validation capability owns:

- Infrastructure verification
- Configuration validation
- Connectivity testing
- Service validation
- Policy verification
- Compliance validation
- Drift detection
- Engineering acceptance testing
- Validation reporting

Validation does not own:

- Infrastructure deployment
- Workflow orchestration
- Monitoring
- Configuration management
- Engineering intent

---

# Validation Categories

The platform supports multiple validation domains.

## Infrastructure Validation

Examples:

- Resource existence
- Object relationships
- Interface status
- Fabric health

---

## Configuration Validation

Examples:

- Tenant configuration
- VRF configuration
- Bridge Domains
- Contracts
- Azure networking

---

## Connectivity Validation

Examples:

- Endpoint reachability
- Routing verification
- VXLAN forwarding
- Application communication

---

## Policy Validation

Examples:

- Security policies
- Contract enforcement
- Network segmentation
- ACL verification

---

## Compliance Validation

Examples:

- Naming standards
- Configuration standards
- Platform policies
- Security requirements

---

## Drift Detection

Examples:

- Configuration drift
- Operational drift
- Engineering drift
- Unauthorized changes

---

# Validation Lifecycle

Validation is performed throughout the engineering lifecycle.

```text
Engineering Intent
        │
        ▼
Pre-Deployment Validation
        │
        ▼
Infrastructure Execution
        │
        ▼
Post-Deployment Validation
        │
        ▼
Continuous Validation
        │
        ▼
Event-Driven Validation
```

Validation is continuous rather than a one-time activity.

---

# Validation Triggers

Validation may be initiated by:

- Infrastructure deployment
- Ansible execution
- Scheduled jobs
- Monitoring alerts
- Drift detection
- Software upgrades
- Maintenance windows
- Security events
- Manual engineer request

---

# Integration with the Platform

Validation is coordinated by the Platform Control Plane.

```text
Workflow Engine
        │
        ▼
Terraform / Ansible
        │
        ▼
Infrastructure
        │
        ▼
Validation Framework
        │
        ▼
Observability
        │
        ▼
Knowledge Repository
```

Validation results become inputs for subsequent platform decisions.

---

# Validation Frameworks

The platform may employ multiple validation technologies.

Examples include:

- pyATS
- Catfish
- Python validation libraries
- Custom validation scripts
- API-based health checks

Validation capabilities may evolve without changing the platform architecture.

---

# Interaction with Observability

Validation confirms engineering correctness.

Observability confirms operational health.

These capabilities complement one another.

Validation answers:

> "Was the engineering intent achieved?"

Observability answers:

> "Is the platform operating correctly over time?"

Both are required.

---

# Interaction with AI

AI assistants consume validation results to:

- Explain failures
- Recommend remediation
- Identify patterns
- Improve future automation
- Generate documentation
- Assist troubleshooting

AI does not replace validation.

Validation provides objective engineering evidence.

---

# Benefits

Validation as an independent platform capability provides:

- Higher deployment confidence
- Reduced operational risk
- Objective acceptance criteria
- Improved compliance
- Automated verification
- Continuous assurance
- Better troubleshooting
- Enhanced AI reasoning
- Stronger governance

---

# Trade-Offs

Independent validation introduces:

- Additional execution time
- Validation framework maintenance
- Test lifecycle management
- Result storage
- Reporting infrastructure

These trade-offs are acceptable because they significantly improve platform reliability.

---

# Alignment with Platform Principles

This decision supports:

- Validation First
- Closed-Loop Engineering
- Separation of Responsibilities
- Platform Before Tools
- Event-Driven Automation
- Human Governance
- AI as an Engineering Assistant
- Continuous Improvement

---

# Future Considerations

Future enhancements may include:

- AI-generated validation tests
- Synthetic application testing
- Policy-as-Code validation
- Multi-domain validation
- Continuous compliance monitoring
- Predictive validation
- Digital Twin verification
- Automated remediation recommendations

These capabilities extend the Validation platform without changing its architectural role.

---

# Success Criteria

A platform workflow is considered complete only when:

- Engineering intent is approved.
- Infrastructure execution succeeds.
- Validation passes.
- No critical compliance violations exist.
- Observability confirms healthy operation.
- Audit records are generated.
- Knowledge artifacts are updated.

Successful execution alone does not constitute successful delivery.

---

# Summary

Validation is a first-class architectural capability within the Network Platform Engineering Platform.

It operates independently of provisioning and operational automation to verify that deployed infrastructure satisfies engineering intent.

By separating execution from verification, the platform establishes a closed-loop engineering model that improves confidence, governance and long-term operational quality.

Validation is therefore a mandatory stage of every engineering workflow rather than an optional post-deployment activity.