# ADR-004 — Platform API as the Unified Platform Interface

**Status:** Accepted

**Date:** 2026-06-29

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-001 — Nautobot as the Source of Truth
- ADR-002 — Terraform Owns Desired State Provisioning
- ADR-003 — Ansible Owns Day-2 Operations
- ADR-014 — Technical Policy Enforcement (OPA)
- ADR-015 — Deployment Approval as a Distinct Capability from Technical Policy

---

# Context

The Network Platform Engineering Platform integrates multiple engineering capabilities, including:

- Engineering Intent Management
- Infrastructure Provisioning
- Day-2 Operations
- Validation
- Observability
- Knowledge Management
- AI Engineering Assistance

These capabilities must be consumable by multiple clients, including:

- Engineers
- Automation workflows
- CI/CD pipelines
- Service portals
- AI assistants
- External ITSM platforms
- Future integrations

Without a common interface, every consumer would need to integrate directly with individual platform components.

This creates:

- Tight coupling
- Inconsistent authentication
- Duplicate business logic
- Multiple integration patterns
- Reduced maintainability
- Poor scalability

The platform therefore requires a unified interface through which all requests enter.

---

# Problem Statement

How should engineers, automation tools and external systems interact with the platform?

Should they communicate directly with internal platform components, or should a unified platform interface be provided?

---

# Decision

The platform shall expose a single Platform API that serves as the official entry point for all platform interactions.

All consumers communicate with the platform through this API.

Internal implementation details remain hidden behind the API boundary.

The Platform API is responsible for exposing platform capabilities—not infrastructure implementation.

---

# Responsibilities

The Platform API owns the external interface and the business logic of the platform.

Responsibilities are grouped into two named sub-capabilities. Both may ship inside the same FastAPI codebase, but they are conceptually distinct so that neither grows to absorb the other's concerns as the platform expands.

**Platform Gateway** — transport and API concerns only; makes no engineering decisions

- Authentication
- Authorization (RBAC)
- API versioning
- Rate limiting
- Audit logging
- Request parsing

**Intent Translation** — transforms an incoming request into Canonical Intent; answers *"can this request be understood?"*

- Parse incoming request
- Normalize data
- Resolve references
- Apply defaults
- Validate schema (Pydantic)
- Build Canonical Intent

Intent Translation does **not** decide whether a request is *allowed* — that is the Technical Policy Engine's responsibility ([ADR-014](ADR-014-Policy-Enforcement.md)) or the Approval Workflow's ([ADR-015](ADR-015-Deployment-Approval.md)), depending on which question is being asked (see ADR-014's Responsibility Boundary table).

## Pipeline Sequence

See [Platform Specification 02 — Platform API](../11-Specifications/02-Platform-API-Specification.md) §3 for the authoritative Intent Lifecycle and Deployment Lifecycle sequences — including the Technical Policy (ADR-014) vs. Approval Workflow (ADR-015) split, and the `PENDING_APPROVAL` resting state. This diagram is intentionally not reproduced here to avoid the two copies silently diverging, as happened before the 2026-07-05 Control Plane coherence review.

The Platform API does not execute infrastructure changes directly.

Execution is delegated to the Platform Control Plane after the Canonical Intent has been produced and stored.

## What the Workflow Engine Does Not Own

Business logic must not leak into the Workflow Engine.

The Workflow Engine (n8n) is an orchestrator.

It reacts to events and sequences execution tasks.

It does not:

- Validate business intent
- Enforce policy
- Normalise input formats
- Generate Canonical Intent
- Make business decisions

All business logic is the exclusive responsibility of the Platform API.

---

# Architectural Position

The Platform API is the boundary between platform consumers and internal platform services.

```text
Users
CLI
Service Portal
GitHub Actions
AI Agents
ITSM Platforms
        │
        ▼
=========================
      Platform API
=========================
        │
        ▼
Platform Control Plane
        │
        ▼
Internal Platform Services
```

All external communication terminates at the Platform API.

---

# Why Direct Access Is Prohibited

Consumers must never communicate directly with:

- Terraform
- Ansible
- Nautobot database
- Validation engines
- Vault
- Observability systems

Direct access introduces:

- Inconsistent authentication
- Duplicate integrations
- Uncontrolled execution
- Security risks
- Increased maintenance effort

The Platform API provides a stable abstraction layer.

---

# Standard Request Flow

Every platform request follows the same lifecycle — see [Platform Specification 02 — Platform API](../11-Specifications/02-Platform-API-Specification.md) §3 for the authoritative Intent Lifecycle and Deployment Lifecycle diagrams. (This section previously reproduced its own version of this flow, including an event, `IntentStored`, that was never defined in [ADR-011](ADR-011-Event-Driven-Automation.md)'s Named Platform Events table — exactly the kind of silent divergence eliminated by treating Contract #2 as the single authoritative sequence, per the 2026-07-05 Control Plane coherence review.)

Many entry points. One canonical execution path.

---

# Supported Consumers

The Platform API is designed to support multiple client types.

Current consumers include:

- Platform Engineers
- Network Engineers
- Cloud Engineers
- Automation Pipelines
- AI Engineering Assistants

Future consumers may include:

- Self-Service Portal
- Service Catalog
- ITSM Platforms
- CMDB Integrations
- Mobile Applications
- Third-party automation tools

The API remains stable regardless of client implementation.

---

# API Design Principles

The Platform API follows these principles:

- API-first design
- Resource-oriented interfaces
- Stateless requests
- Versioned endpoints
- Idempotent operations where appropriate
- Consistent response formats
- Structured error handling
- Backward compatibility where practical

The API should expose engineering concepts rather than vendor-specific implementation details.

---

# Example Platform Resources

Representative API resources include:

- Tenants
- Sites
- VRFs
- Networks
- Services
- Policies
- Deployments
- Validation Jobs
- Compliance Reports
- Workflows
- Knowledge Articles
- AI Sessions

These resources represent platform abstractions rather than infrastructure objects.

---

# Security Considerations

The Platform API integrates with the platform security model.

Security capabilities include:

- Identity-based authentication
- Role-Based Access Control (RBAC)
- Audit logging
- Request tracing
- Rate limiting
- Secure transport (HTTPS)
- Token-based authentication
- Secret isolation

Sensitive operations require appropriate authorization.

---

# Integration with the Platform Control Plane

The Platform API does not orchestrate workflows.

Instead, it delegates execution to the Platform Control Plane.

Responsibilities are clearly separated.

| Platform API | Platform Control Plane |
|--------------|------------------------|
| Accept requests | Coordinate execution |
| Validate input | Manage workflows |
| Authenticate users | Apply governance |
| Expose resources | Select execution engines |
| Return responses | Coordinate platform services |

This separation preserves modularity.

---

# Technology Independence

The Platform API represents an architectural capability rather than a specific implementation.

Possible implementations include:

- FastAPI
- Django REST Framework
- Flask
- Go
- Node.js
- ASP.NET Core

Future implementation changes should not require architectural redesign.

---

# Benefits

Adopting a unified Platform API provides:

- Consistent integrations
- Reduced coupling
- Standardized security
- Stable client interfaces
- Easier testing
- Better documentation
- Improved scalability
- Simplified automation
- Vendor independence

---

# Trade-Offs

Introducing a Platform API requires:

- API lifecycle management
- Version management
- Documentation maintenance
- Backward compatibility
- Operational monitoring

These responsibilities are acceptable because they centralize platform access and simplify long-term evolution.

---

# Alignment with Platform Principles

This decision directly supports:

- API-First Architecture
- Platform Before Tools
- Single Responsibility
- Separation of Responsibilities
- Security by Design
- Technology Independence
- Modularity
- Human Governance

---

# Future Considerations

Future enhancements may include:

- GraphQL support
- OpenAPI SDK generation
- WebSocket event streaming
- Self-service developer portal
- API analytics
- Multi-tenant APIs
- AI-native API endpoints

These enhancements extend the Platform API while preserving its architectural role.

---

# Summary

The Platform API is the unified entry point into the Network Platform Engineering Platform.

It provides a stable, secure and technology-independent interface through which engineers, automation systems and external platforms interact with platform capabilities.

The Platform API exposes engineering services while hiding internal implementation details, enabling the platform to evolve without disrupting its consumers.

Execution remains the responsibility of the Platform Control Plane, preserving a clear separation between interface and orchestration.