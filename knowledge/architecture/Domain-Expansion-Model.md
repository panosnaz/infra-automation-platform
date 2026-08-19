---
type: architecture
domain: platform
status: active
tags: [domain-expansion]
owner: platform-engineering-team
last_updated: 2026-08-19
---

# Domain Expansion Model

## Purpose

This diagram shows how the platform adds a new infrastructure domain without redesigning
the shared services every domain relies on (the MCP Server dispatcher, GitLab CI's shared
stage templates, Nautobot's core setup). See [ADR-020](../adr/ADR-020-ACI-Domain-Coverage-Expansion.md)
and [ADR-021](../adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md) for the two domains that have
actually proven this pattern so far.

> **Implementation note:** "Platform API" and "Workflow Engine" in the diagram below are
> the original Platform v1 names. Per [ADR-016](../adr/ADR-016-Platform-v2-Replacement-Architecture.md),
> these responsibilities are now split across the MCP Server (tool dispatch) and GitLab CI
> (pipeline orchestration) — see [`Execution-Framework.md`](Execution-Framework.md).

**Cisco ACI and Cisco Nexus VXLAN EVPN are the two domains built and live-verified today.**
Azure Networking and any further domains (Fortinet, SD-WAN, etc.) are future work, added the
same additive way — a new generator, a new Terraform/Ansible tree, a new pipeline file, new
MCP tools in their own module — never by changing the shared services themselves.

```text
                          COMMON PLATFORM SERVICES

                  Platform API
                        │
                  Workflow Engine
                        │
                 Validation Framework
                        │
                Observability Platform
                        │
                   AI Reasoning Plane
                        │
                Knowledge Management
                        │
      ┌─────────────────┼───────────────────┬──────────────────┐
      ▼                 ▼                   ▼                  ▼
  Cisco ACI      VXLAN EVPN          Future Domains      Future Domains
  (built)          (built)         (e.g. Azure, Fortinet)      (...)
```