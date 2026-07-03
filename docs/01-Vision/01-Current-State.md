# 01 – Current State

**Project:** Network Platform Engineering Platform

**Document Type:** Current State Assessment

**Status:** Live — updated 2026-07-03

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
| Tenants | 4 | `ACI:common`, `ACI:infra`, `ACI:mgmt` (system); `ACI:web-tenant` (user-defined, Phase 3 vertical slice) |
| VRFs | 7 | `copy`, `default` (common); `ave-ctrl`, `overlay-1` (infra); `inb`, `oob` (mgmt); `web-vrf` (web-tenant) |
| Prefixes | 3 | `10.0.0.0/27` (BD: default, VRF: overlay-1, tenant: infra); `172.30.46.0/24` (VRF: oob, tenant: mgmt); `10.10.10.1/24` (BD: web-bd, VRF: web-vrf, tenant: web-tenant) |
| Devices | 1 | `apic1` — ACI APIC controller |
| Total objects | ~51 | ACI SSoT sync + one manually created user tenant for the Phase 3 vertical slice |

`ACI:web-tenant` was created directly via the Nautobot REST API (tenant + VRF + prefix, with a `vrf-prefix-assignments` link and an `ACI Bridge Domain: web-bd:web-tenant` description) to prove the full Nautobot → generator → Terraform → ACI chain end to end. All other tenants are ACI system tenants (`common`, `infra`, `mgmt`) present because the simulator only ships the default fabric objects.

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
| Deployment | Docker Compose — `lab/docker/vault/docker-compose.yml` (standalone stack) |
| Storage | File backend — Docker volume `infra-automation-lab_vault_data` |
| Mode | Single-node, file storage, TLS disabled (lab only) |
| Root token | See `lab/docker/vault/state/vault-keys.txt` (gitignored) |

Vault runs as a standalone Docker Compose stack independent of Nautobot (`cd lab/docker/vault && docker compose up -d`). On first start the entrypoint script auto-initialises, unseals, and populates all lab credentials into the KV v2 engine at `secret/`.

### Stored secrets

| Vault path | Keys | Purpose |
|---|---|---|
| `secret/lab/nautobot` | `db_password`, `redis_password`, `secret_key`, `superuser_password`, `superuser_api_token` | Nautobot service credentials |
| `secret/lab/aci` | `username`, `password`, `url`, `insecure` | ACI simulator credentials |
| `secret/lab/platform` | `nautobot_url`, `nautobot_api_token`, `aci_url`, `aci_username`, `aci_password` | Combined credentials for platform tooling (Terraform, generator, Ansible, pyATS) |

### Terraform now reads credentials from Vault at runtime

`platform/terraform/aci/scripts/load-vault-creds.sh` reads `secret/lab/platform` and exports `TF_VAR_aci_url` / `TF_VAR_aci_username` / `TF_VAR_aci_password` / `TF_VAR_aci_insecure` for the current shell. There is no static `terraform.tfvars` on disk — `terraform.tfvars.example` remains only as a fallback template for environments without Vault access. This closes a gap where the ACI password had briefly been hand-copied into a local (gitignored) tfvars file during Phase 3 development.

### 2026-07-03 incident — Vault container down

The Vault container was found `Exited (2)` — a stale Docker Desktop/WSL2 bind-mount reference left over from a prior Docker Desktop restart (the host files existed, but the container's mounted path pointer was broken, so the entrypoint script's `wait` on the vault server process ended and the container exited). Fixed with `docker compose down && docker compose up -d` in `lab/docker/vault/`, which recreates the container with fresh mounts. No data was lost (file-backed KV v2 volume was untouched). All three secret paths were verified readable afterward.

### 2026-07-03 cleanup — stale duplicate Vault container removed

A second, unrelated Vault container (`infra-automation-lab-vault-1`) was found stopped (`Exited (2)`, created 2026-07-01). It predated the standalone-stack refactor (commit `d2a6365`): Vault was originally wired directly into the main `infra-automation-lab` Compose project via a `docker-compose.vault.yml` inside `lab/docker/nautobot/environments/`, which was later deleted from disk when Vault was moved to its own standalone stack — but the container it had created was never cleaned up. It shared the same `infra-automation-lab_vault_data` volume as the current Vault container (so no data was at risk) plus two now-orphaned anonymous volumes (old `/vault/logs` and `/vault/file` data, not important). Removed with `docker rm infra-automation-lab-vault-1`. Confirmed via `docker compose ls -a` that the `infra-automation-lab` project's config file list no longer references the deleted `docker-compose.vault.yml`.

## Platform API (Skeleton)

| Property | Value |
|---|---|
| Status | **Running** |
| URL | `http://localhost:8000` |
| Docs | `http://localhost:8000/docs` (Swagger UI) |
| Deployment | Docker Compose — `lab/docker/platform-api/docker-compose.yml` (standalone stack, same pattern as Vault) |
| Image | `infra-automation-lab/platform-api:local` (custom built from `platform/platform-api/Dockerfile`) |

Per ADR-004 (Platform API as the Unified Platform Interface), this is a **Phase-0 skeleton** exposing interface/meta endpoints only — no authentication, RBAC, Canonical Intent handling, policy enforcement, or Event Bus publication yet. Those depend on capabilities that don't exist in the lab yet (Event Bus, n8n, a richer Canonical Intent Model), so implementing them now would be premature.

### Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness probe — always 200 if the process is up, no external dependencies |
| `GET /readiness` | Checks Vault (`/v1/sys/health`) and Nautobot reachability; 200 if both reachable, 503 otherwise |
| `GET /version` | Reports service identity and implementation phase |

The container reaches the Vault and Nautobot stacks via `host.docker.internal` (works out of the box on Docker Desktop; an `extra_hosts: host-gateway` entry is included for portability to plain Linux Docker Engine).

### Compose project layout — three separate, independent stacks

The lab now runs **three separate Docker Compose projects**, all under the `infra-automation-lab-*` container naming convention but managed independently:

| Project | Compose file(s) | Managed via |
|---|---|---|
| `infra-automation-lab` | `lab/docker/nautobot/environments/docker-compose.{base,postgres,local}.yml` | `invoke` tasks inside the nested `lab/docker/nautobot/` repo |
| `vault` | `lab/docker/vault/docker-compose.yml` | plain `docker compose` in `lab/docker/vault/` |
| `platform-api` | `lab/docker/platform-api/docker-compose.yml` | plain `docker compose` in `lab/docker/platform-api/` |

This is a deliberate choice, not an oversight: Nautobot's compose files live inside a nested git repository (`lab/docker/nautobot/`) that this repo's own conventions treat as independently managed and excluded from tracking, so new lab services are added as their own standalone stacks (the same pattern already established for Vault) rather than by editing files inside that nested repo. Merging all three into one Compose project via multiple `-f` flags was considered and rejected — each stack's relative paths (bind mounts, build contexts) are written assuming invocation from their own directory, so merging risks silently breaking them for a purely cosmetic single-project view.

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

## Phase 3 — Terraform ACI module ✅ Complete

`platform/terraform/aci/` provisions ACI objects from the generated NetAsCode YAML using the `CiscoDevNet/aci ~> 2.0` provider (not `netascode/aci` — switched during implementation for wider version support against APIC 6.2(1g)).

| Component | Path | Status |
|---|---|---|
| Provider config | `platform/terraform/aci/providers.tf` | ✅ Working |
| Variables | `platform/terraform/aci/variables.tf` | ✅ Working |
| Resources | `platform/terraform/aci/main.tf` | ✅ Working — tenants, VRFs, bridge domains, subnets |
| Outputs | `platform/terraform/aci/outputs.tf` | ✅ Working |
| Vault credential loader | `platform/terraform/aci/scripts/load-vault-creds.sh` | ✅ Working |

### Behaviour

- Parses the NetAsCode YAML with `yamldecode(file(var.netascode_yaml_file))` and builds flat `for_each` maps for VRFs, bridge domains, and subnets.
- Filters out ACI system tenants (`common`, `infra`, `mgmt`) via a `_system_tenants` local — Terraform never manages them.
- Uses `parent_dn` (not the deprecated `tenant_dn`) for VRF and Bridge Domain parenting.
- Converts Nautobot's network-address prefixes to ACI-compatible gateway IPs in the generator (see Phase 2 update below) since ACI BD subnets require a host address, not a network address.

### End-to-end vertical slice test (2026-07-03)

A user tenant (`ACI:web-tenant`, VRF `web-vrf`, prefix `10.10.10.1/24`) was created in Nautobot, run through the generator, and applied with Terraform — the first full closed-loop validation of the pipeline:

```text
Nautobot (web-tenant + web-vrf + web-bd prefix)
  -> generate_aci.py -> tenants.yaml (10.10.10.1/24)
  -> terraform apply -> ACI APIC 6.2(1g)
```

Objects created in ACI:

- `uni/tn-web-tenant`
- `uni/tn-web-tenant/ctx-web-vrf`
- `uni/tn-web-tenant/BD-web-bd`
- `uni/tn-web-tenant/BD-web-bd/subnet-[10.10.10.1/24]`

### Bugs found and fixed during the vertical slice

1. **Deprecated `tenant_dn` attribute** — replaced with `parent_dn` on `aci_vrf` and `aci_bridge_domain`.
2. **Non-ASCII characters rejected by APIC** — the tenant description contained an em-dash (`—`); APIC returned `400 invalid JSON character`. Fixed by using ASCII-only descriptions in Nautobot.
3. **Network address vs. gateway IP** — ACI requires a host address for BD subnets, not the network address Nautobot normalises prefixes to. Added `_to_gateway_ip()` to `platform/python/generator/transformer.py`, converting e.g. `10.10.10.0/24` → `10.10.10.1/24`.
4. **Terraform → Vault credentials gap** — Terraform originally read `aci_username`/`aci_password` from a hand-typed `terraform.tfvars`. Replaced with `scripts/load-vault-creds.sh`, which exports `TF_VAR_*` from `secret/lab/platform` at runtime; no static tfvars file remains on disk.

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
| Commits | 15 |
| Working tree | Clean |
| Python | 3.12.3 |

| Commit | Description |
|---|---|
| `6143592` | feat(platform-api): add Platform API skeleton container to the lab stack |
| `58d7592` | docs(vision): update current-state for Phase 3 completion and Vault fixes |
| `4fa2e6d` | fix(terraform/aci): close Terraform -> Vault credentials gap |
| `05dc803` | fix(terraform+generator): end-to-end vertical slice corrections |
| `8fbbac7` | feat(terraform/aci): add Terraform ACI module for NetAsCode YAML provisioning — Phase 3 |
| `85cb169` | docs: evolve architecture to Platform Engineering model |
| `aaaacff` | docs(vault): update current-state paths to reflect standalone lab/docker/vault/ |
| `04de7f1` | refactor(vault): move Vault to standalone lab/docker/vault/ folder |
| `970144f` | feat(vault): add HashiCorp Vault to lab stack; update generator for Vault credential support |
| `715fe1e` | docs(vision): add next actions, pending items, open questions, and constraints |
| `b22799d` | docs(vision): document current platform state as of 2026-07-01 |
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
| Desired State Provisioning | Terraform `CiscoDevNet/aci` | ✅ Working — vertical slice applied end-to-end |
| Day-2 Operations | Ansible `cisco.aci` | ❌ Not implemented |
| Validation | pyATS + Catfish | ❌ Not implemented |
| CI/CD Pipeline | GitHub Actions | ❌ Not implemented |
| Platform API | FastAPI | 🟡 Partial — skeleton container running (`/health`, `/readiness`, `/version`); no auth, RBAC, Canonical Intent, or policy enforcement yet |
| Workflow Orchestration | n8n | ❌ Not implemented |
| Secrets Management | HashiCorp Vault | ✅ Running — lab stack, KV v2 populated, Terraform now reads credentials from Vault at runtime (no static tfvars) |
| Observability | Prometheus + Grafana + Loki | ❌ Not implemented |
| Knowledge Layer | Obsidian + Git | ❌ Not implemented |
| AI Assistance | LangGraph | ❌ Not implemented |
| Policy Validation | Open Policy Agent | ❌ Not implemented |

The immediate priority is completing the **first end-to-end vertical slice**: Nautobot → NetAsCode YAML → Terraform → Ansible → pyATS. Terraform is now done and proven end-to-end; Ansible (Phase 4) is next. The Platform API skeleton runs in parallel as lab infrastructure but is not yet part of the vertical slice's critical path. Everything else is future scope.

---

# Next Actions

The next actions are ordered by dependency. Each item must be complete before the one that follows it.

## Phase 3 — Terraform ACI module ✅ Complete

See the full write-up under "Phase 3 — Terraform ACI module" earlier in this document. Summary: `providers.tf`, `variables.tf`, `main.tf`, `outputs.tf`, and `scripts/load-vault-creds.sh` were created, validated (`terraform init`, `terraform validate`), and proven with a live `terraform apply` against the ACI simulator using a real user tenant (`web-tenant`).

---

## Immediate — Phase 4: Ansible Day-2

**This is now the critical path.** Terraform has established the base provisioned state (tenant, VRF, bridge domain, subnet); Ansible will own Day-2 operations Terraform doesn't manage.

### Tasks

1. `platform/ansible/aci/inventory/hosts.yml` — ACI simulator as target
2. `platform/ansible/aci/group_vars/aci.yml` — connection vars sourced from Vault (`secret/lab/platform`), no hardcoded credentials
3. `platform/ansible/aci/playbooks/verify-tenants.yml` — read-only: query ACI, assert tenants match Nautobot intent
4. `platform/ansible/aci/playbooks/day2-epg.yml` — Day-2 example: create an EPG in the `web-bd` bridge domain
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
| 1 | Terraform ACI module (`providers.tf`, `variables.tf`, `main.tf`) | 3 | ✅ Done | — |
| 2 | Static example YAML committed to repo | 3 | 🟡 Medium | Terraform development without live Nautobot (not currently blocking — live Nautobot lab is available) |
| 3 | End-to-end chain test (Nautobot → YAML → Terraform → ACI) | 3b | ✅ Done | — (completed 2026-07-03 with `web-tenant`) |
| 4 | Generator unit tests | 6 | 🟠 High | CI |
| 5 | Ansible Day-2 playbooks (`verify-tenants`, `day2-epg`) | 4 | 🔴 Critical | pyATS, CI |
| 6 | pyATS ACI validation tests | 5 | 🟠 High | CI |
| 7 | GitHub Actions CI workflow | 7 | 🟡 Medium | None (vertical slice cap) |
| 8 | ACI system tenant handling in Terraform | 3 | ✅ Done | Resolved via filtering (`_system_tenants` local excludes `common`/`infra`/`mgmt` from all `for_each` maps) rather than importing them into state |
| 9 | `platform/netascode/aci/example-tenants.yaml` (committed) | 3 | 🟡 Medium | Static Terraform development |
| 10 | `tests/unit/` directory creation | 6 | 🟡 Medium | Unit test phase |
| 11 | Platform API (FastAPI) | Skeleton | 🟡 Partial | Skeleton container running (`/health`, `/readiness`, `/version`); auth, RBAC, Canonical Intent, and policy enforcement remain future scope |
| 12 | Workflow Orchestration (n8n) | Future | 🔵 Future | — |
| 13 | Secrets Management (HashiCorp Vault) | ✅ Done | ✅ Complete | Vault running in lab stack; KV v2 populated; Terraform reads credentials from Vault at runtime via `scripts/load-vault-creds.sh` (no static tfvars) |
| 14 | Observability stack (Prometheus, Grafana, Loki) | Future | 🔵 Future | — |
| 15 | Knowledge Layer (Obsidian + Git) | Future | 🔵 Future | — |
| 16 | AI Assistance (LangGraph) | Future | 🔵 Future | — |
| 17 | Policy Validation (OPA) | Future | 🔵 Future | — |
| 18 | Multi-domain expansion (VXLAN EVPN, Azure) | Future | 🔵 Future | — |
| 19 | Terraform → Vault credential loader (`scripts/load-vault-creds.sh`) | 3 | ✅ Done | — (closed 2026-07-03; replaced hand-typed `terraform.tfvars`) |
| 20 | Stale duplicate Vault container (`infra-automation-lab-vault-1`) removed | — | ✅ Done | — (closed 2026-07-03; leftover from pre-refactor merged stack, shared no unique data) |

---

# Open Questions

| # | Question | Impact |
|---|---|---|
| Q1 | ~~Should Terraform import the ACI system tenants into state on first run, or manage them with `lifecycle { prevent_destroy = true }`?~~ **Resolved (2026-07-03):** neither — Terraform filters system tenants out of every `for_each` map via a `_system_tenants` local, so they are never read into state at all. | Phase 3 approach decided |
| Q2 | ~~Will the ACI simulator require a specific `netascode/aci` provider version for compatibility?~~ **Resolved (2026-07-03):** switched to `CiscoDevNet/aci ~> 2.0` (`v2.20.0` installed), which works against APIC 6.2(1g) with no compatibility issues found. | `providers.tf` version pin decided |
| Q3 | Should pyATS connect directly to the ACI APIC REST API or use the `pyats.contrib.aci` library? | Determines Phase 5 test design |
| Q4 | Should the generator output additional NetAsCode object types beyond tenants, VRFs, and BDs (e.g. EPGs, contracts, external networks)? | Scope of Phase 2 extension vs later phases |
| Q5 | When user-defined tenants are added to the ACI lab, will the generator filter them correctly without `--include-system-tenants`? **Partially answered:** confirmed working for `web-tenant` in the Phase 3 vertical slice test. | Requires further lab data extension to fully verify |

---

# Known Constraints

- The ACI simulator contains **only system tenants**. The `--include-system-tenants` flag is required for the generator to produce any output in the current lab environment.
- The ACI simulator uses a **self-signed TLS certificate**. All tools must use `insecure = true` / `--no-verify` / `verify=False`.
- `platform/netascode/aci/tenants.yaml` is **gitignored** (generated artifact). Terraform cannot reference it from CI unless the generator runs first as a pipeline step.
- The `lab/docker/nautobot/` directory is a **nested git repository** and is excluded from this repo's tracking. It must be managed independently.
- Nautobot VRFs do not carry a `tenant` field in the REST API response by default. VRF-to-tenant association is retrieved via the `tenants.vrfs` GraphQL relationship.
