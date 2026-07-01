# ADR-012 — Centralized Secrets Management

**Status:** Accepted

**Date:** 2026-06-30

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-002 — Terraform Owns Desired State Provisioning
- ADR-003 — Ansible Owns Day-2 Operations
- ADR-004 — Platform API
- ADR-005 — Workflow Orchestration
- ADR-006 — Platform Control Plane
- ADR-007 — Cisco NetAsCode as the Canonical Engineering Model
- ADR-008 — Validation as an Independent Platform Capability
- ADR-009 — Knowledge Layer as the Engineering Memory of the Platform
- ADR-010 — AI as an Engineering Assistant
- ADR-011 — Event-Driven Automation

---

# Context

Modern infrastructure automation relies on numerous sensitive credentials.

Examples include:

- Device credentials
- Cloud service credentials
- API tokens
- SSH keys
- Certificates
- Database passwords
- Service account credentials
- Encryption keys

Historically, these secrets have often been embedded in:

- Source code
- Configuration files
- Terraform variables
- Ansible inventories
- CI/CD pipelines

This approach increases operational risk and makes credential rotation, auditing and governance difficult.

A Platform Engineering architecture requires a centralized capability responsible for securely managing secrets throughout their lifecycle.

---

# Problem Statement

How should sensitive credentials be managed across the platform?

Should each platform component manage its own credentials, or should secrets be centrally governed and retrieved only when required?

---

# Decision

The platform shall implement a **Centralized Secrets Management** capability.

Secrets are owned by a dedicated platform service and retrieved by authorized components only when required.

No platform component permanently stores or owns sensitive credentials.

---

# Architectural Principles

The Secrets Management capability shall follow these principles:

- Centralized ownership
- Least privilege access
- Identity-based authentication
- Secret retrieval at runtime
- Encryption at rest
- Encryption in transit
- Audit logging
- Secret rotation
- Technology independence

---

# Architectural Position

The Secrets Management capability provides credentials to platform components without exposing or duplicating sensitive information.

```text
                    Secrets Management
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼

   Platform API       Terraform          Ansible

        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                            ▼

                    Infrastructure
```

Secrets remain under centralized governance.

---

# Responsibilities

The Secrets Management capability is responsible for:

- Secure storage
- Secret retrieval
- Credential rotation
- Access control
- Audit logging
- Certificate storage
- Encryption key management
- Secret lifecycle management

It is **not** responsible for:

- Infrastructure provisioning
- Configuration management
- Validation
- Workflow orchestration
- Documentation

---

# Secret Categories

The platform manages multiple categories of secrets.

## Infrastructure Credentials

Examples:

- Cisco APIC credentials
- Cisco Nexus credentials
- Azure authentication
- Cloud provider credentials

---

## Platform Credentials

Examples:

- Database credentials
- Message broker credentials
- Platform API authentication
- Internal service authentication

---

## Automation Credentials

Examples:

- Terraform providers
- Ansible automation accounts
- Git repository credentials
- CI/CD service accounts

---

## Security Material

Examples:

- TLS certificates
- SSH private keys
- Encryption keys
- Signing certificates

---

# Secret Lifecycle

Secrets follow a managed lifecycle.

```text
Generate
     │
     ▼
Store
     │
     ▼
Retrieve
     │
     ▼
Rotate
     │
     ▼
Revoke
     │
     ▼
Archive
```

Every stage is governed and auditable.

---

# Runtime Secret Retrieval

Platform components retrieve secrets only when required.

Secrets are never embedded within:

- Source code
- Git repositories
- Markdown documentation
- Configuration templates
- Container images

Long-term storage outside the Secrets Management capability is prohibited.

---

# Identity-Based Access

Platform components authenticate using identities rather than shared credentials.

Access decisions are based on:

- Component identity
- Role
- Environment
- Scope
- Policy

Each component receives only the minimum permissions required.

---

# Least Privilege

The platform enforces least privilege access.

Examples include:

- Terraform accesses only infrastructure credentials.
- Ansible accesses only required automation credentials.
- Validation retrieves only the credentials necessary for testing.
- AI services do not receive direct access to secrets.

No component receives unrestricted access.

---

# Rotation

Secrets should support automated rotation whenever practical.

Examples include:

- Password rotation
- API token renewal
- Certificate renewal
- SSH key replacement

Automation should minimize operational disruption during rotation.

---

# Audit Logging

Every secret operation should be auditable.

Examples include:

- Secret creation
- Secret retrieval
- Secret modification
- Secret rotation
- Secret deletion
- Failed access attempts

Audit records support governance, compliance and incident investigations.

---

# Integration with Platform Components

## Terraform

Terraform retrieves credentials at runtime.

Secrets are not stored within infrastructure code whenever avoidable.

---

## Ansible

Ansible retrieves credentials dynamically during automation execution.

Playbooks remain free of embedded credentials.

---

## Platform API

The Platform API authenticates securely using centrally managed credentials.

API clients receive only the permissions required for their operations.

---

## Validation

Validation tools retrieve only the credentials required to perform validation tasks.

---

## AI Engineering Assistant

AI assistants never receive unrestricted access to secrets.

Any AI interaction requiring infrastructure access must be mediated through approved platform services.

---

# Security Considerations

The platform shall ensure:

- Encryption at rest
- Encryption in transit
- Role-based access control
- Identity-based authentication
- Secure audit logging
- Secret expiration
- Credential rotation
- Multi-environment isolation

---

# Technology Independence

The Secrets Management capability represents an architectural function rather than a specific product.

Potential implementations include:

- HashiCorp Vault
- Azure Key Vault
- AWS Secrets Manager
- Kubernetes Secrets (where appropriate)
- Other enterprise secrets management solutions

Implementation technologies may evolve without changing the architectural principles.

---

# Benefits

Centralized Secrets Management provides:

- Improved security
- Reduced credential sprawl
- Simplified rotation
- Better governance
- Improved auditability
- Reduced operational risk
- Consistent automation
- Stronger compliance

---

# Trade-Offs

The platform accepts additional operational complexity in exchange for improved security.

Trade-offs include:

- Secret lifecycle management
- Identity integration
- High availability requirements
- Backup and recovery considerations

These trade-offs are acceptable because centralized governance significantly reduces security risk.

---

# Alignment with Platform Principles

This decision supports:

- Security by Design
- Least Privilege
- Platform Before Tools
- Separation of Responsibilities
- API-First Architecture
- Closed-Loop Engineering
- Continuous Improvement

---

# Future Considerations

Future enhancements may include:

- Automatic secret rotation
- Dynamic credential generation
- Short-lived credentials
- Hardware-backed key protection
- Certificate lifecycle automation
- Federated identity integration
- Just-in-time privileged access

These capabilities further strengthen the security posture while preserving the architectural role of the Secrets Management capability.

---

# Summary

The Network Platform Engineering Platform adopts a centralized Secrets Management capability responsible for the secure storage, retrieval, rotation and governance of sensitive credentials.

Platform components retrieve secrets dynamically using identity-based authentication and least-privilege access rather than embedding credentials within code or configuration.

By separating credential management from platform implementation, the architecture improves security, auditability and operational consistency while remaining independent of any specific secrets management technology.