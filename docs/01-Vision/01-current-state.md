# 01 – Current State

**Project:** Network Platform Engineering Platform

**Document Type:** Current State Assessment

**Status:** Live — updated 2026-07-01

**Owner:** Platform Engineering Team

---

# Purpose

This document describes the current state of the Network Platform Engineering Platform as of July 2026.

It captures what exists today, what has been implemented, what is still pending, and where the gaps are relative to the target architecture described in [`02-target-architecture.md`](02-target-architecture.md).

This document should be updated whenever the platform state changes significantly.

---

# Starting Point

Before this project, ACI configuration was managed through an ad-hoc workflow:

- Infrastructure intent was stored in **Excel spreadsheets**.
- A Python script transformed Excel data into YAML variable files.
- **Ansible playbooks** consumed those YAML files to configure ACI directly.
- No authoritative Source of Truth existed outside the spreadsheets.
- No validation framework existed.
- No drift detection existed.
- The workflow was manual, undocumented, and difficult to extend.

This platform replaces that workflow with a governed, declarative, validated engineering pipeline.

---

# Current Infrastructure State

## Nautobot (Source of Truth)

| Property | Value |
|---|---|
| Status | **Running** |
| URL | `http://localhost:8080` |
| Version | Nautobot 2.x |
| Deployment | Docker Compose — `lab/docker/nautobot/` |
| Plugin | `nautobot-ssot` with `enable_aci: True` |
| API Token | `0123456789abcdef0123456789abcdef01234567` |

The Nautobot ACI SSoT plugin has been configured and the initial sync from the ACI simulator has been completed.

### Populated objects

| Object type | Count | Notes |
|---|---|---|
| Tenants | 3 | `ACI:common`, `ACI:infra`, `ACI:mgmt` |
| VRFs | 6 | `copy`, `default` (common); `ave-ctrl`, `overlay-1` (infra); `inb`, `oob` (mgmt) |
| Prefixes | 2 | `10.0.0.0/27` (BD: default, VRF: overlay-1, tenant: infra); `172.30.46.0/24` (VRF: oob, tenant: mgmt) |
| Devices | 1 | `apic1` — ACI APIC controller |
| Total objects | ~48 | All from the ACI SSoT sync |

All tenants currently in Nautobot are ACI system tenants (`common`, `infra`, `mgmt`) because the ACI simulator contains only the default fabric objects. User-defined tenants will be added as the lab is extended.

All tenant names carry an `ACI:` namespace prefix added by the SSoT plugin (e.g. `ACI:infra`). The generator strips this prefix before writing NetAsCode YAML.

## ACI Simulator

| Property | Value |
|---|---|
| Status | **Running** |
| URL | `https://172.30.46.103` |
| TLS | Self-signed certificate — use `--no-verify` / `insecure = true` |
| Contents | Default system tenants only (`common`, `infra`, `mgmt`) |

The ACI simulator is a Cisco APIC development appliance. It represents the target infrastructure for the vertical slice.

## HashiCorp Vault (Secrets Management)

| Property | Value |
|---|
| Status | **Running** |
| URL | `http://localhost:8200` |
| UI | `http://localhost:8200/ui` |
| Version | 1.17.6 |
| Deployment | Docker Compose — `lab/docker/nautobot/environments/docker-compose.vault.yml` |
| Storage | File backend — Docker volume `infra-automation-lab_vault_data` |
| Mode | Single-node, file storage, TLS disabled (lab only) |
| Root token | See `lab/docker/nautobot/environments/vault/state/vault-keys.txt` (gitignored) |

Vault is fully integrated into the existing Nautobot Docker Compose stack. On first start the entrypoint script auto-initialises, unseals, and populates all lab credentials into the KV v2 engine at `secret/`.

### Stored secrets

| Vault path | Keys | Purpose |
|---|---|---|
| `secret/lab/nautobot` | `db_password`, `redis_password`, `secret_key`, `superuser_password`, `superuser_api_token` | Nautobot service credentials |
| `secret/lab/aci` | `username`, `password`, `url`, `insecure` | ACI simulator credentials |
| `secret/lab/platform` | `nautobot_url`, `nautobot_api_token`, `aci_url`, `aci_username`, `aci_password` | Combined credentials for platform tooling (Terraform, generator, Ansible, pyATS) |

## Phase 1 — Repository scaffold ✅ Complete

The repository structure follows the canonical layout defined in [`docs/folder structure`](../folder%20structure).

Key directories established:

| Directory | Purpose |
|---|---|
| `platform/python/` | Generator (Nautobot → NetAsCode YAML) |
| `platform/terraform/aci/` | Terraform ACI module (empty — Phase 3) |
| `platform/ansible/aci/` | Ansible Day-2 playbooks (empty — Phase 4) |
| `platform/netascode/aci/` | Generated YAML output (gitignored) |
| `tests/pyats/aci/` | pyATS validation tests (empty — Phase 5) |
| `docs/` | Architecture, ADRs, operations guides |

## Phase 2 — Nautobot → NetAsCode Generator ✅ Complete

A working Python generator translates Nautobot ACI objects into NetAsCode-compatible YAML.

| Component | Path | Status |
|---|---|---|
| Entry point | `platform/python/generate_aci.py` | ✅ Working |
| GraphQL client | `platform/python/generator/client.py` | ✅ Working |
| Transformer | `platform/python/generator/transformer.py` | ✅ Working |
| Dependencies | `platform/python/requirements.txt` | `requests>=2.31.0`, `PyYAML>=6.0.1` |

### Generator behaviour

- Queries Nautobot via GraphQL for tenants (with VRFs) and prefixes.
- Strips the `ACI:` namespace prefix from tenant names.
- Parses BD names from Nautobot prefix descriptions (`ACI Bridge Domain: <bd>:<tenant>`).
- Falls back to a sanitised CIDR string as BD name when no description is present.
- Excludes ACI system tenants (`common`, `infra`, `mgmt`) by default; include with `--include-system-tenants`.
- Writes `platform/netascode/aci/tenants.yaml` (gitignored — generated artifact).
- Optionally reads the Nautobot API token from Vault (`--vault-addr` + `--vault-token` or `VAULT_ADDR` / `VAULT_TOKEN` env vars).

### Sample output (dry-run, 2026-07-01)

```yaml
apic:
  tenants:
  - name: common
    vrfs:
    - name: copy
    - name: default
  - name: infra
    vrfs:
    - name: ave-ctrl
    - name: overlay-1
    bridge_domains:
    - name: default
      unicast_routing: true
      subnets:
      - ip: 10.0.0.0/27
        public: false
        private: true
        shared: false
      vrf: overlay-1
  - name: mgmt
    vrfs:
    - name: inb
    - name: oob
```

### Running the generator

```bash
# Install dependencies
pip install -r platform/python/requirements.txt

# Generate YAML (system tenants excluded by default)
python platform/python/generate_aci.py \
  --token 0123456789abcdef0123456789abcdef01234567

# Include ACI system tenants (required for lab — only system tenants exist)
python platform/python/generate_aci.py \
  --token 0123456789abcdef0123456789abcdef01234567 \
  --include-system-tenants

# Dry-run — print YAML without writing files
python platform/python/generate_aci.py \
  --token 0123456789abcdef0123456789abcdef01234567 \
  --dry-run

# Read token from Vault (lab stack — no --token required)
python platform/python/generate_aci.py \
  --vault-addr http://localhost:8200 \
  --vault-token $(grep "^Initial Root Token:" \
      lab/docker/nautobot/environments/vault/state/vault-keys.txt | awk '{print $NF}') \
  --include-system-tenants \
  --dry-run
```

## Phase 3 — Terraform ACI module ⏳ Pending

`platform/terraform/aci/` is an empty scaffold. No Terraform code exists yet.

This is the **critical path** item for completing the vertical slice. Nothing downstream (Ansible, pyATS, CI) can be implemented until Terraform can provision ACI objects from the generated YAML.

## Phase 4 — Ansible Day-2 ⏳ Pending

`platform/ansible/aci/` is an empty scaffold.

Ansible will own Day-2 operations (EPG creation, contract attachment, health verification) after Terraform has established the base provisioned state.

## Phase 5 — pyATS Validation ⏳ Pending

`tests/pyats/aci/` is an empty scaffold.

pyATS tests will independently verify that deployed ACI objects match engineering intent from Nautobot.

## Phase 6 — Generator unit tests ⏳ Pending

No unit tests exist for `platform/python/generator/`. The generator has been manually validated against the live Nautobot lab but has no automated regression protection.

## Phase 7 — GitHub Actions CI ⏳ Pending

`.github/` contains only a `.gitkeep`. No CI workflow has been defined.

---

# Repository State

| Property | Value |
|---|---|
| Branch | `master` |
| Commits | 4 |
| Working tree | Clean |
| Python | 3.12.3 |

| Commit | Description |
|---|---|
| `2cb7510` | docs: fix all naming inconsistencies, misplaced files, and ADR numbering |
| `7f9c06a` | feat(generator): Phase 2 — Nautobot GraphQL → NetAsCode ACI YAML generator |
| `548df21` | refactor(scaffold): align directory structure with canonical platform/ layout |
| `4a5d78e` | feat(scaffold): Phase 1 — repository structure for first vertical slice |

---

# Architecture Decisions

All 13 ADRs have been authored and accepted. They are located in [`docs/03-Decisions/`](../03-Decisions/).

| ADR | Title | Status |
|---|---|---|
| ADR-001 | Nautobot as the Authoritative Source of Truth | Accepted |
| ADR-002 | Terraform as the Declarative Provisioning Engine | Accepted |
| ADR-003 | Ansible Owns Day-2 Operations | Accepted |
| ADR-004 | Platform API as the Unified Platform Interface | Accepted |
| ADR-005 | Workflow Orchestration | Accepted |
| ADR-006 | Platform Control Plane as the Single Orchestration Layer | Accepted |
| ADR-007 | Cisco NetAsCode as the Canonical Engineering Model | Accepted |
| ADR-008 | Validation as an Independent Platform Capability | Accepted |
| ADR-009 | Knowledge Layer as the Engineering Memory of the Platform | Accepted |
| ADR-010 | AI as an Engineering Assistant | Accepted |
| ADR-011 | Event-Driven Automation | Accepted |
| ADR-012 | Centralized Secrets Management | Accepted |
| ADR-013 | Observability as a Platform Capability | Accepted |

No ADRs are superseded or deprecated.

---

# Gaps vs Target Architecture

| Capability | Target | Current State |
|---|---|---|
| Source of Truth | Nautobot | ✅ Running with ACI data |
| Intent Generation | Python generator | ✅ Working |
| Desired State Provisioning | Terraform `netascode/aci` | ❌ Not implemented |
| Day-2 Operations | Ansible `cisco.aci` | ❌ Not implemented |
| Validation | pyATS + Catfish | ❌ Not implemented |
| CI/CD Pipeline | GitHub Actions | ❌ Not implemented |
| Platform API | FastAPI | ❌ Not implemented |
| Workflow Orchestration | n8n | ❌ Not implemented |
| Secrets Management | HashiCorp Vault | ✅ Running — lab stack, file storage, KV v2 populated |
| Observability | Prometheus + Grafana + Loki | ❌ Not implemented |
| Knowledge Layer | Obsidian + Git | ❌ Not implemented |
| AI Assistance | LangGraph | ❌ Not implemented |
| Policy Validation | Open Policy Agent | ❌ Not implemented |

The immediate priority is completing the **first end-to-end vertical slice**: Nautobot → NetAsCode YAML → Terraform → Ansible → pyATS. Everything else is future scope.

---

# Next Actions

The next actions are ordered by dependency. Each item must be complete before the one that follows it.

## Immediate — Phase 3: Terraform ACI module

**This is the critical path.** Nothing downstream can proceed until Terraform can consume the generated YAML and apply it to the ACI simulator.

### Tasks

1. Create `platform/terraform/aci/providers.tf`
   - Configure `netascode/aci` provider with `url`, `username`, `password`, `insecure` variables
   - Pin provider version to `~> 0.2`

2. Create `platform/terraform/aci/variables.tf`
   - `aci_url` (default: `https://172.30.46.103`)
   - `aci_username` (default: `admin`)
   - `aci_password` (sensitive)
   - `aci_insecure` (default: `true` for lab)
   - `yaml_file` — path to generated `tenants.yaml`

3. Create `platform/terraform/aci/main.tf`
   - Read NetAsCode YAML with `yamldecode(file(var.yaml_file))`
   - Iterate tenants → `aci_tenant`
   - Iterate VRFs → `aci_vrf`
   - Iterate bridge domains → `aci_bridge_domain`
   - Iterate subnets → `aci_subnet`
   - Terraform must **not** recreate system tenants (`common`, `infra`, `mgmt`) — use `lifecycle { prevent_destroy = true }` or import them first

4. Create `platform/terraform/aci/outputs.tf` — tenant IDs and BD names
5. Create `platform/terraform/aci/terraform.tfvars.example` — placeholder values, no real credentials
6. Commit a static example YAML to `platform/netascode/aci/example-tenants.yaml` (not gitignored) so Terraform has a stable input for development when Nautobot is not running

### Validation

```bash
cd platform/terraform/aci
terraform init
terraform validate
terraform plan -var="yaml_file=../../netascode/aci/tenants.yaml"
terraform apply
```

---

## Phase 3b — End-to-end chain test

Once Terraform applies successfully, run the full Nautobot → YAML → Terraform → ACI chain:

1. `python platform/python/generate_aci.py --token <TOKEN> --include-system-tenants`
2. `terraform plan` — confirm no unexpected changes
3. `terraform apply` — confirm objects appear in ACI simulator
4. Browse ACI simulator at `https://172.30.46.103` and verify tenants, VRFs, and BDs

---

## Phase 4 — Ansible Day-2

After Terraform is working:

1. `platform/ansible/aci/inventory/hosts.yml` — ACI simulator as target
2. `platform/ansible/aci/group_vars/aci.yml` — connection vars (no hardcoded credentials)
3. `platform/ansible/aci/playbooks/verify-tenants.yml` — read-only: query ACI, assert tenants match Nautobot intent
4. `platform/ansible/aci/playbooks/day2-epg.yml` — Day-2 example: create an EPG in an existing BD
5. `platform/ansible/aci/requirements.yml` — `cisco.aci` collection

```bash
ansible-galaxy collection install -r platform/ansible/aci/requirements.yml
ansible-playbook --check platform/ansible/aci/playbooks/verify-tenants.yml
```

---

## Phase 5 — pyATS Validation

After Ansible is working:

1. `tests/pyats/aci/testbed.yml` — ACI testbed definition (simulator at `172.30.46.103`)
2. `tests/pyats/aci/test_aci_tenants.py` — connect to ACI, assert every tenant in the NetAsCode YAML exists
3. `tests/pyats/aci/test_aci_vrfs.py` — same pattern for VRFs
4. `tests/pyats/requirements.txt` — `pyats`, `pyats.contrib`

```bash
pip install -r tests/pyats/requirements.txt
pyats run job tests/pyats/aci/
```

---

## Phase 6 — Generator unit tests

Can run in parallel with Phase 3:

1. `tests/unit/test_transformer.py` — test `build_netascode_yaml()` with fixture data:
   - System tenant exclusion
   - `ACI:` prefix stripping
   - BD description parsing
   - Missing description fallback to sanitised CIDR name
2. `tests/unit/test_client.py` — mock HTTP, test error handling
3. `platform/python/requirements-dev.txt` — `pytest`, `pytest-mock`, `responses`

```bash
pip install -r platform/python/requirements-dev.txt
pytest tests/unit/
```

---

## Phase 7 — GitHub Actions CI

After Phases 3b, 5, and 6 are complete:

1. `.github/workflows/vertical-slice.yml` — jobs:
   - `lint`: `yamllint`, `terraform validate`, `ansible-lint`
   - `unit-tests`: `pytest tests/unit/`
   - `generate`: `python platform/python/generate_aci.py --dry-run`
   - `terraform-plan`: `terraform plan` (requires self-hosted runner with ACI simulator access)

---

# Pending Items

| # | Item | Phase | Priority | Blocks |
|---|---|---|---|---|
| 1 | Terraform ACI module (`providers.tf`, `variables.tf`, `main.tf`) | 3 | 🔴 Critical | Everything downstream |
| 2 | Static example YAML committed to repo | 3 | 🔴 Critical | Terraform development without live Nautobot |
| 3 | End-to-end chain test (Nautobot → YAML → Terraform → ACI) | 3b | 🔴 Critical | Ansible, pyATS |
| 4 | Generator unit tests | 6 | 🟠 High | CI |
| 5 | Ansible Day-2 playbooks (`verify-tenants`, `day2-epg`) | 4 | 🟠 High | pyATS, CI |
| 6 | pyATS ACI validation tests | 5 | 🟠 High | CI |
| 7 | GitHub Actions CI workflow | 7 | 🟡 Medium | None (vertical slice cap) |
| 8 | ACI system tenant import to Terraform state | 3 | 🟡 Medium | Avoid recreating `common`/`infra`/`mgmt` |
| 9 | `platform/netascode/aci/example-tenants.yaml` (committed) | 3 | 🟡 Medium | Static Terraform development |
| 10 | `tests/unit/` directory creation | 6 | 🟡 Medium | Unit test phase |
| 11 | Platform API (FastAPI) | Future | 🔵 Future | — |
| 12 | Workflow Orchestration (n8n) | Future | 🔵 Future | — |
| 13 | Secrets Management (HashiCorp Vault) | ✅ Done | ✅ Complete | Vault running in lab stack; KV v2 populated with all lab credentials |
| 14 | Observability stack (Prometheus, Grafana, Loki) | Future | 🔵 Future | — |
| 15 | Knowledge Layer (Obsidian + Git) | Future | 🔵 Future | — |
| 16 | AI Assistance (LangGraph) | Future | 🔵 Future | — |
| 17 | Policy Validation (OPA) | Future | 🔵 Future | — |
| 18 | Multi-domain expansion (VXLAN EVPN, Azure) | Future | 🔵 Future | — |

---

# Open Questions

| # | Question | Impact |
|---|---|---|
| Q1 | Should Terraform import the ACI system tenants into state on first run, or manage them with `lifecycle { prevent_destroy = true }`? | Determines Phase 3 approach for system tenant handling |
| Q2 | Will the ACI simulator require a specific `netascode/aci` provider version for compatibility? | Affects `providers.tf` version pin |
| Q3 | Should pyATS connect directly to the ACI APIC REST API or use the `pyats.contrib.aci` library? | Determines Phase 5 test design |
| Q4 | Should the generator output additional NetAsCode object types beyond tenants, VRFs, and BDs (e.g. EPGs, contracts, external networks)? | Scope of Phase 2 extension vs later phases |
| Q5 | When user-defined tenants are added to the ACI lab, will the generator filter them correctly without `--include-system-tenants`? | Requires lab data extension to verify |

---

# Known Constraints

- The ACI simulator contains **only system tenants**. The `--include-system-tenants` flag is required for the generator to produce any output in the current lab environment.
- The ACI simulator uses a **self-signed TLS certificate**. All tools must use `insecure = true` / `--no-verify` / `verify=False`.
- `platform/netascode/aci/tenants.yaml` is **gitignored** (generated artifact). Terraform cannot reference it from CI unless the generator runs first as a pipeline step.
- The `lab/docker/nautobot/` directory is a **nested git repository** and is excluded from this repo's tracking. It must be managed independently.
- Nautobot VRFs do not carry a `tenant` field in the REST API response by default. VRF-to-tenant association is retrieved via the `tenants.vrfs` GraphQL relationship.
