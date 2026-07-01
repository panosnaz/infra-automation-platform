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

---

# Platform Implementation State

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
| Secrets Management | HashiCorp Vault | ❌ Not implemented |
| Observability | Prometheus + Grafana + Loki | ❌ Not implemented |
| Knowledge Layer | Obsidian + Git | ❌ Not implemented |
| AI Assistance | LangGraph | ❌ Not implemented |
| Policy Validation | Open Policy Agent | ❌ Not implemented |

The immediate priority is completing the **first end-to-end vertical slice**: Nautobot → NetAsCode YAML → Terraform → Ansible → pyATS. Everything else is future scope.
