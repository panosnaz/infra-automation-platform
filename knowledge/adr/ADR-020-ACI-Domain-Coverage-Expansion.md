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

# Progress

## Phase A item 1 — VRF and Bridge Domain attribute depth ✅ Complete (2026-07-29)

* Added 11 Nautobot Custom Fields: 3 on `ipam.vrf` (`aci_ip_data_plane_learning`, `aci_policy_control_enforcement_direction`, `aci_policy_control_enforcement_mode`) and 8 on `ipam.prefix` (`aci_bd_mac`, `aci_bd_arp_flooding`, `aci_bd_advertise_host_routes`, `aci_bd_l2_unknown_unicast`, `aci_bd_l3_unknown_multicast`, `aci_bd_multi_destination`, `aci_bd_ep_move_detect_mode`, `aci_bd_pim`) — BD-level fields live on `Prefix` (not a new BD model) since BD identity is already derived per-prefix in the current generator (see `transformer.py`'s module docstring); `igmp_policy` deferred (the provider models it as a relation to a separate `aci_igmp_snooping_policy` resource, not a scalar — out of proportion for this increment).
* Extended `platform/python/generator/client.py`'s GraphQL queries to fetch `_custom_field_data` for VRFs and Prefixes (confirmed exact field name via live GraphQL introspection, not assumed), and `transformer.py`'s `_build_vrfs`/`_build_bridge_domains` to emit these attributes **only when explicitly set** — an unset Custom Field means "let the netascode/aci Terraform provider's own ACI default apply," keeping generated YAML minimal (same convention `description` already uses).
* Extended `platform/terraform/aci/main.tf`'s `aci_vrf` and `aci_bridge_domain` resources to consume the new attributes via `lookup(..., null)`/`try(..., null)`. **Every attribute name and valid value was verified against the live `CiscoDevNet/aci` 2.20.0 provider** — via `terraform providers schema -json` for the full attribute list, and the provider's Terraform Registry documentation for exact valid value strings (e.g. `l2_unknown_unicast_flooding`: `"flood"`/`"proxy"`; `multi_destination_flooding`: `"bd-flood"`/`"drop"`/`"encap-flood"`) — not assumed from `Nautobot-NaC-Architecture.md`'s older, unverified schema draft, which used different field names in places (e.g. that document's `routing`/`host_routing` vs. the real provider's `unicast_routing`/`advertise_host_routes`). Confirmed the real provider has **no VRF-level `preferred_group` attribute** (the older doc's field) — Preferred Group Member is an EPG-level concept in this provider version, deferred to Phase A item 2.
* **Verified live:** set real Custom Field values on `web-tenant`'s VRF/BD, ran the generator against live Nautobot, confirmed the exact expected YAML was produced (`ip_data_plane_learning: disabled`, `policy_control_enforcement_direction: egress`, etc.), then reverted the test values (arbitrary, not deliberate business config) and confirmed the regenerated YAML matched the git-committed baseline exactly (no residual diff).
* `terraform validate` passes. A live `terraform plan` against the ACI simulator could not be completed this session — `172.30.46.103` was unreachable (confirmed via direct `curl` timeout), the same recurring external outage documented in Milestones 4-5's findings, not a defect in this change. Re-run `terraform plan`/`apply` once the simulator is reachable again for final live-apply confirmation.
* Added `tests/unit/test_transformer.py` (7 tests, no live infra required): baseline-output-unchanged regression guard, attribute emission when set, `None`-vs-`False` distinction (an explicit `false` must still be emitted, not treated as "unset"), and omission when unset. Full suite: 51/51 unit tests passing (44 pre-existing + 7 new).

## Phase A item 2 — Application Profiles and EPGs ✅ Complete (2026-07-29)

* Confirmed the real `CiscoDevNet/aci` 2.20.0 resource names via `terraform providers schema -json` (the older `Nautobot-NaC-Architecture.md` draft's assumed `aci_epg` resource name does not exist — the real resource is `aci_application_epg`) and the Terraform Registry docs (`preferred_group_member` valid values `"exclude"`/`"include"`, default `"exclude"`; `relation_to_bridge_domain` is a nested attribute with sub-field `bridge_domain_name`, not a block).
* Modeled EPGs as Nautobot **VLAN** objects (`ipam.vlan`) rather than adding a new Nautobot plugin/custom model — ADR-020 originally proposed a lightweight custom model, but VLAN already has the right shape (name + an integer identifier) and Custom Fields close the gap cleanly, consistent with item 1's Custom-Field-first approach. Added 3 Custom Fields on `ipam.vlan`: `aci_application_profile` (text, the AP name this EPG belongs to), `aci_epg_bridge_domain` (text, the BD name this EPG binds to), `aci_epg_preferred_group_member` (boolean).
* **Strictly opt-in, unlike item 1's read-if-exported-object-already-exists pattern:** a VLAN is only exported as an EPG when *both* `aci_application_profile` and `aci_epg_bridge_domain` are explicitly set — Nautobot's VLAN model is used for plenty of non-ACI IPAM purposes, so an ordinary VLAN with neither field set must never be silently turned into ACI configuration.
* Extended `client.py` (`_QUERY_VLANS` + `get_vlans()`), `transformer.py` (`_build_application_profiles()`, new `vlans` parameter on `build_netascode_yaml()`, defaults to `None`/empty for backward compatibility), `generate_aci.py` (fetches and passes `vlans`), and `main.tf` (`local.application_profiles`/`local.endpoint_groups` flat maps + `aci_application_profile`/`aci_application_epg` resources, following the exact same `for_each`-flat-map and `lookup(...)`/`try(...)` null-handling pattern as items 1's VRF/BD attributes).
* Added 6 new unit tests to `tests/unit/test_transformer.py` (baseline unchanged without `vlans`, VLAN skipped when either custom field missing, AP/EPG emitted when both set, EPGs correctly grouped by AP name across multiple VLANs, `preferred_group_member` only emitted when `True`). Full suite: 56/56 passing.
* **Verified live, including a real `apply`+`destroy` (not just plan)** — since AP/EPG are genuinely new resource types never before created by this module, a plan-only proof (sufficient for item 1's attribute-only change) was not considered enough:
  1. Created a real test VLAN in Nautobot (`web-epg`, vid 100, under `web-tenant`, `aci_application_profile=web-ap`, `aci_epg_bridge_domain=web-bd`).
  2. Regenerated `tenants.yaml` from live Nautobot — generator correctly emitted `application_profiles: [{name: web-ap, endpoint_groups: [{name: web-epg, bridge_domain: web-bd, description: ...}]}]` for `web-tenant`.
  3. `terraform plan` showed exactly the two new resources (`aci_application_profile.this["web-tenant/web-ap"]`, `aci_application_epg.this["web-tenant/web-ap/web-epg"]` — both `will be created`, correct `parent_dn`s, `relation_to_bridge_domain.bridge_domain_name = "web-bd"`), plus 4 unrelated pre-existing `materialization-test-*` debris adds already known from earlier sessions.
  4. Ran a **targeted `terraform apply`** for just those two resources — both created successfully in the real APIC (`Apply complete! Resources: 2 added`, confirmed via `terraform state list` and a follow-up no-target `terraform plan` on the same two resources showing "No changes").
  5. Ran a **targeted `terraform destroy`** for the same two resources (`Destroy complete! Resources: 2 destroyed`), then deleted the test VLAN from Nautobot via the API, then regenerated `tenants.yaml` again and confirmed it reports `vlans=0`, matching the pre-test baseline with no `application_profiles` key for `web-tenant`.
* GOTCHA (tooling, not code): `generate_aci.py --dry-run` interleaves its own `[generator] ...` progress lines with the actual YAML on **stdout** (not stderr as initially assumed) — parsing dry-run output as pure YAML requires splitting on the `--dry-run: output below` marker line first, or (simpler) writing straight to `--output <dir>` and inspecting the file instead of relying on `--dry-run`'s console output.

## Remaining Phase A items (not started)

3. Contracts / Filters / Subjects (new design)
4. L3Out (new design, deferred to end of phase)

---

# Consequences

**Positive:** each phase is independently shippable and independently valuable (Phase A alone closes the gap for security-policy-adjacent tenant configuration; Phase B alone closes the gap for physical fabric staging) — sequencing avoids a single large, hard-to-review change. Reusing `Nautobot-NaC-Architecture.md`'s existing schema work for Phase A item 2 and Phase B item 2 avoids redesigning what's already been thought through.

**Negative / risk:** Phase A items 3-4 (Contracts, L3Out) and all of Phase B require new Nautobot data modeling decisions (custom models vs. Custom Fields vs. Relationships) that ADR-001/019 do not currently answer — each should get a short design note before implementation, not be improvised mid-PR. Phase B's Access Policy schema was drafted against an unverified provider version and must be re-checked, not assumed correct — **item 1's experience confirms this concern was warranted**: the older doc's VRF/BD field names and the real provider's differed in several places.

**Explicitly out of scope for this ADR:** Fabric-wide POD policies (NTP/DNS/SNMP) — lowest business value for a Tenant-scoped automation platform; revisit only if a concrete need arises.

---

# Phase A Item 1 — Live Verification (2026-07-29)

VRF and Bridge Domain attribute depth (Custom Fields, generator, and Terraform changes) was implemented, then verified against the real ACI simulator once it came back online (it had been unreachable earlier the same day — see Milestone 4/5's findings for this same recurring external-outage class):

- `terraform plan` against the full live tenant set (30 tenants) with no test attributes set: **`Plan: 4 to add, 0 to change, 0 to destroy`** — the 4-to-add is pre-existing, unrelated drift (a `materialization-test-*` debris tenant already known from earlier sessions); critically, **0 to change** confirms the new optional attributes introduce no drift on any already-applied resource when left unset.
- Set `aci_policy_control_enforcement_mode: "unenforced"` on `web-vrf` via a real Nautobot Custom Field write, regenerated the YAML, re-ran `terraform plan`: **`Plan: 4 to add, 1 to change, 0 to destroy`**, with the plan showing exactly `aci_vrf.this["web-tenant/web-vrf"] will be updated in-place`, `policy_control_enforcement_mode = "enforced" -> "unenforced"` — Terraform correctly read the live APIC's current value (`"enforced"`) and proposed exactly the intended change.
- Reverted the test value, regenerated, re-ran `terraform plan`: back to `0 to change`, and `tenants.yaml` matched git HEAD exactly (no leftover diff).

This closes Phase A item 1's live-verification gap noted when it was first implemented (the simulator was down at the time). No `terraform apply` was run — a plan-only proof is sufficient for a non-destructive attribute-depth addition, and applying would have changed live simulator state for a value that was only ever meant as a test, not deliberate configuration.


