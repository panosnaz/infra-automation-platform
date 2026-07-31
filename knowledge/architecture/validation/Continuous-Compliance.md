---
type: architecture
domain: platform
status: active
tags: [validation, compliance]
owner: platform-engineering-team
last_updated: 2026-08-01
---

# 04 – Continuous Compliance

> **Update (2026-08-01):** "Platform API" below is the original Platform v1 name for "the platform's single entry point." Per [ADR-016](../../adr/ADR-016-Platform-v2-Replacement-Architecture.md), that role is now the **MCP Server** — the compliance principles below are unchanged; only the component name changed.

## Purpose

Continuous Compliance ensures that infrastructure remains aligned with engineering intent after deployment.

Unlike Infrastructure Validation, which verifies a single deployment, Continuous Compliance continuously monitors operational infrastructure throughout its lifecycle.

---

# Position in the Workflow

```text
Infrastructure
        │
        ▼
Continuous Compliance
        │
        ▼
Observability
        │
        ▼
Knowledge Layer
```

---

# Objectives

Continuously verify:

- Configuration drift
- Policy compliance
- Security posture
- Naming standards
- Operational standards
- Platform governance
- Lifecycle compliance

---

# Typical Checks

Examples include:

- Manual configuration changes
- Unauthorized VLAN creation
- Contract modifications
- Route changes
- Firewall rule drift
- Secret expiration
- Certificate expiration
- Software version compliance
- Backup verification

---

# Triggers

Continuous Compliance may execute:

- On a schedule
- After deployments
- After Ansible playbooks
- Following monitoring alerts
- After software upgrades
- During maintenance windows
- Upon manual request

---

# Possible Technologies

- pyATS
- Catfish
- Python automation
- GitHub Actions
- Event-Driven workflows
- Custom compliance engines

---

# Outputs

Produces:

- Compliance reports
- Drift reports
- Security findings
- Policy violations
- Engineering recommendations
- Automated remediation requests

---

# Integration

Continuous Compliance integrates with:

- Observability
- Workflow Engine
- Knowledge Layer
- AI Engineering Assistant
- Platform API

Compliance failures may automatically initiate remediation workflows through the Platform Control Plane.

---

# Success Criteria

Infrastructure continuously remains aligned with:

- Engineering intent
- Platform standards
- Security policies
- Operational requirements
- Governance controls

Continuous Compliance transforms validation from a one-time deployment activity into an ongoing engineering capability.