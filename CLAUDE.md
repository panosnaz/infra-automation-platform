---
title: "AI Agent Instructions — Network Platform Engineering Platform"
description: "Entry point and operating instructions for AI coding agents working in this repository."
---

# AI Agent Instructions

This file provides context and operating instructions for AI agents (Claude, GitHub Copilot, etc.) working in this repository.

---

## What is this repository?

The **Network Platform Engineering Platform** automates network infrastructure through a common engineering framework. It currently covers two domains — Cisco ACI and Cisco Nexus VXLAN EVPN — and is designed to expand to further domains the same way.

**Do not** treat this as an ACI-only project. EVPN (Cisco Nexus VXLAN) already proves the platform's mechanism generalizes to a different vendor/protocol with zero shared-pipeline-logic changes — see [ADR-021](knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md). Every design decision is made with multi-domain reuse in mind.

---

## Read these files first

Before making any changes, read in order:

1. [`README.md`](README.md) — project overview and quick start
2. [`knowledge/README.md`](knowledge/README.md) — knowledge base map (architecture, ADRs, runbooks, AI notes)
3. [`knowledge/architecture/Platform-v2-Reference-Architecture.md`](knowledge/architecture/Platform-v2-Reference-Architecture.md) — the approved target architecture (MCP Server + Nautobot + GitLab)
4. [`knowledge/adr/ADR-019-Three-Truths-Principle.md`](knowledge/adr/ADR-019-Three-Truths-Principle.md) — the core conceptual model (Business Intent / Desired State / Observed State) underpinning every other design decision
5. [`knowledge/adr/ADR-018-NetAsCode-Centric-Execution-Framework.md`](knowledge/adr/ADR-018-NetAsCode-Centric-Execution-Framework.md) — why NetAsCode YAML, not an MCP-owned schema, is the authoritative intent artifact
6. [`knowledge/architecture/Execution-Framework.md`](knowledge/architecture/Execution-Framework.md) — the 7-stage lifecycle and the current build milestones (§6) — this is the actual build order and status tracker
7. [`knowledge/adr/ADR-020-ACI-Domain-Coverage-Expansion.md`](knowledge/adr/ADR-020-ACI-Domain-Coverage-Expansion.md) and [`knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md`](knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md) — what's actually implemented today for each of the two live domains (ACI and EVPN)
8. [`knowledge/architecture/Platform-Status-and-Pending-Items.md`](knowledge/architecture/Platform-Status-and-Pending-Items.md) — current status, known pending items, and hard-won operational lessons — check this before starting new work (supersedes `Current-State.md`, which is stale)
9. [`Platform-Administration-Guide.md`](Platform-Administration-Guide.md) — operational reference for every running container (ports, credentials, restart/troubleshooting procedures) — read before touching `docker compose` in this repo
10. Relevant ADRs in [`knowledge/adr/`](knowledge/adr/) for the specific capability you are changing (`knowledge/adr/archive/` holds ADRs superseded by [ADR-016](knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md))

---

## Definition of Done

Reading the files above tells you how to *make* a change. This section is what makes it *finished*. It exists because between 2026-09-08 and 2026-09-12, 22 of 31 commits touched no documentation at all and the MCP tool catalogue silently grew from 18 to 48 while every document still said 18. The discipline had been carried entirely by work being shaped as "ADR-020 Phase X" increments; the moment work became live debugging, nothing prompted it.

When you add or change a capability, you must **also**:

1. **Add or extend unit tests.** A new MCP tool needs **both** a schema-validation test in `mcp-server/tests/unit/test_schemas_aci.py` *and* a dispatch test in `test_tools_aci.py`. A generator change needs a positive *and* a negative test in `tests/unit/test_transformer.py` (the negative one asserts the key is absent when the Custom Field is unset — that rule is easy to break silently). Watch a new test fail before you make it pass.
2. **Declare any new Nautobot Custom Field in `platform/workflows/scripts/bootstrap_nautobot.py`, and run it, before writing to the field.** Writes to an undeclared field are silently discarded by the REST serializer — HTTP 200, no error, no data. On 2026-09-15 an entire L4-L7/PBR lab was built through the MCP tools, every call reported success, and nothing persisted. The script is the authoritative schema (32 fields today); `--verify` checks any environment without changing it, and `tests/unit/test_bootstrap_nautobot.py` fails if you add a field to the code without declaring it there.
3. **Attempt live verification, and say so either way.** Actually run it: a new MCP tool over the real MCP protocol against live Nautobot; a new or changed Terraform module against the real APIC — `plan`, then `apply` and `destroy` where that is safe on a throwaway object. Note that this simulator **accepts** configuration for switches that do not exist (relations simply sit at `state: unformed`), so far more is live-verifiable here than the older "permanently blocked by simulator" notes claim — verify before assuming a blocker. If live verification genuinely is not feasible, write down *why*, rather than silently downgrading the claim to a plan. **Live verification must include an APIC fault check** — run `platform/workflows/scripts/check_apic_faults.py --snapshot` before and `--compare` after. Object existence plus `state: formed` is NOT sufficient: APIC accepts configuration it then marks invalid, deploying nothing, and Terraform reports success either way. On 2026-09-15 an apply verified that way was found to have left 11 faults and an invalid L4-L7 device.
4. **Record it in the relevant ADR** — [ADR-020](knowledge/adr/ADR-020-ACI-Domain-Coverage-Expansion.md) for ACI, [ADR-021](knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md) for EVPN.
5. **Update [`Platform-Status-and-Pending-Items.md`](knowledge/architecture/Platform-Status-and-Pending-Items.md)**, and the tool catalogue in ADR-020 if you added an MCP tool.
6. **Declare the evidence level in code, not only in prose.** A new MCP tool passes `evidence=` to `registry.register()` — `unit-tested` (the default), `plan-verified`, or `live-verified`, the last requiring an `evidence_note` saying how. Terraform resources and fixtures that are not live-verified carry an `# EVIDENCE:` comment; find them all with `grep -rn "EVIDENCE:" platform/terraform/`. The default is deliberately the weakest claim, so forgetting understates rather than overstates. `tests/unit/test_registry.py` fails if a tool declares an invalid level, claims `live-verified` without a note, or if the live/unit counts drift from what `Platform-Status-and-Pending-Items.md` documents.
7. **State the evidence level explicitly, and never imply more than was proven.** `unit-tested`, `plan-verified`, and `live-verified (apply + destroy)` are three different claims. This is the one that keeps being lost: a clean `terraform plan` validates against the provider schema only, never against live APIC state, and treating "plan-verified" as "works" is what caused an applicable feature set to be recorded as permanently blocked.

**Verifying a claim before you write it down.** A clean plan is not evidence a resource was produced — count it: `terraform plan ... | grep -c '<resource_type>'`. An OSPF fixture once planned cleanly while producing zero `aci_l3out_ospf_interface_profile` resources, and nobody noticed because the plan succeeded.

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

## Standing up a new environment

Nautobot needs its schema declared before any MCP tool can persist anything. On a **fresh Nautobot** (a customer site, or a rebuilt container) run this first:

```bash
export NAUTOBOT_URL=... NAUTOBOT_TOKEN=...

# check without changing anything — safe to run anywhere, anytime
python platform/workflows/scripts/bootstrap_nautobot.py --verify

# create whatever is missing (idempotent; re-running is a no-op)
python platform/workflows/scripts/bootstrap_nautobot.py --location "Customer DC1"
```

Without it the tools report success and write nothing — see Definition of Done item 2. To rebuild a fabric from Nautobot (wipe the APIC, regenerate, re-apply), follow [`knowledge/runbooks/Demo-Rebuild-From-Nautobot.md`](knowledge/runbooks/Demo-Rebuild-From-Nautobot.md).

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

**Domain Expansion Phase 2 — VXLAN EVPN ([ADR-021](knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md)):** the first domain expansion beyond ACI, proving the Execution Framework's mechanism generalizes with zero shared-pipeline-logic changes. Built the Terraform module (`platform/terraform/evpn/`, real `CiscoDevNet/nxos` provider), Nautobot Custom Fields, `pipelines/evpn.gitlab-ci.yml`, and 3 MCP tools. A real CML lab with 4 genuine Nexus 9000v devices was found and used. All 4 devices (`DC1-Leaf`, `DC1-BGW`, `DC2-Leaf`, `DC2-BGW`) have a proven, live `terraform apply` cycle against real hardware via a CML jump-host relay mechanism (the GitLab Runner has no direct network path to the devices), with Terraform state persisting correctly across pipeline runs (ADR-021 §22), real BGP/EVPN peer sessions established fabric-wide (§23), and pyATS-equivalent verification live-verified with no `genie` dependency (§19). **`pipelines/evpn.gitlab-ci.yml` is now included from the root `.gitlab-ci.yml` alongside ACI's** (§20, 2026-08-26) — see [`Platform-Status-and-Pending-Items.md`](knowledge/architecture/Platform-Status-and-Pending-Items.md) for the current, exact state of what's still open.

Domain coverage (a separate axis from the milestones above — see [ADR-020](knowledge/adr/ADR-020-ACI-Domain-Coverage-Expansion.md) and [`Execution-Framework.md` §7](knowledge/architecture/Execution-Framework.md)) is **complete as of 2026-07-29**: VRF/BD attribute depth, Application Profiles/EPGs, Contracts/Filters/Subjects, L3Out, and Access/Fabric Policies (VLAN Pools, Physical Domains, AEPs, Leaf Interface Policy Groups) are all implemented, unit-tested, and live-verified. L3Out and Access Policies are logical-only (no physical interface/OSPF/BGP attachment) — a permanent limitation of this lab's ACI simulator (confirmed via direct APIC API queries: no real leaf/spine interface data exists), not a gap in the generator/Terraform pattern. The MCP Server's tool catalogue has been widened to match Phase A: `create_vrf`/`create_bridge_domain`/`create_epg`/`create_contract`/`create_l3out` (2026-07-29). **Phase B's Access/Fabric Policy tools now exist too (2026-09-01)**: `create_vlan_pool`/`create_physical_domain`/`create_aep`/`create_leaf_interface_policy_group`, unit-tested (schema validation + tool dispatch), not yet live-verified over the real MCP protocol against a running pipeline. **Phases D-G (VMM Domain/EPG-domain-binding, further Fabric Policies, RBAC, Syslog/Fault) are complete and live-verified (2026-09-04)**; **Phases H-J (L4-L7/PBR/Service Graph, VRF route-leak, protocol L3Out/remaining access-policy tools), ported from `copilot/aci-platform-comparison` and merged 2026-09-08, HAVE now been applied (2026-09-15/16) — but read the evidence before assuming any of it works.** The access-policy and protocol-L3Out scope applied with zero new faults; the L4-L7/PBR scope applied and APIC then flagged the device and graph **invalid** (10 faults, `vnsConfIssue-missing-cdev`, which is the floor without a vCenter); VRF route-leak still has no apply at all. **L3Out Logical Interface Profile sub-policies (ND / DPP / PIM / IGMP / Custom QoS / QoS priority) were added 2026-09-16 and are live-verified apply+destroy.** Per-tool and per-scope status lives in [`Evidence-Matrix.md`](knowledge/architecture/Evidence-Matrix.md) — see ADR-020 and [`Platform-Status-and-Pending-Items.md`](knowledge/architecture/Platform-Status-and-Pending-Items.md) before assuming any of it is live-ready.

The old Platform API (`main.py`, `execution_store.py`, `approval_workflow.py`, `terraform_executor.py`, `nautobot_store.py`) is **legacy (Platform v1)**, replaced (not migrated) per [ADR-016](knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md) — do not extend it.
