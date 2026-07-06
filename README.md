---
title: "Network Platform Engineering Platform"
description: "Repository entry point for the Network Platform Engineering Platform — automated, validated, AI-augmented network infrastructure management."
---

# Network Platform Engineering Platform

A reusable engineering control plane that manages network infrastructure through declarative intent, automated provisioning, continuous validation, and AI-assisted workflows.

**Current focus:** Cisco ACI vertical slice — Nautobot → NetAsCode YAML → Terraform → Ansible → pyATS

**Status (2026-07-04):** the vertical slice is complete end-to-end (Phases 1-5). Remaining work is generator unit tests (Phase 6) and CI (Phase 7). See [`docs/01-Vision/01-Current-State.md`](docs/01-Vision/01-Current-State.md) for the full status.

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
  python/        Generator: Nautobot GraphQL → NetAsCode YAML          ✅ Phase 2
  netascode/aci/ NetAsCode YAML (generated, gitignored)
  terraform/aci/ Terraform ACI module (CiscoDevNet/aci)                ✅ Phase 3
  ansible/aci/   Ansible Day-2 playbooks (cisco.aci)                   ✅ Phase 4

tests/
  pyats/aci/     pyATS validation tests                                ✅ Phase 5
  unit/          Generator unit tests                                  ⏳ Phase 6

docs/            Architecture, ADRs, operations guides
lab/             Local lab environment
  docker/nautobot/      Nautobot stack (nested git repo)
  docker/vault/         HashiCorp Vault — standalone stack, running
  docker/platform-api/  Platform API (FastAPI) + OPA sidecar — Vertical Slice v0.1, Milestones 1-3
```

Full canonical layout: [`docs/folder structure`](docs/folder%20structure)

---

## Nautobot lab

| URL | `http://localhost:8080` |
|---|---|
| Admin | `admin` / `admin` |
| API token | `0123456789abcdef0123456789abcdef01234567` |
| ACI Simulator | `https://172.30.46.103` |

Start the lab (three independent Compose stacks — see [`docs/folder structure`](docs/folder%20structure) for why they're kept separate):

```bash
# Nautobot (nested git repo; managed via its own invoke tasks)
cd lab/docker/nautobot && invoke start

# HashiCorp Vault (secrets — populates itself on first start)
cd lab/docker/vault && docker compose up -d

# Platform API — SubmitIntent, Technical Policy, RequestDeployment (needs NAUTOBOT_TOKEN, see lab/README.md)
export NAUTOBOT_TOKEN=0123456789abcdef0123456789abcdef01234567
cd lab/docker/platform-api && docker compose up -d
```

---

## Quick start — run the full vertical slice

All three tools read credentials from Vault at runtime — no hardcoded secrets.

```bash
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=<token>   # see lab/docker/vault/state/vault-keys.txt (gitignored)

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

| Capability | Technology | Status |
|---|---|---|
| Source of Truth | Nautobot | ✅ Running |
| Desired State | Terraform (`CiscoDevNet/aci`) | ✅ Working |
| Day-2 Operations | Ansible (`cisco.aci`) | ✅ Working |
| Validation | pyATS (`rest.connector`) | ✅ Working |
| Secrets | HashiCorp Vault | ✅ Running |
| Platform API | FastAPI + OPA | 🟡 Milestones 1-3 done — SubmitIntent, Technical Policy, RequestDeployment through STABLE (stubs); no auth/RBAC/Business Approval yet |
| Orchestration | n8n | ❌ Future |
| Observability | Prometheus + Grafana + Loki | ❌ Future |
| CI/CD | GitHub Actions | ❌ Future |
