---
title: "Network Platform Engineering Platform"
description: "Repository entry point for the Network Platform Engineering Platform — automated, validated, AI-augmented network infrastructure management."
---

# Network Platform Engineering Platform

A reusable engineering control plane that manages network infrastructure through declarative intent, automated provisioning, continuous validation, and AI-assisted workflows.

**Current focus:** Cisco ACI vertical slice — Nautobot → NetAsCode YAML → GitLab CI → Terraform → Ansible → pyATS → Nautobot/MinIO knowledge capture

**Status (2026-07-28):** the domain automation vertical slice (Nautobot generator → Terraform → Ansible → pyATS) is complete, and so are Milestones 1-4 of the [Execution Framework](knowledge/architecture/Execution-Framework.md)'s 7-stage lifecycle — a real GitLab CI pipeline now runs Validation → Policy → Approval → Execution → Verification → Knowledge Capture end-to-end against live Nautobot, the ACI simulator, and MinIO. Remaining work is Milestone 5 (MCP Server) and Milestone 6 (AI agents as MCP clients) — see [`knowledge/architecture/Execution-Framework.md` §6](knowledge/architecture/Execution-Framework.md) for the full milestone table and gate evidence, and [`knowledge/architecture/Platform-v2-As-Built.md`](knowledge/architecture/Platform-v2-As-Built.md) for the as-built infrastructure record.

---

## Start here

| First time? | Read [`knowledge/README.md`](knowledge/README.md) |
|---|---|
| Target architecture | [`knowledge/architecture/Platform-v2-Reference-Architecture.md`](knowledge/architecture/Platform-v2-Reference-Architecture.md) |
| Build order / current status | [`knowledge/architecture/Execution-Framework.md`](knowledge/architecture/Execution-Framework.md) |
| AI agent entry point | [`CLAUDE.md`](CLAUDE.md) |

`docs/` is reserved for future generated/customer-facing documentation only — it is not the knowledge base (see [`docs/README.md`](docs/README.md)).

---

## Platform flow

```
Nautobot (SoT)
    │
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
```

---

## Repository structure

```
platform/
  python/             Generator: Nautobot GraphQL → NetAsCode YAML          ✅ Done
  netascode/aci/       NetAsCode YAML — generated + committed by CI          ✅ Done
  terraform/aci/       Terraform ACI module (CiscoDevNet/aci)                ✅ Done
  ansible/aci/         Ansible Day-2 playbooks (cisco.aci)                   ✅ Done
  workflows/scripts/   Python/shell helpers backing GitLab CI jobs           ✅ Done

tests/
  pyats/aci/     pyATS validation tests                                     ✅ Done
  unit/          Generator unit tests                                       ✅ Done
  integration/   Live-lab integration smoke tests                           ✅ Done

pipelines/       GitLab CI includes (common templates + ACI domain wiring)  ✅ Done
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

---

## Technology stack

| Capability | Technology | Status |
|---|---|---|
| Source of Truth | Nautobot | ✅ Running |
| Desired State | Terraform (`CiscoDevNet/aci`) | ✅ Working |
| Day-2 Operations | Ansible (`cisco.aci`) | ✅ Working |
| Validation | pyATS (`rest.connector`) | ✅ Working |
| Secrets | HashiCorp Vault | ✅ Running |
| Execution Engine | GitLab CE + Runner | ✅ Running — Execution Framework Milestones 1-4 complete |
| Policy | OPA (Rego) | ✅ Working — `policy_check` CI job |
| Observability | Prometheus + Grafana + Loki | ✅ Deployed (scrape targets for Nautobot/platform-api not yet wired — see `Platform-v2-As-Built.md` §3) |
| Knowledge Capture | MinIO (S3-compatible JSONL log) | ✅ Working |
| Platform API (legacy v1) | FastAPI + OPA | ❌ Superseded by GitLab CI + MCP Server per ADR-016 — do not extend |
| MCP Server | — | ❌ Not started (Milestone 5) |
| AI Agents | Claude Desktop / Copilot / LangGraph | ❌ Not started (Milestone 6) |
