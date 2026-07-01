---
title: "Network Platform Engineering Platform"
description: "Repository entry point for the Network Platform Engineering Platform — automated, validated, AI-augmented network infrastructure management."
---

# Network Platform Engineering Platform

A reusable engineering control plane that manages network infrastructure through declarative intent, automated provisioning, continuous validation, and AI-assisted workflows.

**Current focus:** Cisco ACI vertical slice — Nautobot → NetAsCode YAML → Terraform → Ansible → pyATS

---

## Start here

| First time? | Read [`docs/START-HERE.md`](docs/START-HERE.md) |
|---|---|
| Architecture overview | [`docs/ARCHITECTURE-AT-A-GLANCE.md`](docs/ARCHITECTURE-AT-A-GLANCE.md) |
| AI agent entry point | [`CLAUDE.md`](CLAUDE.md) |

---

## Platform flow

```
Nautobot (SoT)
    │
    ▼  platform/python/generate_aci.py
NetAsCode YAML  (platform/netascode/aci/)
    │
    ▼  terraform apply
Cisco ACI (APIC)
    │
    ▼  ansible-playbook
Day-2 operations
    │
    ▼  pyats run job
Continuous validation
```

---

## Repository structure

```
platform/
  python/        Generator: Nautobot GraphQL → NetAsCode YAML
  netascode/aci/ NetAsCode YAML (generated, gitignored)
  terraform/aci/ Terraform ACI module  (Phase 3)
  ansible/aci/   Ansible Day-2 playbooks (Phase 4)

tests/
  pyats/aci/     pyATS validation tests (Phase 5)
  unit/          Generator unit tests (Phase 6)

docs/            Architecture, ADRs, operations guides
lab/             Local lab environment (Nautobot Docker stack)
```

Full canonical layout: [`docs/folder structure`](docs/folder%20structure)

---

## Nautobot lab

| URL | `http://localhost:8080` |
|---|---|
| Admin | `admin` / `admin` |
| API token | `0123456789abcdef0123456789abcdef01234567` |
| ACI Simulator | `https://172.30.46.103` |

Start the lab:

```bash
cd lab/docker/nautobot
docker compose up -d
```

---

## Quick start — run the generator

```bash
# Install dependencies
pip install -r platform/python/requirements.txt

# Generate NetAsCode YAML from Nautobot (includes lab system tenants)
python platform/python/generate_aci.py \
  --token 0123456789abcdef0123456789abcdef01234567 \
  --include-system-tenants

# Dry-run (print YAML, do not write files)
python platform/python/generate_aci.py --token <TOKEN> --dry-run
```

---

## Architecture decisions

All decisions are recorded as ADRs in [`docs/03-Decisions/`](docs/03-Decisions/):

| ADR | Decision |
|---|---|
| ADR-001 | Nautobot as the authoritative Source of Truth |
| ADR-002 | Terraform owns desired-state provisioning |
| ADR-003 | Ansible owns Day-2 operations |
| ADR-007 | Cisco NetAsCode as the canonical engineering model |
| ADR-008 | Validation as an independent platform capability |

---

## Technology stack

| Capability | Technology |
|---|---|
| Source of Truth | Nautobot |
| Desired State | Terraform (`netascode/aci`) |
| Day-2 Operations | Ansible (`cisco.aci`) |
| Validation | pyATS + Catfish |
| Platform API | FastAPI (future) |
| Orchestration | n8n (future) |
| Secrets | HashiCorp Vault (future) |
| CI/CD | GitHub Actions (future) |
