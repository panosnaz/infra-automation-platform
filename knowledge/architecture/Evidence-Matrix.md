---
title: "Evidence Matrix"
description: "Per-tool and per-module verification status — every MCP tool and Terraform scope named individually, with its evidence level and the specific reason it sits there."
type: architecture
domain: platform
status: active
tags: [status, evidence, testing]
owner: platform-engineering-team
last_updated: 2026-09-15
---

# Evidence Matrix

This is the itemized companion to [`Platform-Status-and-Pending-Items.md`](Platform-Status-and-Pending-Items.md). That document tracks status by feature/phase; this one names **every individual MCP tool and Terraform scope** with its evidence level, so no claim about "the L4-L7 tools" or "the access hierarchy" hides which specific ones are actually confirmed.

## How to read this

Three evidence levels, defined in [`mcp-server/src/mcp_server/tools/registry.py`](../../mcp-server/src/mcp_server/tools/registry.py) and required by [`CLAUDE.md`](../../CLAUDE.md)'s Definition of Done:

| Level | Means | Does NOT mean |
|---|---|---|
| `unit-tested` | Schema validation + dispatch covered by offline tests. **This is the default** for every new tool — chosen so forgetting to test something *understates* the claim, never overstates it. | That the tool has a limitation preventing live use. In nearly every case here, nothing blocks it — it just hasn't been run live yet. |
| `plan-verified` | The Terraform it drives produces a clean plan against the real APIC. | That the resource is actually produced or valid — a clean plan validates against the provider schema only, never live APIC state (see the OSPF fixture note below). |
| `live-verified` | Exercised for real — over the MCP protocol against live Nautobot, and/or a genuine Terraform apply + destroy with the APIC fault delta checked. | That it is fault-free forever, or that the current session's containers are up right now — this records a session that *happened*, not a live health check. |

**Live counts** (`registry.by_evidence()`, re-confirmed 2026-09-15): 50 tools total — **18 live-verified, 0 plan-verified, 32 unit-tested**. If these numbers drift from what's below, `mcp-server/tests/unit/test_registry.py::test_live_verified_tools_match_the_documented_count` will fail — that test is the drift guard.

**Runtime state is deliberately not recorded here.** Per `knowledge/README.md`'s rule, this vault holds durable build-status facts, not live snapshots — whether the MCP server container is up right now is checked with `docker ps`, not read from this file.

---

## 1. MCP Tools — all 50

### Live-verified (18)

| # | Tool | Domain | Evidence note |
|---|---|---|---|
| 1 | `create_tenant` | cisco_aci | MCP protocol + Nautobot, Milestone 6 end-to-end |
| 2 | `create_vrf` | cisco_aci | MCP protocol + Nautobot, Milestone 6 end-to-end |
| 3 | `create_bridge_domain` | cisco_aci | MCP protocol + Nautobot, Milestone 6 end-to-end |
| 4 | `create_epg` | cisco_aci | MCP protocol + Nautobot (ADR-020 Phase A) |
| 5 | `bind_epg_domain` | cisco_aci | MCP protocol session 2026-09-04, verified in Nautobot then cleaned up |
| 6 | `create_contract` | cisco_aci | MCP protocol + Nautobot (ADR-020 Phase A) |
| 7 | `create_l3out` | cisco_aci | MCP protocol + Nautobot (ADR-020 Phase A, logical scope) |
| 8 | `create_vlan_pool` | cisco_aci | MCP protocol session 2026-09-04 |
| 9 | `create_physical_domain` | cisco_aci | MCP protocol session 2026-09-04 |
| 10 | `create_aep` | cisco_aci | MCP protocol session 2026-09-04 |
| 11 | `create_leaf_interface_policy_group` | cisco_aci | MCP protocol session 2026-09-04 |
| 12 | `create_vmm_domain` | cisco_aci | MCP protocol session 2026-09-04, against this lab's real vCenter |
| 13 | `create_security_domain` | cisco_aci | MCP protocol session 2026-09-04 (ADR-020 Phase F) |
| 14 | `create_local_user` | cisco_aci | MCP protocol session 2026-09-04 (ADR-020 Phase F) |
| 15 | `create_evpn_tenant` | vxlan_evpn | MCP protocol + Nautobot (ADR-021) |
| 16 | `create_evpn_vrf` | vxlan_evpn | MCP protocol + Nautobot (ADR-021) |
| 17 | `create_evpn_bridge_domain` | vxlan_evpn | MCP protocol + Nautobot (ADR-021) |
| 18 | `show_status` | generic | MCP protocol, Milestone 6 gate — merged Nautobot + live GitLab status |

### Unit-tested only (32) — reason stated per tool, not as a group

| # | Tool | Domain | Reason |
|---|---|---|---|
| 19 | `create_filter` | cisco_aci | Terraform side (`aci_filter`) is live-verified as part of Phase A contract work; this tool has never been called through a live MCP session |
| 20 | `create_filter_entry` | cisco_aci | `aci_filter_entry` live-verified via direct Terraform; tool never called live |
| 21 | `create_contract_subject` | cisco_aci | `aci_contract_subject` live-verified via Phase A; tool never called live |
| 22 | `bind_epg_contract` | cisco_aci | `aci_epg_to_contract` live-verified via Phase A; tool never called live |
| 23 | `create_pod_policy_group` | cisco_aci | Terraform (`fabricPodPGrp`) is live-verified, ADR-020 Phase E, including a destroy-safety test; the MCP tool itself was never called live |
| 24 | `create_access_port_profile` | cisco_aci | XML-compatible access hierarchy, ported 2026-09-08 — plan-verified only in Terraform, no apply ever run; tool never called |
| 25 | `create_access_port_selector` | cisco_aci | Same scope — plan-verified only |
| 26 | `create_access_port_block` | cisco_aci | Same scope — plan-verified only |
| 27 | `create_leaf_profile` | cisco_aci | Same ported scope — plan-verified only |
| 28 | `create_leaf_selector` | cisco_aci | Same ported scope — plan-verified only |
| 29 | `create_leaf_node_block` | cisco_aci | Same ported scope — plan-verified only |
| 30 | `create_leaf_interface_profile` | cisco_aci | Physical/protocol L3Out scope, ported 2026-09-08 — plan-verified only, no apply run |
| 31 | `create_interface_selector` | cisco_aci | Same scope — plan-verified only |
| 32 | `create_static_path_binding` | cisco_aci | Depends on real `pathep-` DNs; ported 2026-09-08, plan-verified only |
| 33 | `create_fabric_device` | cisco_aci | **Note:** called directly against live Nautobot on 2026-09-14/15 (created `spine-1`, backfilled `pod_id` on `leaf-a`/`leaf-b`) — but that call bypassed the MCP protocol transport (direct Python call, no JSON-RPC session). Kept at `unit-tested` rather than promoted, consistent with "never overstate" |
| 34 | `create_fabric_interface` | cisco_aci | Never called against live Nautobot in any form |
| 35 | `create_bgp_l3out` | cisco_aci | Protocol L3Out, ported 2026-09-08 — plan-verified only, no apply run |
| 36 | `create_ospf_l3out` | cisco_aci | Same scope — plan-verified only |
| 37 | `create_l3out_node_profile` | cisco_aci | Same scope — plan-verified only |
| 38 | `create_l3out_interface_profile` | cisco_aci | Same scope — plan-verified only |
| 39 | `create_l3out_interface` | cisco_aci | Same scope — plan-verified only |
| 40 | `create_bgp_peer` | cisco_aci | Same scope — plan-verified only |
| 41 | `create_ospf_interface` | cisco_aci | Same scope — plan-verified only |
| 42 | `create_ospf_interface_policy` | cisco_aci | Same scope — plan-verified only |
| 43 | `create_vrf_route_leak` | cisco_aci | `aci_vrf_leak_epg_bd_subnet` is plan-verified only in Terraform (no apply ever run); tool never called |
| 44 | `create_l4l7_device` | cisco_aci | Terraform side is live-verified (physical, 6-fault floor) / plan-verified (virtual); this MCP tool was never called — the fixtures used for live testing were hand-written YAML, not tool-generated |
| 45 | `create_service_graph` | cisco_aci | Same — Terraform live-verified, tool never called |
| 46 | `create_one_arm_service_graph` | cisco_aci | Never exercised in any form, Terraform or tool |
| 47 | `create_pbr_policy` | cisco_aci | Terraform side live-verified (physical) / plan-verified (virtual); tool never called |
| 48 | `create_pbr_health_group` | cisco_aci | Same — Terraform live-verified, tool never called |
| 49 | `create_ip_sla_policy` | cisco_aci | Same — Terraform live-verified, tool never called |
| 50 | `create_pbr_contract` | cisco_aci | Never exercised in any form, Terraform or tool |

**On row 33** — the one genuinely ambiguous case. Its Nautobot write path is proven correct by direct evidence, but not through the real MCP transport, so it stays at the weaker level by design.

**On "unit-tested" in general** — see the clarifying exchange this doc was built from: the tool *call* (a Nautobot Custom Field write) has zero technical obstacle for all 32. All 32 could be live-verified this week with no external blocker. Where a real constraint exists, it sits in the Terraform/APIC layer beneath the tool, not in the tool itself — see §2 and §3.

---

## 2. Terraform modules/fixtures not fully live-verified

| # | Module / Resource / Fixture | Evidence | Reason |
|---|---|---|---|
| 1 | `aci_l3out_path_attachment` | plan-verified only | No apply ever run. Expected to succeed (`pathep-` DNs accepted, left `unformed`) but unverified |
| 2 | `aci_bgp_peer_connectivity_profile` | plan-verified only | Same scope — no BGP session can ever establish (no switches) |
| 3 | `aci_vrf_leak_epg_bd_subnet` | plan-verified only | No apply ever run for VRF route leaking |
| 4 | `aci_concrete_interface` (physical L4-L7) | **live-verified, with a hard floor** | Apply+destroy proven; bottoms out at 6 faults — no leaf ports exist. See §3 |
| 5 | `l4l7-vmm-virtual.yaml` (virtual L4-L7 chain) | plan-verified only | 37-to-add plan clean, 0 `pathep-` refs; apply blocked on missing vCenter password + unproven reachability to `192.168.10.62` — not a simulator dataplane issue, see §3's exclusions |
| 6 | `access-l3out-tools.yaml` fixture | plan-verified only, superseded | Reference fixture, not used for live testing anymore |
| 7 | `l4l7-pbr.yaml` fixture | plan-verified only, superseded | Superseded by `l4l7-pbr-resilient.yaml` |
| 8 | `aci_rest_managed.fabric_node_identity` | live-verified, **gated off by default** | Proven both directions (apply+destroy); costs 3 extra faults on a switch-less fabric, so `register_fabric_membership = false` |

Find every `# EVIDENCE:` comment in the codebase with:
```bash
grep -rn "EVIDENCE:" platform/terraform/
```

---

## 3. Specifically blocked by APIC simulator dataplane / switch unavailability

Root cause, measured directly against the live APIC: `fabricNode` = 1 (the controller only), leaf = 0, spine = 0, `l1PhysIf` = 0, `fabricPathEp` = 0. No switch has ever checked in, and the one discovered stub (`TEP-1-101`) has an all-zero MAC and no firmware — it is not a device waiting to join.

Configuration is **never** the blocker here — APIC accepts every construct below. Deployment and operation are.

| # | Capability | What actually fails |
|---|---|---|
| 1 | L3Out physical interface activation (routed/SVI/sub-interface) + BGP/OSPF/EIGRP peer sessions on it | Config accepted, relation sits `unformed` forever — no neighbor device exists |
| 2 | Access Policy physical port bindings (leaf interface profile/selector → a real leaf port) | Same — accepted, `unformed`, never deploys |
| 3 | L4-L7 physical concrete device → leaf port (`vnsRsCIfPathAtt`) | Worse than silently unformed — a concrete device with no real port is invalid. **Measured floor of 6 APIC faults**, confirmed both with the path declared and omitted |
| 4 | BGP Route Reflector → spine node binding | Config accepted (`bgpRRNodePEp`); no spine exists to run reflection |
| 5 | Registering a new switch into the fabric (`fabricNodeIdentP`) | Creates a roster entry; node stays `fabricSt: undiscovered` / `adSt: off` forever |
| 6 | vPC / port-channel-bound objects (`l3extMember` side A/B) | Outright **rejected** at config time — *"can be contained only if target is fabricProtPathEpCont/PathEp"* |
| 7 | Any operational verification of the above | No adjacency, no learned endpoint, no PBR redirect actually forwards a packet, no multicast/BUM flooding — there is no dataplane to measure |

**Explicitly excluded from this list** (blocked for unrelated reasons — do not conflate):
- **Virtual (VMM-backed) L4-L7** — blocked by a missing vCenter password and unproven network reachability, not by simulator dataplane. Has zero leaf-port dependency; could plausibly reach zero faults in ACI's MIT if credentials/reachability were resolved.
- **Health Score policy** — genuinely unavailable in this APIC version (no resolvable class, confirmed by direct API testing). Not a hardware issue.

Unaffected entirely by this limitation: tenant/VRF/BD/EPG, contracts, VMM domain integration, fabric-wide POD policies (NTP/DNS/SNMP/COOP/ISIS), RBAC, syslog/fault.

---

## 4. Standing process gaps — not evidence-level facts, but adjacent

| Gap | Status |
|---|---|
| Unit test suites run in CI | **No.** Confirmed 2026-09-15 — no `pytest` invocation anywhere in `pipelines/` or `.gitlab-ci.yml`. All 348 tests are manual-only |
| Nautobot Custom Field schema bootstrap script | **Not built.** Undeclared fields are still silently dropped on write (the root cause behind finding F-01) |
| Webhook coverage beyond Tenant | **Not fixed.** Only `tenancy.tenant` changes trigger the pipeline (finding F-04) |
| APIC fault-delta check (`check_apic_faults.py`) wired for EVPN | **Not wired.** Only wired into the ACI pipeline (`.verify_apic_faults` in `pipelines/aci.gitlab-ci.yml`) |

---

*Last verified against the live registry and both test suites on 2026-09-15 — see `mcp-server/tests/unit/test_registry.py` for the drift guard that keeps §1's counts honest.*
