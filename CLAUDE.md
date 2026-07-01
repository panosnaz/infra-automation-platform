---
title: "AI Agent Instructions — Network Platform Engineering Platform"
description: "Entry point and operating instructions for AI coding agents working in this repository."
---

# AI Agent Instructions

This file provides context and operating instructions for AI agents (Claude, GitHub Copilot, etc.) working in this repository.

---

## What is this repository?

The **Network Platform Engineering Platform** automates network infrastructure through a common engineering framework. The current implementation targets Cisco ACI and is designed to expand to additional domains.

**Do not** treat this as an ACI-only project. Every design decision is made with multi-domain reuse in mind.

---

## Read these files first

Before making any changes, read in order:

1. [`README.md`](README.md) — project overview and quick start
2. [`docs/START-HERE.md`](docs/START-HERE.md) — platform philosophy and architecture navigation
3. [`docs/ARCHITECTURE-AT-A-GLANCE.md`](docs/ARCHITECTURE-AT-A-GLANCE.md) — full architecture reference
4. Relevant ADRs in [`docs/03-Decisions/`](docs/03-Decisions/) for the capability you are changing

---

## Repository layout

The canonical layout is defined in [`docs/folder structure`](docs/folder%20structure). Key paths:

| Path | Purpose |
|---|---|
| `platform/python/` | Generator: Nautobot → NetAsCode YAML |
| `platform/terraform/aci/` | Terraform ACI module |
| `platform/ansible/aci/` | Ansible Day-2 playbooks |
| `platform/netascode/aci/` | Generated YAML output (gitignored) |
| `tests/pyats/aci/` | pyATS validation tests |
| `docs/03-Decisions/` | Architecture Decision Records |
| `lab/docker/nautobot/` | Local Nautobot lab (nested git repo, not tracked) |

---

## Conventions

- **Source of Truth:** Nautobot owns all intent. Do not put infrastructure intent in Terraform variables or Ansible vars.
- **Terraform:** consumes NetAsCode YAML; does not duplicate Nautobot data.
- **Ansible:** Day-2 operations only; does not provision new infrastructure.
- **Validation:** always independent of Terraform and Ansible.
- **Secrets:** never hardcode tokens, passwords, or API keys. Use environment variables.
- **ACI system tenants** (`common`, `infra`, `mgmt`): Terraform must not recreate these.

---

## Active Nautobot lab

- URL: `http://localhost:8080`
- API token: `0123456789abcdef0123456789abcdef01234567`
- ACI Simulator: `https://172.30.46.103` (self-signed cert, use `--no-verify`)

---

## Pending implementation (vertical slice)

| Phase | Directory | Status |
|---|---|---|
| Generator | `platform/python/` | ✅ Complete |
| Terraform ACI module | `platform/terraform/aci/` | ⏳ Phase 3 |
| Ansible Day-2 | `platform/ansible/aci/` | ⏳ Phase 4 |
| pyATS validation | `tests/pyats/aci/` | ⏳ Phase 5 |
| Unit tests | `tests/unit/` | ⏳ Phase 6 |
| GitHub Actions CI | `.github/workflows/` | ⏳ Phase 7 |
