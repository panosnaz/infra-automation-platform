# START HERE

Welcome to the **Network Platform Engineering Platform** repository.

If this is your first time working with this project—whether you are a human engineer or an AI coding agent—this document explains where to begin.

---

# What is this repository?

This repository contains the source code, architecture, documentation and automation required to build a modern Network Platform Engineering solution.

The platform manages network infrastructure through a common engineering framework instead of isolated automation scripts.

Current supported domains include:

* Cisco ACI
* Cisco Nexus VXLAN EVPN
* Azure Networking

The architecture has been designed to support additional infrastructure domains without changing the overall platform.

---

# Platform Philosophy

The platform follows five core principles.

1. Engineering Intent lives in Nautobot.

2. The Platform Control Plane executes infrastructure changes.

3. Validation independently proves correctness.

4. Observability continuously measures operational state.

5. AI assists engineers but never directly controls infrastructure.

---

# High-Level Architecture

```text
Engineer
    │
    ▼
Nautobot (Source of Truth)
    │
    ▼
Platform Control Plane
    │
    ▼
Terraform / Ansible
    │
    ▼
Infrastructure
    │
    ▼
Continuous Validation
    │
    ▼
Observability
    │
    ▼
AI Reasoning
    │
    ▼
Engineering Improvements
    │
    └──────────────► Source of Truth
```

---

# Recommended Reading Order

If you are new to the project, read the documents in this order.

1. START-HERE.md

2. README.md

3. README-ARCHITECTURE.md

4. docs/architecture/

Continue with:

* 00 Project Charter
* 01 Current State
* 02 Target Architecture
* 03 Platform Principles
* 04 Technology Stack
* 05 Repository Structure
* 06 Deployment Workflow
* 07 Day-2 Operations
* 08 Continuous Validation
* 09 AI-Augmented Platform
* 10 Platform Security
* 11 Platform Observability
* 12 Platform Roadmap
* 13 Platform Lifecycle Management

Finally, review the Architecture Decision Records (ADRs) to understand the reasoning behind key design choices.

---

# Golden Rules

The following rules apply throughout the project.

* Nautobot is the single Source of Truth.
* Infrastructure changes originate from engineering intent.
* Terraform provisions infrastructure.
* Ansible performs operational configuration.
* Validation is independent from deployment.
* AI never executes infrastructure directly.
* Secrets are managed centrally.
* Every significant architectural decision must have an ADR.
* Documentation is treated as code.
* Every change is version controlled.

---

# Repository Structure

```text
docs/
architecture/
adr/
automation/
terraform/
ansible/
python/
platform-api/
validation/
knowledge/
workflows/
```

---

# If You Are an AI Coding Agent

Before generating code:

* Read the architecture documents.
* Respect the documented platform principles.
* Do not introduce technologies that conflict with the architecture.
* Prefer extending existing platform capabilities over creating new ones.
* Assume Nautobot is the authoritative Source of Truth.
* Route infrastructure execution through the Platform Control Plane.
* Treat validation as a mandatory engineering activity.
* Never bypass governance or security controls.

---

# Long-Term Vision

The objective is not simply to automate Cisco ACI.

The objective is to build a reusable Network Platform Engineering Platform capable of managing multiple infrastructure domains through a common architecture.

The platform should remain modular, deterministic, observable and AI-augmented for many years.
