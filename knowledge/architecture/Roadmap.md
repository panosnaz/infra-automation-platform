---
type: architecture
domain: platform
status: active
tags: [roadmap]
owner: platform-engineering-team
last_updated: 2026-07-31
---

# 12 – Platform Roadmap

**Project:** Network Platform Engineering Platform

**Document Type:** Strategic Roadmap

**Status:** Draft v1.0

**Owner:** Platform Engineering Team

---

# Purpose

This document defines the strategic evolution of the Network Platform Engineering Platform.

Rather than focusing on specific projects or deadlines, the roadmap describes the platform's expected maturity over time.

The roadmap serves as a planning guide for future engineering capabilities while remaining flexible enough to accommodate changing business priorities and technology advancements.

> **2026-07-28 update:** the near-term increment following Phase 1's infrastructure work (see [`Platform-v2-As-Built.md`](Platform-v2-As-Built.md)) is **not** scoped as "build the GitLab CI pipeline." It is scoped as the [**Execution Framework**](Execution-Framework.md) — a seven-stage lifecycle (Intent → Validation → Policy → Approval → Execution → Verification → Knowledge Capture) of which GitLab CI implements exactly one stage (Execution) plus hosts the native Approval gate. See [ADR-017](../adr/ADR-017-Execution-Framework.md) for the decision record. The future AI/reasoning-layer integration (Obsidian-compatible knowledge base, Nautobot, GitLab, Vault, OPA, and a future LangGraph layer) is mapped onto this same lifecycle in [`../ai/Future-AI-Integration-Design.md`](../ai/Future-AI-Integration-Design.md), even though LangGraph itself remains a later-phase build.

---

# Vision

The long-term vision is to build a unified, AI-augmented Network Platform capable of managing multiple infrastructure domains through a common engineering framework.

The platform should provide:

- Declarative infrastructure management
- Continuous validation
- Event-driven automation
- AI-assisted engineering
- Secure operations
- Observable automation
- Reusable engineering services
- Multi-domain support

The platform evolves incrementally while maintaining backward compatibility whenever practical.

---

# Guiding Principles

The roadmap follows several principles.

- Build reusable platform capabilities.
- Prefer incremental improvements over large rewrites.
- Automate repetitive engineering tasks.
- Keep the Source of Truth authoritative.
- Separate reasoning from execution.
- Design for multiple infrastructure domains.
- Continuously improve operational maturity.

---

# Platform Maturity Model

The platform evolves through five maturity levels.

```text
Level 1
Manual Automation
        │
        ▼
Level 2
Platform Automation
        │
        ▼
Level 3
Platform Engineering
        │
        ▼
Level 4
AI-Augmented Platform
        │
        ▼
Level 5
Autonomous Engineering Platform
```

Each level builds upon the previous one.

---

# Level 1 – Manual Automation

Current focus:

Automate repetitive engineering tasks.

Capabilities include:

- Ansible playbooks
- Terraform deployments
- CSV/YAML inputs
- Manual execution
- Basic documentation
- Initial Git repository

Primary objective:

Reduce manual configuration effort.

---

# Level 2 – Platform Automation

Focus:

Standardise engineering workflows.

Capabilities:

- Nautobot as Source of Truth
- Platform API
- Workflow orchestration
- Git-based deployments
- Standardised repository structure
- Validation framework
- Automated documentation

Primary objective:

Deliver consistent and repeatable infrastructure deployments.

---

# Level 3 – Platform Engineering

Focus:

Treat the automation platform as an engineering product.

Capabilities:

- Domain-based architecture
- Shared platform services
- Policy as Code
- Secrets management
- Observability
- Continuous validation
- Engineering standards
- Architecture Decision Records
- CI/CD pipelines — see the [Execution Framework](Execution-Framework.md) for the stage-by-stage design this platform builds pipelines against

Primary objective:

Build a maintainable engineering platform rather than isolated automation scripts.

---

# Level 4 – AI-Augmented Platform

Focus:

Increase engineering productivity using AI.

Capabilities:

- AI architecture assistant
- AI documentation assistant
- AI validation assistant
- AI code generation
- Knowledge retrieval
- MCP integration
- Vector database
- Semantic documentation search
- Engineering recommendations

See [`../ai/Future-AI-Integration-Design.md`](../ai/Future-AI-Integration-Design.md) for how the knowledge base, Nautobot, GitLab, Vault, OPA, and a future LangGraph reasoning layer map onto this level's capabilities.

Primary objective:

Accelerate engineering while preserving deterministic execution.

---

# Level 5 – Autonomous Engineering Platform

Focus:

Highly autonomous engineering workflows.

Potential capabilities:

- Predictive analytics
- Digital Twin simulation
- Automated impact analysis
- AI-assisted capacity planning
- Intelligent change recommendations
- Automated remediation
- Self-healing workflows
- Multi-agent collaboration

Human governance remains mandatory for production infrastructure changes.

Primary objective:

Maximise engineering efficiency while maintaining governance and operational safety.

---

# Infrastructure Domain Expansion

The platform is designed to support multiple infrastructure domains.

## Phase 1

- Cisco ACI

---

## Phase 2

- Cisco Nexus VXLAN EVPN
- **Complete** ([ADR-021](../adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md)): generator (`generate_evpn.py`), Nautobot data model (Custom Fields on VRF/VLAN/Device), Terraform module (`platform/terraform/evpn/`, real `CiscoDevNet/nxos` provider), and pyATS tests are in place. **Live-verified against real hardware** — a real CML lab with 4 genuine Nexus 9000v devices was found and used; all 4 now have a proven `terraform apply` cycle. What remains is wiring the EVPN pipeline into the root GitLab pipeline, which needs the lab's devices to be reachable from wherever the pipeline runs — a lab networking limitation, not a code gap. See [`Platform-Status-and-Pending-Items.md`](Platform-Status-and-Pending-Items.md) for the current state of that work.

---

## Phase 3

- Azure Networking

---

## Future

Potential future domains include:

- SD-WAN
- Firewall platforms
- Load Balancers
- Kubernetes Networking
- Public Cloud Networking
- Hybrid Cloud

Each new domain should reuse the common platform capabilities wherever possible.

---

# Platform Capability Roadmap

The following capabilities are expected to mature over time.

| Capability | Initial | Target |
|------------|----------|---------|
| Source of Truth | Nautobot | Enterprise CMDB Integration |
| Deployment | Terraform / Ansible | Platform API |
| Validation | pyATS / Catfish | Continuous Validation |
| Observability | Metrics | AI-assisted Observability |
| Security | RBAC | Zero Trust Platform |
| Documentation | Markdown | AI-generated Knowledge Base |
| Workflows | Manual | Event-driven Automation |
| AI | Assistant | Multi-agent Collaboration |

---

# Engineering Priorities

The following priorities guide platform development.

## Reliability

Improve stability and repeatability of automation.

---

## Reusability

Develop shared libraries, templates and services.

---

## Standardisation

Reduce variation across infrastructure domains.

---

## Governance

Ensure all automation remains auditable and policy-driven.

---

## Developer Experience

Simplify onboarding and platform usage.

---

## Operational Excellence

Improve visibility, validation and incident response.

---

# Success Metrics

Platform success should be measured through engineering outcomes rather than technology adoption.

Examples include:

- Deployment success rate
- Deployment frequency
- Validation coverage
- Configuration drift reduction
- Mean Time to Detect (MTTD)
- Mean Time to Recover (MTTR)
- Platform availability
- Automation adoption
- Documentation coverage
- Engineering productivity

---

# Risks

Potential risks include:

- Platform complexity
- Technology sprawl
- Over-automation
- Vendor lock-in
- Skill gaps
- AI overreliance
- Operational drift

These risks should be reviewed regularly and addressed through continuous improvement.

---

# Continuous Improvement

The roadmap is a living document.

Platform capabilities should be reviewed periodically based on:

- Business requirements
- Engineering feedback
- Technology evolution
- Operational experience
- Security recommendations
- Lessons learned

Architecture Decision Records (ADRs) should capture significant design changes.

---

# Long-Term Vision

The Network Platform Engineering Platform aims to become the standard engineering platform for network infrastructure management across the organisation.

The platform should provide a unified operating model for:

- Infrastructure provisioning
- Operational automation
- Validation
- Observability
- Security
- AI-assisted engineering

while remaining extensible enough to support future technologies and infrastructure domains.

---

# Summary

The roadmap describes the platform's evolution from isolated automation scripts into a mature, AI-augmented engineering platform.

By focusing on reusable capabilities, continuous validation, strong governance and incremental improvements, the platform can evolve sustainably while delivering long-term value to engineering and operations teams.