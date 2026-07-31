---
title: "Network Platform Engineering Platform"
description: "Repository entry point for the Network Platform Engineering Platform — automated, validated, AI-augmented network infrastructure management."
---

# Network Platform Engineering Platform

A reusable engineering control plane that manages network infrastructure through declarative intent, automated provisioning, continuous validation, and AI-assisted workflows.

**Current focus:** two network domains on one shared automation pipeline — Cisco ACI (Nautobot → NetAsCode YAML → GitLab CI → Terraform → Ansible → pyATS → Nautobot/MinIO knowledge capture) and Cisco Nexus VXLAN EVPN (same pipeline mechanism, proven against real Nexus 9000v hardware).

**Status (2026-07-31):** all 6 milestones of the [Execution Framework](knowledge/architecture/Execution-Framework.md)'s 7-stage lifecycle are complete for ACI. The MCP Server (`mcp-server/`) is live and callable over the real MCP protocol (`create_tenant`, `create_vrf`, `create_bridge_domain`, `create_epg`, `create_contract`, `create_l3out`, `show_status`), and the VS Code Copilot Agent is wired as a real MCP client (`.vscode/mcp.json`) that has completed a full natural-language-driven business operation end-to-end with no manual pipeline triggering. See [`knowledge/architecture/Execution-Framework.md` §6](knowledge/architecture/Execution-Framework.md) for the full milestone table and gate evidence, and [`knowledge/architecture/Platform-v2-As-Built.md`](knowledge/architecture/Platform-v2-As-Built.md) for the as-built infrastructure record.

**EVPN, the platform's second domain** ([ADR-021](knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md)), proves the same generator → Terraform → Ansible → pyATS mechanism works for a completely different vendor/protocol without any changes to the pipeline logic itself — only new domain-specific files, exactly as designed. It has been live-verified against 4 real Cisco Nexus 9000v devices (not a simulator): every device now has a proven `terraform apply` cycle, and pyATS tests are written and validated. What's still open: wiring EVPN's pipeline into the root GitLab pipeline needs the lab's devices to be reachable from wherever the pipeline actually runs, which isn't the case yet in this lab environment — see [`knowledge/architecture/Platform-Status-and-Pending-Items.md`](knowledge/architecture/Platform-Status-and-Pending-Items.md) for the current, honest state of that work.

---

## Start here

**New to this project? Read in this order:**

1. [`README.md`](README.md) — this file: what the project is, the platform flow, how to run it
2. [`knowledge/README.md`](knowledge/README.md) — map of the knowledge base (architecture, ADRs, runbooks) and the rules for how it's organized
3. [`knowledge/architecture/Platform-v2-Reference-Architecture.md`](knowledge/architecture/Platform-v2-Reference-Architecture.md) — the target architecture and its non-negotiable design principles (MCP Server, Nautobot, GitLab roles)
4. [`knowledge/adr/ADR-019-Three-Truths-Principle.md`](knowledge/adr/ADR-019-Three-Truths-Principle.md) — the core conceptual model: Business Intent / Desired State / Observed State are three distinct truths, never conflated. This explains *why* the platform is split the way it is.
5. [`knowledge/adr/ADR-018-NetAsCode-Centric-Execution-Framework.md`](knowledge/adr/ADR-018-NetAsCode-Centric-Execution-Framework.md) — why NetAsCode YAML (not a custom MCP-owned schema) is the one artifact Terraform consumes
6. [`knowledge/architecture/Execution-Framework.md`](knowledge/architecture/Execution-Framework.md) — the 7-stage lifecycle (Intent → Validation → Policy → Approval → Execution → Verification → Knowledge Capture), the 6 build milestones, and current status/gate evidence
7. [`knowledge/adr/ADR-020-ACI-Domain-Coverage-Expansion.md`](knowledge/adr/ADR-020-ACI-Domain-Coverage-Expansion.md) — what's actually implemented today for ACI (Tenant/VRF/BD/EPG/Contract/L3Out) versus roadmap
8. [`knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md`](knowledge/adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md) — the platform's second domain (Cisco Nexus VXLAN EVPN), proving the same pipeline mechanism works for a different vendor/protocol with no pipeline logic changes
9. [`knowledge/architecture/Platform-Status-and-Pending-Items.md`](knowledge/architecture/Platform-Status-and-Pending-Items.md) — current status, known pending items, and hard-won operational lessons — check this before starting new work
10. [`Platform-Administration-Guide.md`](Platform-Administration-Guide.md) — once the design makes sense, this is how to actually run it day-to-day (every container, credentials, troubleshooting)

Other ADRs in [`knowledge/adr/`](knowledge/adr/) go deeper on individual decisions (Terraform's role, Ansible's role, secrets management, policy enforcement, etc.) — read the specific one relevant to what you're changing, once the above gives you the overall shape.

**AI coding agent?** Read [`CLAUDE.md`](CLAUDE.md) instead/first — it has agent-specific operating instructions layered on top of this same reading order.

`docs/` is reserved for future generated/customer-facing documentation only — it is not the knowledge base (see [`docs/README.md`](docs/README.md)).

---

## Platform flow

How this actually gets used: a person (or an AI agent acting on their behalf) makes a natural-language request. The AI agent decides which MCP tool to call and calls it; everything after that is native automation the agent never touches directly.

```
User (natural language, e.g. "create a VRF for the finance tenant")
    │
    ▼  AI agent (VS Code Copilot Agent / Claude Desktop) picks a tool + arguments
    ▼  MCP tool call (create_tenant / create_vrf / create_bridge_domain / create_epg / create_contract / create_l3out)
MCP Server (mcp-server/, validates input, writes to Nautobot)
    │
    ▼  structured write (Tenant / VRF / Prefix, etc.)
Nautobot (SoT)
    │
    ▼  webhook fires automatically → triggers GitLab pipeline (no MCP involvement)
    ▼  generate_nac (platform/python/generate_aci.py, GitLab CI)
NetAsCode YAML  (platform/netascode/aci/, committed by CI)
    │
    ▼  policy_check (OPA) → manual approval gate
    ▼  terraform apply
Cisco ACI (APIC)
    │
    ▼  ansible-playbook
Day-2 operations
    │
    ▼  pyats run job
Continuous validation
    │
    ▼  write_results / knowledge_capture
Nautobot status write-back + MinIO/JSONL knowledge record
    │
    ▼  AI agent calls show_status → merges Nautobot custom_fields + live GitLab pipeline status
User sees the result in plain language
```

The MCP Server never sequences the pipeline itself — it only writes to Nautobot and later reads status back. Nautobot's own webhook is what starts the pipeline; GitLab is what runs it. See [Platform-v2-Reference-Architecture.md](knowledge/architecture/Platform-v2-Reference-Architecture.md) for the full design rationale.

---

## Repository structure

```
platform/
  python/              Generator: Nautobot GraphQL → NetAsCode YAML          ✅ Done (both domains)
  netascode/aci/       NetAsCode YAML — generated + committed by CI          ✅ Done
  netascode/evpn/      NetAsCode YAML for the EVPN domain                    ✅ Done
  terraform/aci/       Terraform ACI module (CiscoDevNet/aci)                ✅ Done
  terraform/evpn/      Terraform EVPN module (CiscoDevNet/nxos)              ✅ Live-verified, ADR-021
  ansible/aci/         Ansible Day-2 playbooks (cisco.aci)                   ✅ Done
  ansible/evpn/        Ansible Day-2 playbooks for EVPN                      ✅ Done
  workflows/scripts/   Python/shell helpers backing GitLab CI jobs           ✅ Done

tests/
  pyats/aci/     pyATS validation tests (ACI)                                ✅ Done
  pyats/evpn/    pyATS validation tests (EVPN)                               ✅ Done
  unit/          Generator unit tests                                        ✅ Done
  integration/   Live-lab integration smoke tests                            ✅ Done

pipelines/       GitLab CI includes (common templates + one file per domain) ✅ ACI wired in; EVPN written but not yet wired (see Platform-Status-and-Pending-Items.md)
knowledge/       Architecture, ADRs, runbooks, AI notes — the knowledge base
docs/            Reserved for future generated/customer-facing docs (empty today)
docker/          All lab infrastructure: Nautobot, Vault, GitLab CE + Runner,
                 OPA, Prometheus/Grafana/Loki, MinIO, Traefik — each its own
                 Compose stack (see docker/README.md)
```

---

## Active lab

| Service | URL | Notes |
|---|---|---|
| Nautobot | `http://localhost:8080` | admin/admin, API token `0123456789abcdef0123456789abcdef01234567` |
| GitLab CE | `http://localhost:8929` / `http://gitlab.local:8929` | project `root/nautobot-infra-automation` — the execution engine |
| HashiCorp Vault | `http://localhost:8200` | root token in `docker/vault/state/vault-keys.txt` (gitignored) |
| MinIO | `http://localhost:9000` | bucket `knowledge-capture` — durable Knowledge Capture log |
| ACI Simulator | `https://172.30.46.103` | self-signed cert, use `--no-verify` |

Start the lab (each service is its own independent Compose stack under `docker/` — see `docker/README.md` for why they're kept separate and for full per-service startup commands):

```bash
# Nautobot (nested git repo; managed via its own invoke tasks)
cd docker/nautobot && invoke start

# HashiCorp Vault (secrets — populates itself on first start)
cd docker/vault && docker compose up -d

# GitLab CE + Runner, Prometheus/Grafana/Loki, MinIO, Traefik — see docker/README.md
```

---

## Quick start — run the vertical slice manually (without GitLab CI)

All tools read credentials from Vault at runtime — no hardcoded secrets. This is the same domain automation the GitLab CI pipeline runs automatically end-to-end; running it manually is useful for local development.

```bash
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=<token>   # see docker/vault/state/vault-keys.txt (gitignored)

# 1. Generate NetAsCode YAML from Nautobot
pip install -r platform/python/requirements.txt
python platform/python/generate_aci.py \
  --vault-addr "$VAULT_ADDR" --vault-token "$VAULT_TOKEN" \
  --include-system-tenants

# 2. Provision with Terraform
cd platform/terraform/aci
source scripts/load-vault-creds.sh
terraform init && terraform apply
cd -

# 3. Day-2 operations with Ansible
cd platform/ansible/aci
ansible-playbook -i inventory/hosts.yml playbooks/verify-tenants.yml
ansible-playbook -i inventory/hosts.yml playbooks/day2-epg.yml
cd -

# 4. Independent validation with pyATS
cd tests/pyats
source aci/scripts/load-vault-env.sh
pyats run job aci/job.py --testbed-file aci/testbed.yml --no-mail
cd -
```

To run the real, automated end-to-end pipeline instead, push to the `main` branch of the local GitLab project — see [`knowledge/architecture/Execution-Framework.md`](knowledge/architecture/Execution-Framework.md) for the full stage design.

---

## Architecture decisions

All decisions are recorded as ADRs in [`knowledge/adr/`](knowledge/adr/) (`knowledge/adr/archive/` holds ADRs superseded by [ADR-016](knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md)'s Platform v2 replacement decision):

| ADR | Decision |
|---|---|
| ADR-001 | Nautobot as the authoritative Source of Truth |
| ADR-002 | Terraform owns desired-state provisioning |
| ADR-003 | Ansible owns Day-2 operations |
| ADR-007 | Cisco NetAsCode as the canonical engineering model |
| ADR-008 | Validation as an independent platform capability |
| ADR-016 | Platform v2 replacement — MCP Server + Nautobot + GitLab replaces the custom Platform API |
| ADR-017 | Execution Framework — the 7-stage lifecycle (Intent → Validation → Policy → Approval → Execution → Verification → Knowledge Capture) |
| ADR-018 | NetAsCode YAML (not a shared intent schema) is the Execution Framework's authoritative intent artifact |
| ADR-019 | Three Truths principle — Business Intent / Desired State / Execution History are distinct, separately owned truths |
| ADR-020 | ACI domain coverage expansion — VRF/Bridge-Domain depth, Application Profiles/EPGs, Contracts, L3Out, Access/Fabric Policies |
| ADR-021 | VXLAN EVPN domain expansion — proves the Execution Framework's mechanism generalizes to a second vendor/protocol, live-verified against real Cisco Nexus 9000v hardware |

---

## Technology stack

| Capability | Technology | Status |
|---|---|---|
| Source of Truth | Nautobot | ✅ Running |
| Desired State | Terraform (`CiscoDevNet/aci`) | ✅ Working |
| Day-2 Operations | Ansible (`cisco.aci`) | ✅ Working |
| Validation | pyATS (`rest.connector`) | ✅ Working |
| Secrets | HashiCorp Vault | ✅ Running |
| Execution Engine | GitLab CE + Runner | ✅ Running — all 6 Execution Framework milestones complete for ACI |
| Policy | OPA (Rego) | ✅ Working — `policy_check` CI job |
| Observability | Prometheus + Grafana + Loki | ✅ Deployed (scrape targets for Nautobot/platform-api not yet wired — see `Platform-v2-As-Built.md` §3) |
| Knowledge Capture | MinIO (S3-compatible JSONL log) | ✅ Working |
| Platform API (legacy v1) | FastAPI + OPA | ❌ Superseded by GitLab CI + MCP Server per ADR-016 — archived, do not extend |
| MCP Server | Python, `mcp` library | ✅ Live — callable over the real MCP protocol |
| AI Agents | VS Code Copilot Agent | ✅ Live — a real MCP client, completes full business operations end-to-end |
| Second domain (EVPN) | Terraform (`CiscoDevNet/nxos`), same pipeline | ✅ Live-verified against real Nexus 9000v hardware — see ADR-021 |
