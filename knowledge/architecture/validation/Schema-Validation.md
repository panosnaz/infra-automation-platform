---
type: architecture
domain: platform
status: active
tags: [validation]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 01 – Schema Validation

## Purpose

Schema Validation verifies that engineering intent is structurally correct before any infrastructure changes are executed.

It prevents invalid requests from reaching Terraform, Ansible or infrastructure APIs.

---

# Position in the Workflow

```text
Engineer
    │
    ▼
Nautobot
    │
    ▼
Schema Validation
    │
    ▼
Workflow Engine
```

---

# Objectives

Validate:

* Required fields
* Object relationships
* Naming standards
* Data types
* Mandatory attributes
* Reference integrity
* Canonical Engineering Model compatibility

---

# Typical Validation Rules

Examples include:

* Tenant names follow platform standards.
* VRFs belong to an existing Tenant.
* Bridge Domains reference valid VRFs.
* VLAN IDs are unique.
* IP prefixes do not overlap.
* Azure CIDRs are valid.
* VXLAN VNIs are unique.

---

# Possible Technologies

* Pydantic
* JSON Schema
* NetAsCode schema validation
* Python validation libraries

---

# Output

Schema Validation produces:

* Validation status
* Detailed errors
* Warnings
* Suggested remediation

Infrastructure execution only proceeds after successful schema validation.

---

# Success Criteria

* Valid engineering intent
* Consistent object relationships
* Standards compliance
* Ready for execution
