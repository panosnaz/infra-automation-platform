# 02 – Infrastructure Validation

## Purpose

Infrastructure Validation verifies that the requested infrastructure has been successfully deployed.

It focuses on the infrastructure itself rather than application behavior.

---

# Position in the Workflow

```text
Terraform / Ansible
        │
        ▼
Infrastructure
        │
        ▼
Infrastructure Validation
```

---

# Objectives

Verify:

* Resource creation
* Configuration correctness
* Routing
* Interface state
* VXLAN state
* BGP EVPN status
* Cisco ACI object state
* Azure resource deployment

---

# Typical Checks

Examples include:

* Tenant exists.
* VRF exists.
* Bridge Domain deployed.
* EPG operational.
* BGP sessions established.
* VXLAN VNIs active.
* Azure VNET created.
* NSGs applied.
* Route Tables associated.

---

# Possible Technologies

* pyATS
* Catfish
* Terraform outputs
* Cisco APIs
* Azure REST APIs
* Custom Python validation

---

# Output

Produces:

* Pass/Fail status
* Resource inventory
* Configuration deviations
* Infrastructure health report

---

# Success Criteria

Infrastructure exists exactly as defined by the Canonical Engineering Model.
