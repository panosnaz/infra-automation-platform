# 06 – Engineering Deployment Workflow

**Project:** Network Platform Engineering Platform

**Document Type:** Operational Workflow

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

---

# Purpose

This document defines the standard engineering workflow for introducing infrastructure changes into the Network Platform Engineering Platform.

The objective is to ensure that every deployment is:

* Repeatable
* Auditable
* Governed
* Validated
* Observable
* Recoverable

No infrastructure changes should bypass this workflow unless performed under an approved emergency change process.

---

# Engineering Lifecycle

Every infrastructure change follows the same canonical lifecycle regardless of the entry point.

```text
Entry Point (Portal • CLI • Jira • Git • AI • REST • ServiceNow)
        │
        ▼
Platform API (Intent Translation Layer)
   • Authentication + Authorisation
   • Request Validation + Normalisation
   • Policy Enforcement
   • Canonical Intent Generation
        │
        ▼ Event: IntentReceived
Nautobot (Source of Truth)
   • Engineering Intent stored
        │
        ▼ Event: IntentStored
Approval (if required)
        │
        ▼
NetAsCode Generator
   • Canonical Model (YAML) generated
        │
        ▼ Event: DeploymentRequested → DeploymentStarted
Workflow Engine (Orchestration)
        │
        ▼
Execution (Terraform / Ansible)
        │
        ▼ Event: DeploymentCompleted
Validation  ──────► Event: ValidationPassed / ValidationFailed
        │
        ▼
Observability (continuous • cross-cutting)
        │
        ▼
Knowledge Layer (Engineering Memory updated)
        │
        ▼
Continuous Operations
```

This lifecycle applies equally to Cisco ACI, Cisco Nexus VXLAN EVPN, Azure Networking and future supported domains.

No consumer bypasses the Platform API.

No consumer receives special treatment regardless of entry point.

---

# Roles and Responsibilities

| Role                | Responsibility                   |
| ------------------- | -------------------------------- |
| Requester           | Defines business requirement     |
| Network Engineer    | Creates or updates intent        |
| Platform API        | Receives engineering requests    |
| Nautobot            | Stores desired intent            |
| Workflow Engine     | Coordinates deployment           |
| Git                 | Tracks all changes               |
| CI/CD               | Executes pipeline                |
| Terraform           | Provisions infrastructure        |
| Validation Platform | Confirms correctness             |
| Observability       | Monitors deployed infrastructure |

---

# Phase 1 – Business Request

A deployment begins with a business or operational requirement.

Examples include:

* New application onboarding
* New tenant
* Additional VRF
* New L3Out
* Contract modification
* Azure connectivity
* VXLAN EVPN extension

The requester does not interact directly with infrastructure.

---

# Phase 2 – Intent Creation

The Network Engineer translates the request into engineering intent.

Intent is created or updated in Nautobot.

Typical objects include:

* Tenant
* VRF
* Bridge Domain
* EPG
* Contract
* External Network
* VLAN Pool
* IPAM Objects

Nautobot becomes the authoritative representation of the requested change.

---

# Phase 3 – Change Validation

Before deployment begins, the Platform API performs initial validation.

Checks include:

* Mandatory fields
* Object relationships
* Naming conventions
* Duplicate objects
* Dependency validation

Requests failing validation are rejected before infrastructure code is generated.

---

# Phase 4 – Workflow Orchestration

The Platform API invokes the workflow engine.

The workflow coordinates:

* Notifications
* Approval gates
* Artifact generation
* Git operations
* Pipeline execution
* Status updates

The workflow engine orchestrates activities but does not perform infrastructure deployment.

---

# Phase 5 – Intent Generation

Engineering intent is transformed into deployment artifacts.

Outputs may include:

* Terraform configuration
* Variable files
* YAML
* JSON
* Documentation
* Change reports

Generated artifacts should not be edited manually.

---

# Phase 6 – Version Control

Generated artifacts are committed to Git.

Each deployment must include:

* Commit message
* Associated change request
* Pull Request
* Peer review

Git becomes the immutable audit trail for all engineering changes.

---

# Phase 7 – Policy Validation

Before deployment, policy validation is executed.

Typical checks include:

* Naming standards
* VLAN allocation
* VRF placement
* Security policy
* Route leaking restrictions
* Tenant isolation
* Environment constraints

Policy failures prevent deployment.

---

# Phase 8 – CI/CD Pipeline

The CI/CD platform executes the deployment pipeline.

Pipeline stages include:

1. Syntax validation
2. Static analysis
3. Policy enforcement
4. Terraform formatting
5. Terraform validation
6. Terraform plan
7. Approval gate
8. Terraform apply
9. Post-deployment validation
10. Reporting

Every stage must complete successfully before progressing.

---

# Phase 9 – Infrastructure Deployment

Terraform provisions the desired infrastructure.

Terraform is responsible for:

* Creating resources
* Updating resources
* Removing obsolete resources
* Maintaining state

No manual infrastructure changes should occur during deployment.

---

# Phase 10 – Independent Validation

Successful deployment does not guarantee operational correctness.

Independent validation verifies:

* Configuration consistency
* Endpoint connectivity
* Routing
* Contract enforcement
* Object relationships
* Platform health
* Compliance

Validation is executed using:

* pyATS
* Catfish
* Custom Python validation suites

---

# Phase 11 – Observability

Following successful validation, the observability platform begins continuous monitoring.

Collected information includes:

* Infrastructure health
* API metrics
* Deployment metrics
* Validation results
* Platform events
* Performance indicators

Observability provides the operational baseline for future deployments.

---

# Phase 12 – Closed-Loop Feedback

Deployment results are returned to the Platform Control Plane.

Feedback includes:

* Deployment outcome
* Validation status
* Compliance reports
* Drift information
* Operational health

This information updates the engineering view of the platform.

---

# Rollback Strategy

Every deployment must define a rollback approach.

Rollback methods include:

* Terraform state rollback
* Git revert
* Previous release deployment
* Manual recovery procedures (only when necessary)

Rollback procedures should be documented before production deployment.

---

# Failure Handling

Failures may occur during any phase.

Typical failure scenarios include:

* Invalid intent
* Policy violation
* Pipeline failure
* Terraform error
* Validation failure
* Infrastructure API failure
* Connectivity loss

Failure handling principles:

* Stop further execution.
* Preserve logs.
* Notify stakeholders.
* Prevent partial deployments where possible.
* Record audit information.
* Provide clear remediation guidance.

---

# Emergency Change Process

Emergency changes should remain exceptional.

When required:

1. Obtain appropriate approval.
2. Record the justification.
3. Perform the minimum necessary change.
4. Capture the implemented state.
5. Reconcile the Source of Truth after resolution.
6. Conduct a post-implementation review.

Emergency changes should never become routine operational practice.

---

# Deployment Success Criteria

A deployment is considered successful only when:

* Intent has been approved.
* Infrastructure has been provisioned.
* Validation has passed.
* Compliance has been confirmed.
* Observability is operational.
* No critical drift exists.
* Documentation has been updated.

Infrastructure deployment alone does not constitute success.

---

# Workflow Summary

The engineering workflow can be summarized as:

```text
Business Requirement
        │
        ▼
Nautobot (Intent)
        │
        ▼
Platform API
        │
        ▼
Workflow Engine
        │
        ▼
Intent Generation
        │
        ▼
Git
        │
        ▼
Policy Validation
        │
        ▼
CI/CD
        │
        ▼
Terraform Apply
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
Closed-Loop Feedback
```

---

# Summary

The Engineering Deployment Workflow provides a governed, repeatable and auditable process for introducing infrastructure changes.

By separating intent, orchestration, deployment, validation and observability into distinct phases, the platform minimizes operational risk while ensuring consistency across all supported infrastructure domains.

This workflow forms the operational backbone of the Network Platform Engineering Platform and should be followed for every standard infrastructure change.
