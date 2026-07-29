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
2. [`knowledge/README.md`](knowledge/README.md) — knowledge base map (architecture, ADRs, runbooks, AI notes)
3. [`knowledge/architecture/Platform-v2-Reference-Architecture.md`](knowledge/architecture/Platform-v2-Reference-Architecture.md) — the approved target architecture (MCP Server + Nautobot + GitLab)
4. [`knowledge/architecture/Execution-Framework.md`](knowledge/architecture/Execution-Framework.md) — the 7-stage lifecycle and the current build milestones (§6) — this is the actual build order and status tracker
5. Relevant ADRs in [`knowledge/adr/`](knowledge/adr/) for the capability you are changing (`knowledge/adr/archive/` holds ADRs superseded by [ADR-016](knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md))

`docs/` is reserved for future generated/customer-facing documentation only — it is not the knowledge base. If a stale reference anywhere points at `docs/START-HERE.md`, `docs/ARCHITECTURE-AT-A-GLANCE.md`, `docs/03-Decisions/`, or `docs/folder structure`, treat it as wrong and use the `knowledge/` paths above instead.

---

## Repository layout

| Path | Purpose |
|---|---|
| `platform/python/` | Generator: Nautobot GraphQL → NetAsCode YAML |
| `platform/terraform/aci/` | Terraform ACI module |
| `platform/ansible/aci/` | Ansible Day-2 playbooks |
| `platform/netascode/aci/` | Generated NetAsCode YAML — committed by the `generate_nac` CI job, not gitignored |
| `platform/workflows/scripts/` | Python scripts backing GitLab CI jobs (`write_results.py`, `capture_knowledge.py`, `check_determinism.sh`, `commit_generated_yaml.sh`, `policy_check.py`, `validate_nac.py`) |
| `tests/pyats/aci/` | pyATS validation tests |
| `tests/unit/` | Generator unit tests |
| `tests/integration/` | Live-lab integration smoke tests |
| `pipelines/` | GitLab CI includes — `pipelines/includes/common.gitlab-ci.yml` (shared hidden job templates) + `pipelines/aci.gitlab-ci.yml` (domain wiring); root `.gitlab-ci.yml` just includes the ACI pipeline |
| `docker/` | All lab infrastructure (Nautobot, Vault, GitLab, GitLab Runner, OPA, Prometheus/Grafana/Loki, MinIO, Traefik) as Compose stacks |
| `knowledge/adr/` | Architecture Decision Records |

---

## Conventions

- **Source of Truth:** Nautobot owns all intent. Do not put infrastructure intent in Terraform variables or Ansible vars.
- **Terraform:** consumes NetAsCode YAML; does not duplicate Nautobot data.
- **Ansible:** Day-2 operations only; does not provision new infrastructure.
- **Validation:** always independent of Terraform and Ansible.
- **Secrets:** never hardcode tokens, passwords, or API keys. Use environment variables, or read from Vault at runtime.
- **ACI system tenants** (`common`, `infra`, `mgmt`): Terraform must not recreate these.
- **GitLab CI `needs:` is not transitive** — a job only auto-downloads artifacts from jobs explicitly listed in its own `needs:` array. Always list every upstream job whose generated file/artifact is actually consumed, not just the immediately-prior stage.

---

## Active lab (local GitLab CE + Nautobot + Vault)

- Nautobot: `http://localhost:8080`, API token `0123456789abcdef0123456789abcdef01234567`
- ACI Simulator: `https://172.30.46.103` (self-signed cert, use `--no-verify`) — can go unreachable independent of this repo; check `docker network ls` for a subnet collision (a real recurring bug class here, see [`Current-State.md`](knowledge/architecture/Current-State.md)) before assuming a genuine external outage
- GitLab CE: `http://localhost:8929` / `http://gitlab.local:8929`, project `root/nautobot-infra-automation`
- HashiCorp Vault: `http://localhost:8200` — root token in `docker/vault/state/vault-keys.txt` (gitignored, regenerated on each init)
- MinIO: `http://localhost:9000`, bucket `knowledge-capture`

---

## Current build status (Execution Framework, per ADR-017/ADR-018)

Phase 2 is built domain-automation-first, with no AI/MCP Server involved until Milestone 5. See [`Execution-Framework.md` §6](knowledge/architecture/Execution-Framework.md) for full gate evidence.

| Milestone | Scope | Status |
|---|---|---|
| 1 | GitLab Execution Pipeline (validate → policy → plan → apply → ansible → pyATS → capture) against a static NetAsCode YAML fixture | ✅ Complete |
| 2 | Nautobot → NetAsCode Integration (`generate_nac` job replaces the static fixture, generator determinism proven) | ✅ Complete |
| 3 | Policy & Approval (OPA policy job + GitLab protected-branch manual-gate substitute for Premium-only Protected Environments) | ✅ Complete |
| 4 | Verification & Knowledge Capture (`write_results.py` → Nautobot custom fields, `capture_knowledge.py` → GitLab artifact + MinIO JSONL) | ✅ Complete |
| 5 | MCP Server (`mcp-server/`, tool registry, thin per-tool schemas, no shared intent envelope per ADR-018 — `create_tenant` + `show_status` scope) | ✅ Complete |
| 6 | AI Agents (Claude Desktop, VS Code Copilot Agent, future LangGraph) as MCP clients | ❌ Not started |

Domain coverage (a separate axis from the milestones above — see [ADR-020](knowledge/adr/ADR-020-ACI-Domain-Coverage-Expansion.md) and [`Execution-Framework.md` §7](knowledge/architecture/Execution-Framework.md)) is **complete as of 2026-07-29**: VRF/BD attribute depth, Application Profiles/EPGs, Contracts/Filters/Subjects, L3Out, and Access/Fabric Policies (VLAN Pools, Physical Domains, AEPs, Leaf Interface Policy Groups) are all implemented, unit-tested, and live-verified. L3Out and Access Policies are logical-only (no physical interface/OSPF/BGP attachment) — a permanent limitation of this lab's ACI simulator (confirmed via direct APIC API queries: no real leaf/spine interface data exists), not a gap in the generator/Terraform pattern. The MCP Server's tool catalogue has been widened to match Phase A: `create_vrf`/`create_bridge_domain`/`create_epg`/`create_contract`/`create_l3out` (2026-07-29) — Access/Fabric Policy tools (Phase B) remain a future addition.

The old Platform API (`main.py`, `execution_store.py`, `approval_workflow.py`, `terraform_executor.py`, `nautobot_store.py`) is **legacy (Platform v1)**, replaced (not migrated) per [ADR-016](knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md) — do not extend it.
