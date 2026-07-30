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
4. [`knowledge/adr/ADR-019-Three-Truths-Principle.md`](knowledge/adr/ADR-019-Three-Truths-Principle.md) — the core conceptual model (Business Intent / Desired State / Observed State) underpinning every other design decision
5. [`knowledge/adr/ADR-018-NetAsCode-Centric-Execution-Framework.md`](knowledge/adr/ADR-018-NetAsCode-Centric-Execution-Framework.md) — why NetAsCode YAML, not an MCP-owned schema, is the authoritative intent artifact
6. [`knowledge/architecture/Execution-Framework.md`](knowledge/architecture/Execution-Framework.md) — the 7-stage lifecycle and the current build milestones (§6) — this is the actual build order and status tracker
7. [`knowledge/architecture/Platform-Status-and-Pending-Items.md`](knowledge/architecture/Platform-Status-and-Pending-Items.md) — current status, known pending items, and hard-won operational lessons — check this before starting new work (supersedes `Current-State.md`, which is stale)
8. [`Platform-Administration-Guide.md`](Platform-Administration-Guide.md) — operational reference for every running container (ports, credentials, restart/troubleshooting procedures) — read before touching `docker compose` in this repo
9. Relevant ADRs in [`knowledge/adr/`](knowledge/adr/) for the specific capability you are changing (`knowledge/adr/archive/` holds ADRs superseded by [ADR-016](knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md))

---

## Custom Agents (`.github/agents/`)

This repo is frequently opened alongside other repos in a multi-root workspace that already define their own custom agents (some with generic, easily-colliding names — e.g. a generic Nautobot DCIM/IPAM admin agent unrelated to this platform). When adding a new custom agent here:

- **Workspace-committed only** (`.github/agents/*.agent.md`), never user-profile-scoped — every developer working on this repo must get the same agents via version control, with no personal drift.
- **Name and describe it specifically enough to survive being opened next to unrelated repos' agents.** Don't assume this repo's agents are the only ones in the picker. State plainly, in the `description:` field, what this agent is *not* for, including "not the generic Nautobot/DCIM/IPAM agent you might have from elsewhere" if relevant — that exact collision exists today (`NautobotExpert` in the sibling `mcp-servers` workspace folder).
- **Default to `disable-model-invocation: true`** for business-facing personas (meant to be explicitly chosen by a human via the agent picker) unless there's a specific reason to allow another agent to auto-delegate to it as a subagent.
- **State hard MCP/container dependencies in the description**, not just in the body — a developer opening this repo standalone, without the required container running, should be told why the agent has no working tools rather than left guessing.
- Current agents: [`network-platform-operator.agent.md`](.github/agents/network-platform-operator.agent.md) — business-operation persona scoped to this platform's MCP tools only (no terminal access, by design — see its own file for the incident that led to that).

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
- ACI Simulator: `https://172.30.46.103` (self-signed cert, use `--no-verify`) — can go unreachable independent of this repo; check `docker network ls` for a subnet collision (a real recurring bug class here, see [`Current-State-v1.md`](knowledge/architecture/archive/Current-State-v1.md)) before assuming a genuine external outage
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
| 6 | AI Agents (Claude Desktop, VS Code Copilot Agent, future LangGraph) as MCP clients | ✅ Complete |

Milestone 6 (2026-07-29): the VS Code Copilot Agent was wired as a real MCP client (`.vscode/mcp.json`, `streamable-http` transport) against the running `mcp-server` container. Gate met via a single natural-language request that drove `create_tenant` → `create_vrf` → `create_bridge_domain` (tenant `milestone6-demo`) purely through AI tool-call reasoning, confirmed the webhook-triggered GitLab pipeline (`source: "trigger"`, no manual trigger), and confirmed `show_status` correctly reported back. Two real, unrelated issues surfaced by this run, both now resolved: (1) a pre-existing tenant `ACI:Sales` violated the OPA naming policy and blocked `terraform_plan`/`terraform_apply` on every pipeline — fixed by renaming to `ACI:sales`; (2) two pre-existing duplicate VRF objects (`web-vrf` under `ACI:web-tenant`, `new-app-vrf` under `ACI:new-app-tenant`) each had one real entry and one empty orphan from the same debris window — both orphans deleted after confirming zero attached resources, verified clean via pipeline #32 reaching `terraform_apply: manual`. (3) the full-stack incident recovery earlier this session had left `minio` running with placeholder root credentials that didn't match GitLab CI's stored variables, breaking `knowledge_capture` — found and fixed by recreating only the `minio` container with the correct credentials. See `Execution-Framework.md` §6 for full evidence.

**Domain Expansion Phase 2 — VXLAN EVPN ([ADR-021](knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md), started 2026-07-29):** the first domain expansion beyond ACI, proving the Execution Framework's mechanism generalizes. Confirmed the real Terraform provider (`CiscoDevNet/nxos` v0.13.1) and its resource schemas (`nxos_feature`/`nxos_vrf`/`nxos_bridge_domain`/`nxos_nvo`/`nxos_evpn`) via the Terraform Registry before writing any code. Built `generate_evpn.py` + `generator/evpn_{client,transformer}.py`, Nautobot Custom Fields (`VRF.evpn_l3_vni`, `VLAN.evpn_l2_vni`/`evpn_vrf`, `Device.evpn_bgp_asn`/`evpn_role`), `platform/terraform/evpn/`, `platform/ansible/evpn/`, and `pipelines/evpn.gitlab-ci.yml` (not yet included from the root `.gitlab-ci.yml` -- deliberate, see below). Live-verified end-to-end against real Nautobot: created a test EVPN tenant/VRF/VLAN, ran the generator (caught and fixed a real bug -- it was exporting ACI tenants too, not just `EVPN:`-prefixed ones), proved determinism (byte-identical on a second run), then fed the generated YAML into a real `terraform plan` against the actual downloaded `nxos` provider schema -- succeeded cleanly (5 resources to add, no schema errors). **Explicitly deferred, not a gap glossed over:** no Nexus 9Kv (or equivalent NX-OS simulator) exists in this lab, so `terraform apply` and pyATS validation cannot run yet -- `pipelines/evpn.gitlab-ci.yml` is deliberately not wired into the root pipeline until one exists, to avoid every commit's pipeline failing against an unreachable device.

Domain coverage (a separate axis from the milestones above — see [ADR-020](knowledge/adr/ADR-020-ACI-Domain-Coverage-Expansion.md) and [`Execution-Framework.md` §7](knowledge/architecture/Execution-Framework.md)) is **complete as of 2026-07-29**: VRF/BD attribute depth, Application Profiles/EPGs, Contracts/Filters/Subjects, L3Out, and Access/Fabric Policies (VLAN Pools, Physical Domains, AEPs, Leaf Interface Policy Groups) are all implemented, unit-tested, and live-verified. L3Out and Access Policies are logical-only (no physical interface/OSPF/BGP attachment) — a permanent limitation of this lab's ACI simulator (confirmed via direct APIC API queries: no real leaf/spine interface data exists), not a gap in the generator/Terraform pattern. The MCP Server's tool catalogue has been widened to match Phase A: `create_vrf`/`create_bridge_domain`/`create_epg`/`create_contract`/`create_l3out` (2026-07-29) — Access/Fabric Policy tools (Phase B) remain a future addition.

The old Platform API (`main.py`, `execution_store.py`, `approval_workflow.py`, `terraform_executor.py`, `nautobot_store.py`) is **legacy (Platform v1)**, replaced (not migrated) per [ADR-016](knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md) — do not extend it.
