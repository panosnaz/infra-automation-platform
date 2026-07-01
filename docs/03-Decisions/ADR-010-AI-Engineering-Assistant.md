# ADR-009 — AI as an Engineering Assistant

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
- ADR-008 — Validation as an Independent Platform Capability

---

# Context

The Network Platform Engineering Platform incorporates Artificial Intelligence to improve engineering productivity, accelerate knowledge discovery and assist with operational decision making.

AI enables engineers to interact with the platform using natural language while leveraging accumulated architectural knowledge, operational history and engineering standards.

However, AI systems are probabilistic.

Infrastructure execution must remain deterministic.

For this reason, AI must never become the authoritative source of engineering intent or execute infrastructure changes directly.

---

# Problem Statement

How should Artificial Intelligence be integrated into the platform without compromising governance, security or engineering quality?

Should AI interact directly with infrastructure, or should it operate as an engineering assistant within the platform architecture?

---

# Decision

Artificial Intelligence shall operate exclusively as an Engineering Assistant.

AI provides recommendations, analysis, documentation and engineering guidance.

All infrastructure execution shall be performed by the Platform Control Plane after appropriate validation and, where required, human approval.

The guiding principle is:

> **AI Recommends. Humans Approve. The Platform Executes.**

---

# Architectural Position

The AI Engineering Layer operates alongside the platform rather than inside the execution path.

```text
Engineer
     │
     ▼
AI Engineering Assistant
     │
     ▼
Platform API
     │
     ▼
Platform Control Plane
     │
     ▼
Terraform / Ansible
     │
     ▼
Infrastructure
```

AI never bypasses the Platform API or Platform Control Plane.

---

# Responsibilities

The AI Engineering Assistant is responsible for:

- Architecture guidance
- Design reviews
- Documentation generation
- Engineering recommendations
- Troubleshooting assistance
- Validation analysis
- Drift analysis
- Knowledge retrieval
- Code generation
- Workflow suggestions
- Impact analysis
- Best practice recommendations

The AI layer does not:

- Execute infrastructure
- Modify production systems directly
- Store authoritative engineering intent
- Replace engineering governance
- Override validation results

---

# Knowledge Sources

The AI Engineering Assistant may use:

- Architecture documentation
- ADRs
- Platform Principles
- Runbooks
- Validation reports
- Observability data
- Canonical Engineering Models
- Knowledge Layer
- Platform APIs
- Operational history

Engineering recommendations are grounded in the platform's documented knowledge.

---

# Interaction with the Knowledge Layer

The Knowledge Layer serves as the primary context source for AI.

It contains:

- Architecture decisions
- Standards
- Design patterns
- Operational procedures
- Validation outcomes
- Lessons learned
- Troubleshooting guides

The AI Engineering Assistant retrieves information from the Knowledge Layer but does not modify authoritative records without platform workflows.

---

# Interaction with the Platform API

All AI interactions with the platform occur through the Platform API.

The API provides controlled access to:

- Engineering intent
- Validation results
- Workflow status
- Inventory
- Documentation
- Operational telemetry

Direct access to infrastructure components is prohibited.

---

# Human Governance

Human engineers remain accountable for engineering decisions.

Typical approval points include:

- Production deployments
- Architecture changes
- Security policy modifications
- Network segmentation
- Large-scale infrastructure updates

AI assists decision making but does not replace human judgement.

---

# Safety Principles

The AI Engineering Assistant follows these principles:

- Explain recommendations.
- Cite relevant documentation where available.
- Distinguish facts from assumptions.
- Request clarification when information is incomplete.
- Respect governance workflows.
- Operate within platform permissions.
- Never expose secrets.
- Never bypass validation.
- Never execute infrastructure directly.

---

# Example Workflow

```text
Engineer
      │
      ▼
Ask AI:
"Deploy a new ACI Tenant"
      │
      ▼
AI analyses request
      │
      ▼
Suggests architecture
      │
      ▼
Engineer approves
      │
      ▼
Platform API
      │
      ▼
Platform Control Plane
      │
      ▼
Terraform
      │
      ▼
Validation
      │
      ▼
Observability
      │
      ▼
Knowledge Updated
```

The AI remains advisory throughout the workflow.

---

# Benefits

Integrating AI as an Engineering Assistant provides:

- Faster engineering decisions
- Improved documentation quality
- Consistent architecture guidance
- Accelerated troubleshooting
- Knowledge reuse
- Reduced onboarding time
- Better design consistency
- Enhanced operational efficiency

---

# Trade-Offs

AI integration introduces:

- Additional platform complexity
- Context management requirements
- Prompt engineering
- Model lifecycle management
- Continuous knowledge maintenance

These trade-offs are acceptable because AI significantly enhances engineering productivity without compromising governance.

---

# Alignment with Platform Principles

This decision supports:

- Human Governance
- Platform Before Tools
- API-First Architecture
- Knowledge as a Platform Asset
- Validation First
- Closed-Loop Engineering
- Security by Design
- Continuous Improvement

---

# Future Considerations

Future AI capabilities may include:

- Multi-agent collaboration
- Automated design reviews
- Intelligent workflow generation
- Predictive capacity planning
- Root cause analysis
- Policy recommendation
- Digital Twin simulation
- AI-assisted validation authoring

These capabilities extend the Engineering Assistant while preserving the separation between reasoning and execution.

---

# Summary

Artificial Intelligence is integrated into the Network Platform Engineering Platform as an Engineering Assistant.

AI enhances engineering productivity through analysis, recommendations and knowledge retrieval while remaining outside the infrastructure execution path.

Infrastructure changes continue to follow the established platform workflow through the Platform API, Platform Control Plane, execution engines and independent validation.

This architecture combines the strengths of AI-assisted reasoning with deterministic, governed and auditable infrastructure automation.