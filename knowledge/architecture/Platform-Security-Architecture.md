---
type: architecture
domain: platform
status: active
tags: [security]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 10 – Platform Security Architecture

**Project:** Network Platform Engineering Platform

**Document Type:** Architecture Strategy

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

> **Update (2026-07-29):** the "Platform API Security" section below describes the original Platform v1 single-entry-point model (Platform API + n8n + GitHub Actions). Per [ADR-016](../adr/ADR-016-Platform-v2-Replacement-Architecture.md), the Platform API is legacy/replaced — the MCP Server is now the single entry point for AI agents (see [`Platform-v2-Reference-Architecture.md`](Platform-v2-Reference-Architecture.md) §1), and GitLab CE/CI (not GitHub Actions/n8n) is the execution engine. This document's underlying security principles (least privilege, AI never gets direct execution-engine access, secrets centralized in Vault) remain valid and unchanged — only the specific component names are outdated.

---

# Purpose

This document defines the security architecture of the Network Platform Engineering Platform.

The objective is to ensure that every platform component operates according to the principles of least privilege, defense in depth, auditability and zero trust.

Security is treated as a cross-cutting architectural capability rather than a standalone feature.

---

# Security Philosophy

The platform follows one fundamental principle:

> **Trust nothing. Verify everything.**

Every request must be authenticated.

Every action must be authorized.

Every change must be auditable.

---

# Security Objectives

The platform is designed to provide:

- Confidentiality
- Integrity
- Availability
- Auditability
- Least Privilege
- Non-Repudiation
- Secure Automation

Security applies equally to engineers, automation, APIs and AI agents.

---

# Security Domains

The platform security model consists of several independent domains.

```text
                Platform Security

        ┌────────────────────────────┐
        │ Identity & Authentication  │
        ├────────────────────────────┤
        │ Authorization (RBAC)       │
        ├────────────────────────────┤
        │ Secrets Management         │
        ├────────────────────────────┤
        │ API Security               │
        ├────────────────────────────┤
        │ CI/CD Security             │
        ├────────────────────────────┤
        │ Infrastructure Security    │
        ├────────────────────────────┤
        │ AI Security                │
        ├────────────────────────────┤
        │ Audit & Compliance         │
        └────────────────────────────┘
```

---

# Identity and Authentication

Every user, service and automation component must possess an identity.

Examples:

- Engineers
- Platform API
- GitHub Actions
- n8n
- Nautobot
- AI Agents
- Validation Platform

Authentication should use enterprise identity providers where possible.

Examples:

- Microsoft Entra ID
- LDAP
- OAuth2
- OpenID Connect

---

# Authorization

Authentication identifies who you are.

Authorization determines what you may do.

The platform follows Role-Based Access Control (RBAC).

Example roles include:

- Platform Administrator
- Network Architect
- Network Engineer
- Operations Engineer
- Read-Only User
- AI Service Account
- CI/CD Service Account

Every role receives only the permissions required.

---

# Secrets Management

Secrets must never be stored in:

- Git repositories
- Terraform code
- Ansible playbooks
- Markdown documentation
- AI prompts
- Configuration templates

Secrets are centrally managed.

Recommended technologies:

- HashiCorp Vault
- Azure Key Vault

Examples of managed secrets:

- APIC credentials
- Azure service principals
- API tokens
- SSH keys
- Certificates

---

# Platform API Security

The Platform API is the single entry point into the platform.

Security requirements include:

- Authentication
- Authorization
- HTTPS only
- Token expiration
- Rate limiting
- Input validation
- Audit logging

Infrastructure components should never be exposed directly to end users.

---

# Workflow Security

Workflow orchestration must enforce governance.

Examples:

- Approval gates
- Change windows
- Environment restrictions
- Production approval
- Emergency workflow

Automation must never bypass governance.

---

# Infrastructure Security

Infrastructure components should not be directly modified.

Examples:

- APIC
- Azure
- Nexus Dashboard
- MSO

Changes should occur only through approved platform workflows.

Manual production changes should be exceptional and reconciled back into the Source of Truth.

---

# Git Security

Git is the authoritative history of engineering intent.

Security requirements include:

- Protected branches
- Pull Requests
- Peer review
- Signed commits (recommended)
- Mandatory CI validation

Direct commits to production branches should be prohibited.

---

# CI/CD Security

The deployment pipeline should enforce:

- Static analysis
- Policy validation
- Secret scanning
- Dependency scanning
- Artifact integrity
- Environment approval

Production deployment should require explicit approval.

---

# AI Security

AI introduces unique security considerations.

AI must never:

- Store credentials
- Execute privileged commands directly
- Bypass RBAC
- Ignore approval workflows
- Modify production without governance

AI should operate with least privilege and interact only through the Platform API.

---

# Validation Security

Validation systems should be read-only wherever possible.

Validation credentials should not possess deployment privileges.

This separation prevents validation tooling from modifying production infrastructure.

---

# Observability Security

Monitoring platforms collect operational information.

Access should be restricted according to role.

Sensitive information should be masked where appropriate.

Audit logs should be immutable.

---

# Logging and Audit

Every significant platform action should be recorded.

Examples include:

- User authentication
- Infrastructure deployment
- AI interactions
- Validation execution
- Workflow approvals
- Secret access
- Platform configuration changes

Audit records should include:

- Timestamp
- Identity
- Action
- Target
- Outcome

---

# Policy as Code

Security policies should be version controlled.

Examples:

- Naming standards
- Environment restrictions
- Production approvals
- Allowed deployment windows
- Resource ownership

Policy evaluation should occur before deployment.

---

# Zero Trust Principles

The platform adopts Zero Trust principles.

- Never trust implicitly.
- Verify every request.
- Authenticate continuously.
- Authorize every action.
- Log everything.
- Assume compromise.

---

# Security Responsibilities

| Capability | Responsibility |
|------------|----------------|
| Identity | Enterprise Identity Provider |
| Secrets | Vault / Key Vault |
| Authorization | RBAC |
| API Security | Platform API |
| Workflow Governance | n8n |
| Deployment | Terraform / Ansible |
| Validation | pyATS / Catfish |
| Monitoring | Prometheus / Grafana |
| Audit | Central Logging |

---

# AI Governance

AI recommendations are advisory.

AI must never become the final authority for infrastructure changes.

Every infrastructure change remains subject to:

- Engineering review
- Policy validation
- Approval workflow
- Deterministic execution
- Audit logging

---

# Security Maturity Model

## Level 1

Basic authentication.

---

## Level 2

RBAC and centralized secrets.

---

## Level 3

Policy as Code.

---

## Level 4

Zero Trust platform.

---

## Level 5

Continuous risk assessment with AI-assisted anomaly detection.

---

# Future Evolution

The security architecture is expected to evolve with:

- Short-lived credentials
- Hardware-backed identities
- Certificate-based workload authentication
- Continuous compliance
- Supply chain security
- Software Bill of Materials (SBOM)
- Runtime threat detection
- AI-assisted anomaly detection

These enhancements should strengthen the platform without changing its core security principles.

---

# Summary

The Network Platform Engineering Platform treats security as a foundational architectural capability.

By integrating identity, authorization, secrets management, governance, auditability and zero trust into every layer of the platform, security becomes an inherent property of the architecture rather than an afterthought.

The platform remains secure regardless of whether infrastructure is managed through Terraform, Ansible, AI-assisted workflows or future automation technologies.