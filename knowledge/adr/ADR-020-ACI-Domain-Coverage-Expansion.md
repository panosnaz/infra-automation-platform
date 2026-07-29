---
type: adr
domain: platform
status: active
tags: [aci, domain-coverage, roadmap, generator, terraform, mcp]
owner: platform-engineering-team
last_updated: 2026-07-29
---

# ADR-020 — ACI Domain Coverage Expansion (Tenant Policy Depth, then Access/Fabric Policies)

**Status:** Accepted

**Date:** 2026-07-29

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-002 — Terraform as the Declarative Provisioning Engine (this ADR extends Terraform's scope, not its role)
- ADR-007 — Cisco NetAsCode as the Canonical Engineering Model (the schema this expansion adds to)
- ADR-017 — Execution Framework (the pipeline this expansion reuses unchanged)
- ADR-018 — NetAsCode YAML as the Authoritative Intent Artifact (governs how new object types are added: through the generator, never a parallel schema)
- ADR-019 — Three Truths Principle (Desired State ownership boundary this expansion stays inside)

---

# Context

Execution Framework Milestones 1-5 (see [`Execution-Framework.md`](../architecture/Execution-Framework.md) §6) proved the full lifecycle — Nautobot → generator → GitLab CI (validate → policy → approve → apply → configure → verify → capture) → MCP Server — end to end, against live infrastructure. But the *domain automation* those milestones proved is narrow: checked directly against the code (`platform/python/generator/transformer.py`, `platform/terraform/aci/main.tf`), the only ACI object types under repeatable, Nautobot-driven management today are:

| Object | Status |
|---|---|
| Tenant | Full lifecycle |
| VRF | Full lifecycle |
| Bridge Domain | Full lifecycle (unicast routing only, no L2/L3 attribute depth) |
| Subnet (BD gateway) | Full lifecycle |

Everything else a real ACI deployment needs is either absent or exists only as a hand-scripted, non-repeatable example:

- **Application Profiles / EPGs** — `platform/ansible/aci/playbooks/day2-epg.yml` exists but hardcodes tenant/AP/EPG/BD names; it is not driven by Nautobot data and is not part of the pipeline.
- **Contracts / Filters / Subjects** — no code, no schema, no Nautobot modeling at all.
- **L3Outs / external connectivity** — no code, no schema, no Nautobot modeling at all.
- **Access Policies** (VLAN pools, physical/VMM domains, AEPs, leaf/spine interface policies, interface/leaf profiles) — no code. This is the layer that actually stages physical fabric connectivity (which ports carry which VLANs/EPGs).
- **Fabric Policies** (POD-wide NTP/DNS/SNMP, etc.) — no code.

This gap was flagged directly by the user: *"realistically, we need to support all kind of configurations and staging of the APIC and fabric"* — the current pipeline proves the *mechanism* (Milestones 1-5), not *coverage*.

A prior planning document, [`Nautobot-NaC-Architecture.md`](../architecture/Nautobot-NaC-Architecture.md), already contains a detailed NetAsCode YAML schema and Nautobot-object mapping for Application Profiles, EPGs (with physical/VMM domain bindings and static port bindings), VLAN Pools, physical/VMM Domains, AEPs, and leaf interface policy groups/profiles/selectors (its Parts 2, 5, and 6). That document's own "Implementation Phases" (Part 7) is superseded — it predates and describes a different, more primitive delivery mechanism (a manually-triggered Nautobot Job, no GitLab CI, no policy/approval gates) than the Execution Framework this repository actually built. Its schema and data-model design remain valid and are reused here; its delivery-mechanism plan is not. Neither Contracts/Filters/Subjects nor L3Outs are covered by that document at all — those need new design work, not just implementation of an existing plan.

---

# Decision

Expand ACI domain coverage in two sequenced phases, **both reusing the Execution Framework's existing machinery (generator pattern, GitLab CI pipeline stages, policy/approval gates, MCP Server tool registry) completely unchanged** — per ADR-018, a new object type is added by extending the generator's output schema and adding Terraform resources, never by inventing a new pipeline stage or a parallel intent schema.

## Phase A — Tenant Policy Depth

Extends the existing Tenant → VRF → Bridge Domain chain. Reuses Nautobot's current Tenant/VRF/Prefix data model plus Custom Fields (the same mechanism already used for `write_results.py`'s status fields) — no new Nautobot plugin or custom model required for the BD/VRF attribute depth; Application Profiles/EPGs need a small addition (see below).

1. **VRF and Bridge Domain attribute depth** — the four VRF-level and ten BD-level attributes already designed in `Nautobot-NaC-Architecture.md` Part 3 (e.g. `contract_enforcement_preference`, `unicast_routing` detail, `arp_flooding`, `l2_unknown_unicast`, `pim`), added as Nautobot Custom Fields on `VRF`/`Prefix` and read by the generator. Lowest-risk, highest-value first step — pure attribute enrichment of objects the generator already handles.
2. **Application Profiles + EPGs** — per the schema already designed in `Nautobot-NaC-Architecture.md` Part 5 (`apic.tenants[].application_profiles[].endpoint_groups[]`, including `bridge_domain` binding, `physical_domains`/`vmm_domains`, and `static_ports`). Requires modeling Application Profile and EPG in Nautobot — a lightweight custom model or Nautobot's `Tag`/`Relationship` primitives are sufficient (per that document's own "Plugin-managed custom model" note); does not require a new Nautobot plugin. New Terraform resources: `aci_application_profile`, `aci_epg`, `aci_epg_to_domain`, `aci_static_path` (or equivalent, per the netascode/aci provider's actual resource names — confirm against the provider docs before implementing, not assumed).
3. **Contracts / Filters / Subjects** — new design (not covered by the existing planning doc). Minimum viable schema: `apic.tenants[].contracts[].{name, scope, subjects[].{name, filters[]}}`, `apic.tenants[].filters[].{name, entries[].{ether_type, ip_protocol, ports}}`, plus EPG-level `provided_contracts[]`/`consumed_contracts[]`. Nautobot modeling: likely a custom model per Contract/Filter, or (simpler, deferred decision) representing them as structured Custom Field data on the Tenant until real usage proves whether first-class Nautobot objects are worth the modeling cost.
4. **L3Out** — new design, largest single item in Phase A (routing protocol config, external EPGs, L3Out interface profiles). Deferred to the end of Phase A; scope it properly (a short design note, not a full ADR) once EPG/Contract are proven, since L3Out's Nautobot modeling questions (which objects represent an external routed connection) are non-trivial and benefit from the EPG/Contract work's lessons.
5. **MCP tools** — add `create_epg`/`create_contract`/`create_l3out` to `mcp-server/tools/aci.py` (per `Platform-v2-Reference-Architecture.md` §7.8's already-named catalogue) once each object's generator/Terraform support lands, following the exact `create_tenant` pattern (Milestone 5): thin Pydantic schema, direct Nautobot write, no intent envelope.

## Phase B — Access and Fabric Policies

A materially different engineering problem from Phase A: these objects map to Nautobot's **Device/Interface/Cable/VLAN** data (DCIM/IPAM), not Tenant/VRF/Prefix, and the current ACI SSoT sync does not populate or use any of it today. Sequenced after Phase A so the generator/pipeline/MCP pattern is proven twice on the simpler problem (Tenant Policy) before tackling the harder data-modeling problem (Access Policy).

1. **Nautobot data model** — confirm what the existing ACI SSoT sync already populates for `Device`/`Interface` (leaf/spine nodes and their ports are synced today per `Nautobot-NaC-Architecture.md` Part 2's table — verify current depth against the live lab before assuming), and what's missing (VLAN pool ranges, physical/VMM domain assignments, AEP-to-domain bindings, interface policy groups). `VLANGroup` (IPAM) is the natural home for VLAN Pools per that document's mapping.
2. **Schema and Terraform** — reuse the YAML schema already designed in `Nautobot-NaC-Architecture.md` Part 6 (`apic.fabric_policies.vlan_pools[]`, `apic.access_policies.{physical_domains, vmm_domains, aaeps, leaf_interface_policy_groups, leaf_interface_profiles, leaf_profiles}[]`) as the starting draft — re-validate every field name against the current `netascode/aci` Terraform provider version before implementing, since that schema was drafted against an unspecified earlier provider version.
3. **Staging semantics** — Access Policies commonly need "define once, reference from many EPGs/interfaces" idempotency (e.g. an AEP reused across many leaf ports) more heavily than Tenant Policy does; validate the generator's determinism proof (Milestone 2's byte-identical-YAML check) still holds under this reuse pattern before considering the pipeline unchanged sufficient.
4. **MCP tools** — deferred until the generator/Terraform side is proven; Access Policy tools are not yet named in `Platform-v2-Reference-Architecture.md` §7.8 and should be scoped once the object model is settled.

## What does not change

- The Execution Framework's 7 stages (Intent → Validation → Policy → Approval → Execution → Verification → Knowledge Capture) — unchanged, per ADR-017/018.
- GitLab CI's shared stage templates (`pipelines/includes/common.gitlab-ci.yml`) — unchanged; each new object type is generator/Terraform-module work, not new pipeline logic, per the reusable-pipeline design already proven across the ACI/future-EVPN/Fortinet/Azure domain split in `Platform-v2-Reference-Architecture.md` §6.
- NetAsCode YAML as the sole intent artifact — no parallel schema, per ADR-018.
- The MCP Server's domain-isolation rule (`tools/generic.py` never imports `tools/aci.py`) — unchanged, per §7.2.

---

# Consequences

**Positive:** each phase is independently shippable and independently valuable (Phase A alone closes the gap for security-policy-adjacent tenant configuration; Phase B alone closes the gap for physical fabric staging) — sequencing avoids a single large, hard-to-review change. Reusing `Nautobot-NaC-Architecture.md`'s existing schema work for Phase A item 2 and Phase B item 2 avoids redesigning what's already been thought through.

**Negative / risk:** Phase A items 3-4 (Contracts, L3Out) and all of Phase B require new Nautobot data modeling decisions (custom models vs. Custom Fields vs. Relationships) that ADR-001/019 do not currently answer — each should get a short design note before implementation, not be improvised mid-PR. Phase B's Access Policy schema was drafted against an unverified provider version and must be re-checked, not assumed correct.

**Explicitly out of scope for this ADR:** Fabric-wide POD policies (NTP/DNS/SNMP) — lowest business value for a Tenant-scoped automation platform; revisit only if a concrete need arises.
