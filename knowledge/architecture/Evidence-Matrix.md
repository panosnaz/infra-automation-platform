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

**Live counts** (`registry.by_evidence()`, re-confirmed 2026-09-16): 65 tools total — **35 live-verified, 0 plan-verified, 30 unit-tested**. If these numbers drift from what's below, `mcp-server/tests/unit/test_registry.py::test_live_verified_tools_match_the_documented_count` will fail — that test is the drift guard.

**Runtime state is deliberately not recorded here.** Per `knowledge/README.md`'s rule, this vault holds durable build-status facts, not live snapshots — whether the MCP server container is up right now is checked with `docker ps`, not read from this file.

---

## 1. MCP Tools — all 65

### Live-verified (35)

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
| 12 | `create_vmm_domain` | cisco_aci | MCP protocol session 2026-09-04, against this lab's real vCenter. Extended 2026-09-15: the controller is now optional, and a **controller-less** domain (`vCenter_VMM`) was created over MCP and applied — `vmmDomP` present, 0 `vmmCtrlrP`, and an L4-L7 VIRTUAL device's `vnsRsALDevToDomP` reaches `state: formed` against it, so a virtual device is visible in APIC with no vCenter at all |
| 13 | `create_security_domain` | cisco_aci | MCP protocol session 2026-09-04 (ADR-020 Phase F) |
| 14 | `create_local_user` | cisco_aci | MCP protocol session 2026-09-04 (ADR-020 Phase F) |
| 15 | `create_evpn_tenant` | vxlan_evpn | MCP protocol + Nautobot (ADR-021) |
| 16 | `create_evpn_vrf` | vxlan_evpn | MCP protocol + Nautobot (ADR-021) |
| 17 | `create_evpn_bridge_domain` | vxlan_evpn | MCP protocol + Nautobot (ADR-021) |
| 18 | `show_status` | generic | MCP protocol, Milestone 6 gate — merged Nautobot + live GitLab status |
| 19 | `create_filter` | cisco_aci | PBR lab 2026-09-15 — `Web_Fltr` (tcp/80 + tcp/443) written over MCP → generator → `terraform apply`; both `vzEntry` objects confirmed in APIC, **zero faults** |
| 20 | `create_pbr_policy` | cisco_aci | PBR lab 2026-09-15 — `DB_PBR` (10.0.2.253) and `Backup_PBR` (10.0.9.253) applied; `vnsSvcRedirectPol` + `vnsRedirectDest` confirmed in APIC, **zero faults of their own** |
| 21 | `create_pbr_contract` | cisco_aci | PBR lab 2026-09-15 — `FW_Ct` applied; `vzBrCP`, its subject, `vzRsSubjGraphAtt`→`FW_SGT` and the `vnsLDevCtx` device-selection policy with both `vnsRsLIfCtxToSvcRedirectPol` relations all `state: formed`, **zero faults** |
| 22 | `create_nd_interface_policy` | cisco_aci | Terraform apply + destroy on a throwaway tenant 2026-09-16 (`19 added` — `19 destroyed`) with the MO read back from APIC, AND driven over real MCP JSON-RPC against the running container with the write confirmed in Nautobot. `ndIfPol ND_Strict`: `hopLimit=64 mtu=1500 retransTimer=1000` confirmed; `l3extRsNdIfPol` `state: formed` |
| 23 | `create_dpp_policy` | cisco_aci | Terraform apply + destroy on a throwaway tenant 2026-09-16 (`19 added` — `19 destroyed`) with the MO read back from APIC, AND driven over real MCP JSON-RPC against the running container with the write confirmed in Nautobot. `qosDppPol Ingress_100M`: `rate=100 mega burst=200 mega conform=transmit exceed=drop` confirmed; both ingress and egress relations `formed` |
| 24 | `create_pim_interface_policy` | cisco_aci | Terraform apply + destroy on a throwaway tenant 2026-09-16 (`19 added` — `19 destroyed`) with the MO read back from APIC, AND driven over real MCP JSON-RPC against the running container with the write confirmed in Nautobot. `pimRsIfPol` and `pimRsV6IfPol` both `formed`. Note these are nested under `pimifp`/`pimipv6ifp` containers, not direct `l3extRs*` children |
| 25 | `create_igmp_interface_policy` | cisco_aci | Terraform apply + destroy on a throwaway tenant 2026-09-16 (`19 added` — `19 destroyed`) with the MO read back from APIC, AND driven over real MCP JSON-RPC against the running container with the write confirmed in Nautobot. `igmpIfPol IGMP_v3`: `ver=v3 queryIntvl=125 grpTimeout=260` confirmed; `igmpRsIfPol` `formed` |
| 26 | `create_custom_qos_policy` | cisco_aci | Terraform apply + destroy on a throwaway tenant 2026-09-16 (`19 added` — `19 destroyed`) with the MO read back from APIC, AND driven over real MCP JSON-RPC against the running container with the write confirmed in Nautobot. `l3extRsLIfPCustQosPol` `formed` |
| 27 | `bind_l3out_interface_profile_policies` | cisco_aci | Terraform apply + destroy on a throwaway tenant 2026-09-16 (`19 added` — `19 destroyed`) with the MO read back from APIC, AND driven over real MCP JSON-RPC against the running container with the write confirmed in Nautobot. All seven relations bound at once reached `state: formed`, while a control profile with no bindings correctly fell back to `uni/tn-common/*-default` — which is the only way to inherit the default, since the literal `default` is rejected |
| 28 | `create_match_rule` | cisco_aci | Transit-routing lab 2026-09-16: written over the real MCP protocol, generated, applied (`8 added, 8 changed, 0 destroyed`) with **zero new faults** (25 before, 25 after), and the MO read back from APIC. `rtctrlSubjP` + `rtctrlMatchRtDest` confirmed for `match-permit-prefix-out` (172.16.200.200/32) and `deny-prefix-out` (10.0.3.0/24), each with `aggregate=no ge=0 le=0` — the screenshots' exact defaults |
| 29 | `create_route_control_profile` | cisco_aci | Transit-routing lab 2026-09-16: written over the real MCP protocol, generated, applied (`8 added, 8 changed, 0 destroyed`) with **zero new faults** (25 before, 25 after), and the MO read back from APIC. `rtctrlProfile Uni-Route-Profile-OUT` at `type=global` (Match Routing Policy Only) with `rtctrlCtxP` order 0 permit-explicit/permit and order 1 explicit-deny-out/deny, both `rtctrlRsCtxPToSubjP` relations `state: formed` |
| 30 | `bind_external_epg_route_control_profile` | cisco_aci | Transit-routing lab 2026-09-16: written over the real MCP protocol, generated, applied (`8 added, 8 changed, 0 destroyed`) with **zero new faults** (25 before, 25 after), and the MO read back from APIC. `l3extRsInstPToProfile` on `Cat_ExtNet`, `direction=export`, `state: formed`. Needed because a custom-named map is inert — only `default-export`/`default-import` apply on their own |
| 31 | `set_external_epg_subnet_scope` | cisco_aci | Transit-routing lab 2026-09-16: written over the real MCP protocol, generated, applied (`8 added, 8 changed, 0 destroyed`) with **zero new faults** (25 before, 25 after), and the MO read back from APIC. `Cat_ExtNet` 172.16.200.200/32 moved from `export-rtctrl` to `import-security`, read back from APIC. The feared overlap fault (the same prefix is classified by `Nexus_ExtNet`) did **not** materialise — measured, not assumed |
| 32 | `bind_external_epg_contract` | cisco_aci | Transit-lab corrections 2026-09-16: written over the real MCP protocol, generated, applied (`15 added, 6 changed, 2 destroyed`) and the MO read back from APIC. Fault delta: 2 new, both the switch-absence family, neither a config error. `fvRsCons` on Cat_ExtNet and `fvRsProv` on Nexus_ExtNet, both to FileServices_Ct, `state: formed`. Terraform had modelled this all along — no tool could write it |
| 33 | `add_external_epg_subnet` | cisco_aci | Transit-lab corrections 2026-09-16: written over the real MCP protocol, generated, applied (`15 added, 6 changed, 2 destroyed`) and the MO read back from APIC. Fault delta: 2 new, both the switch-absence family, neither a config error. `l3extSubnet 172.16.199.199/32 scope=import-security` on Nexus_ExtNet |
| 34 | `add_match_rule_prefix` | cisco_aci | Transit-lab corrections 2026-09-16: written over the real MCP protocol, generated, applied (`15 added, 6 changed, 2 destroyed`) and the MO read back from APIC. Fault delta: 2 new, both the switch-absence family, neither a config error. the second `rtctrlMatchRtDest` inside `deny-prefix-out`, alongside 10.0.3.0/24 |
| 35 | `create_l3_domain` | cisco_aci | Transit-lab corrections 2026-09-16: written over the real MCP protocol, generated, applied (`15 added, 6 changed, 2 destroyed`) and the MO read back from APIC. Fault delta: 2 new, both the switch-absence family, neither a config error. `l3extDomP ExtL3Dom` bound to `vlanns-[ExtL3_Pool]-static`, and `EXTERNAL_SWITCH_AAEP` — `uni/l3dom-ExtL3Dom` `state: formed`. Closing this also fixed the standing finding that vlan-51 was in no VLAN pool |

### Unit-tested only (30) — reason stated per tool, not as a group

| # | Tool | Domain | Reason |
|---|---|---|---|
| 36 | `create_filter_entry` | cisco_aci | `aci_filter_entry` live-verified via direct Terraform; tool never called live |
| 37 | `create_contract_subject` | cisco_aci | `aci_contract_subject` live-verified via Phase A; tool never called live |
| 38 | `bind_epg_contract` | cisco_aci | `aci_epg_to_contract` live-verified via Phase A; tool never called live |
| 39 | `create_pod_policy_group` | cisco_aci | Terraform (`fabricPodPGrp`) is live-verified, ADR-020 Phase E, including a destroy-safety test; the MCP tool itself was never called live |
| 40 | `create_access_port_profile` | cisco_aci | XML-compatible access hierarchy, ported 2026-09-08. **Terraform side applied live 2026-09-15** (`infraAccPortP`/`infraHPortS`/`infraPortBlk`/`infraNodeP` present, zero new faults); this MCP tool has still never been called |
| 41 | `create_access_port_selector` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`infraHPortS` × 2 present) |
| 42 | `create_access_port_block` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`infraPortBlk` × 2 present) |
| 43 | `create_leaf_profile` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`infraNodeP` × 2 present) |
| 44 | `create_leaf_selector` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called |
| 45 | `create_leaf_node_block` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called |
| 46 | `create_leaf_interface_profile` | cisco_aci | Physical/protocol L3Out scope, ported 2026-09-08. **Terraform applied live 2026-09-15**, zero new faults; tool never called |
| 47 | `create_interface_selector` | cisco_aci | Plan-verified only. The 2026-09-15 apply covered the XML-compatible access hierarchy (rows 26-31), not this older selector tool's own resource path — not claimed as applied |
| 48 | `create_static_path_binding` | cisco_aci | **Terraform applied live 2026-09-15** — 2 × `fvRsPathAtt` present, `state: unformed` (no switches), zero new faults; tool never called |
| 49 | `create_fabric_device` | cisco_aci | **Note:** called directly against live Nautobot on 2026-09-14/15 (created `spine-1`, backfilled `pod_id` on `leaf-a`/`leaf-b`) — but that call bypassed the MCP protocol transport (direct Python call, no JSON-RPC session). Kept at `unit-tested` rather than promoted, consistent with "never overstate" |
| 50 | `create_fabric_interface` | cisco_aci | Never called against live Nautobot in any form |
| 51 | `create_bgp_l3out` | cisco_aci | Protocol L3Out, ported 2026-09-08. **Terraform applied live 2026-09-15** (`bgpExtP` present, zero new faults); tool never called |
| 52 | `create_ospf_l3out` | cisco_aci | **Terraform applied live 2026-09-15** (`ospfExtP` + `ospfIfP` present, zero new faults); tool never called |
| 53 | `create_l3out_node_profile` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`l3extLNodeP` × 2 present) |
| 54 | `create_l3out_interface_profile` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`l3extLIfP` × 2 present) |
| 55 | `create_l3out_interface` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`l3extRsPathL3OutAtt` × 2, both `state: unformed` — no switches) |
| 56 | `create_bgp_peer` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`bgpPeerP` present; no session can establish without switches) |
| 57 | `create_ospf_interface` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`ospfIfP` present) |
| 58 | `create_ospf_interface_policy` | cisco_aci | **Terraform applied live 2026-09-15** as part of the 93-resource `sales` apply, zero new faults; this MCP tool has still never been called (`ospfIfPol` × 2 present) |
| 59 | `create_vrf_route_leak` | cisco_aci | `aci_vrf_leak_epg_bd_subnet` is plan-verified only in Terraform (no apply ever run); tool never called |
| 60 | `create_l4l7_device` | cisco_aci | **Called over MCP and applied live 2026-09-15 — deliberately NOT promoted.** `vnsLDevVip` exists and `vnsRsALDevToDomP` is `formed`, but APIC flags the device **invalid**: 8 faults rooted in `vnsConfIssue-missing-cdev`. Measured A/B on a throwaway tenant: adding a `vnsCDev` does **not** reduce the count — it trades them for vCenter-vNIC faults (F1778/F0765). **10 faults is the floor for a VIRTUAL device with no vCenter.** The object exists; the deployment does not, so this is not live-verified |
| 61 | `create_service_graph` | cisco_aci | **Called over MCP and applied live 2026-09-15 — deliberately NOT promoted.** `vnsAbsGraph` + `vnsAbsNode-N1` created and the contract's `vzRsSubjGraphAtt` is `formed`, but APIC flags the graph **invalid** (F0757 + F1690) — inherited from row 46's missing concrete device, not a defect in this tool |
| 62 | `create_one_arm_service_graph` | cisco_aci | Never exercised in any form, Terraform or tool |
| 63 | `create_pbr_health_group` | cisco_aci | Same — Terraform live-verified, tool never called |
| 64 | `create_ip_sla_policy` | cisco_aci | Same — Terraform live-verified, tool never called |
| 65 | `create_concrete_device` | cisco_aci | **New 2026-09-15**, closing the gap the PBR lab exposed: `main.tf` had read `vnic_name` since the concrete-device work landed but nothing upstream could produce it, so a virtual concrete device was unexpressible. **Plan-verified** via `tests/fixtures/l4l7-concrete-virtual.yaml` - `Plan: 30 to add`, emitting 1 `aci_concrete_device` (with the `vmm_controller_dn` the client builds), 2 `aci_concrete_interface` carrying `vnic_name`, and **0 `pathep-` references**. Not live-verified: VIRTUAL needs a real vCenter with the appliance VM present, PHYSICAL needs leaf switches. Both blocked on lab hardware, not on this code |

**On row 35** (`create_fabric_device`) — the one genuinely ambiguous case. Its Nautobot write path is proven correct by direct evidence, but not through the real MCP transport, so it stays at the weaker level by design.

**On "unit-tested" in general** — see the clarifying exchange this doc was built from: the tool *call* (a Nautobot Custom Field write) has zero technical obstacle for all 30. All 30 could be live-verified this week with no external blocker. Where a real constraint exists, it sits in the Terraform/APIC layer beneath the tool, not in the tool itself — see §2 and §3.

---

## 2. Terraform modules/fixtures not fully live-verified

| # | Module / Resource / Fixture | Evidence | Reason |
|---|---|---|---|
| 1 | `aci_l3out_path_attachment` | **live-verified 2026-09-15 (apply, no destroy)** | Applied as part of the 93-resource `sales` apply. Confirmed: 2 × `l3extRsPathL3OutAtt` exist, both `state: unformed`, and **zero new faults**. The long-standing expectation is now measured, not reasoned |
| 2 | `aci_bgp_peer_connectivity_profile` | **live-verified 2026-09-15 (apply, no destroy)** | `bgpPeerP` + `bgpExtP` applied and present, zero new faults. A session still cannot establish (no switches) — that is a dataplane limit, not a config one |
| 3 | `aci_vrf_leak_epg_bd_subnet` | plan-verified only | Still no apply. The 2026-09-15 run did not cover it — `aci_vrf_route_leaks` is declared in Nautobot but unset, so the generator emitted nothing |
| 4 | `aci_concrete_interface` (physical L4-L7) | **live-verified, with a hard floor** | Apply+destroy proven; bottoms out at 6 faults — no leaf ports exist. See §3 |
| 5 | Virtual L4-L7 chain (`vnsLDevVip` VIRTUAL + VMM domain) | **applied live 2026-09-15 — and the result is a failed deployment** | The earlier "apply blocked on missing vCenter password" is resolved: a **controller-less** VMM domain removes the vCenter dependency entirely, and the whole PBR chain applied (93 added, 0 destroyed). But APIC flags the device and graph **invalid** — 10 new faults, all rooted in `vnsConfIssue-missing-cdev`. Adding a `vnsCDev` does not help (A/B measured: 10 → 10, trading them for F1778/F0765 vCenter-vNIC faults). **10 faults is the floor for a virtual L4-L7 device with no vCenter.** The fixture `l4l7-vmm-virtual.yaml` remains plan-verified only; this evidence comes from the generator-driven `sales` tenant |
| 6 | `l4l7-concrete-virtual.yaml` (virtual chain WITH a concrete device) | plan-verified only | `Plan: 30 to add`, 0 `pathep-` references. Proves the path `create_concrete_device` feeds: `vmm_controller_dn` and `vnic_name` both reach the provider, and the LIf-to-CIf relation is emitted. Apply needs a real vCenter holding the appliance VM — APIC resolves `vm_name`/`vnic_name` against live inventory, they are not free text |
| 7 | `l3out-interface-policies.yaml` (ND / DPP / PIM / IGMP / Custom QoS on an interface profile) | **live-verified 2026-09-16 (apply + destroy)** | `19 added` — `19 destroyed`; all seven relations `formed` with attribute values spot-checked; one fault (`F1298`, switch-absence family from the fixture's external EPG, not from any policy); zero policy leftovers after destroy. Needs no leaf port, switch or vCenter |
| 7 | `access-l3out-tools.yaml` fixture | plan-verified only, superseded | Reference fixture, not used for live testing anymore |
| 8 | Route control (`rtctrlProfile`/`rtctrlCtxP`/`rtctrlSubjP`/`rtctrlMatchRtDest`) | **live-verified 2026-09-16 (apply, no destroy)** | Applied into the real `sales` tenant with zero new faults; every object and both relations read back at `state: formed`. No destroy run — these are production objects for the transit lab, not a throwaway fixture |
| 8 | `l4l7-pbr.yaml` fixture | plan-verified only, superseded | Superseded by `l4l7-pbr-resilient.yaml` |
| 9 | `aci_rest_managed.fabric_node_identity` | live-verified, **gated off by default** | Proven both directions (apply+destroy); costs 3 extra faults on a switch-less fabric, so `register_fabric_membership = false` |

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
- **Virtual (VMM-backed) L4-L7** — **resolved and measured 2026-09-15; the old reasoning was wrong.** The blocker was never the vCenter password or reachability: a VMM domain can be created with **no controller at all**, which removes the vCenter dependency entirely, and the whole virtual chain then applies. But it does **not** reach zero faults. It bottoms out at **10**, all rooted in `vnsConfIssue-missing-cdev` — a logical device with no concrete device behind it is invalid, and a concrete device cannot be supplied without a vCenter to discover the VM's vNICs. A/B measured on a throwaway tenant: adding a `vnsCDev` holds the count at 10 and simply trades the faults for `F1778`/`F0765` vCenter-vNIC ones. So virtual L4-L7 has the *same* shape of hard floor as physical (6 faults, no leaf ports) — just a different cause.
- **Health Score policy** — genuinely unavailable in this APIC version (no resolvable class, confirmed by direct API testing). Not a hardware issue.

Unaffected entirely by this limitation: tenant/VRF/BD/EPG, contracts, VMM domain integration, fabric-wide POD policies (NTP/DNS/SNMP/COOP/ISIS), RBAC, syslog/fault.

---

## 4. Standing process gaps — not evidence-level facts, but adjacent

| Gap | Status |
|---|---|
| Unit test suites run in CI | **No.** Confirmed 2026-09-16 — no `pytest` invocation anywhere in `pipelines/` or `.gitlab-ci.yml`. All 526 tests are manual-only (400 mcp-server + 126 generator/fault-check) |
| Nautobot Custom Field schema bootstrap script | **Built 2026-09-17.** `platform/workflows/scripts/bootstrap_nautobot.py` declares all **32** `aci_*` fields, idempotent, with `--verify` as a non-destructive pre-flight check. Its cross-check test immediately found **12 fields the generator reads that had never been declared** — VRF and Bridge Domain attribute depth, plus EPG preferred-group — meaning that documented capability was silently inert through Nautobot. All now created and live-verified |
| Webhook coverage beyond Tenant | **Not fixed.** Only `tenancy.tenant` changes trigger the pipeline (finding F-04) |
| APIC fault-delta check (`check_apic_faults.py`) wired for EVPN | **Not wired.** Only wired into the ACI pipeline (`.verify_apic_faults` in `pipelines/aci.gitlab-ci.yml`) |
| `create_*` tools append instead of deduping | **Fixed for the known cases 2026-09-16.** A duplicate name is not clutter — `local.*` maps in `main.tf` are keyed by name, so Terraform fails outright with "Duplicate object key". Fixed in `create_contract`, `create_vlan_pool` and `create_leaf_interface_policy_group`; other `create_*` tools have not been audited |
| `location` defaults to a name that does not exist | **Fixed 2026-09-17 by removing the default, not by changing it.** The upstream repo has the same `"ACI-Lab"` default and **there it is correct** — two labs, two Location names, one shared codebase, so no literal default can be right for both. `_get_location_or_raise` now resolves at call time: explicit `location=` unchanged; omitted, it prefers a Location carrying `aci_fabric_policies` and raises naming the candidates rather than guessing. All 18 location-scoped tools behave identically now (three conventions existed before). Live-verified over MCP with no argument |
| Drift detection | **Does not exist.** Proven the hard way 2026-09-16: a test fixture's `terraform destroy` deleted the shared `ExtL3Dom` out from under the real `sales` L3Outs, leaving both domain relations at `state=missing-target`, and nothing noticed. `check_apic_faults.py` is scoped to what the current deployment declares and a `missing-target` relation raises no fault at all — fault checking is not drift detection |
| Non-converging `terraform plan` | **Fixed for the known cases 2026-09-16**, two remain. APIC HTML-escapes `<`/`>` in descriptions and upper-cases MACs, so plan never reached zero changes. Fixed in intent. Still open: `aci_function_node` interface names APIC does not return, and `aci_ospf_interface_policy.ctrl` (`[]` vs `["unspecified"]`) |
| Fault check blind to non-tenant objects | **Fixed 2026-09-15.** It anchored only on `tn-<name>/`, so faults on VMM domains, VLAN pools, physical/L3 domains, AEPs, policy groups and the access-policy hierarchy — none of which live under a tenant — were invisible. The PBR lab apply raised 7 such faults and the check reported none of them (all happened to be `cleared`, so nothing was missed that time). `managed_global_objects()` now derives the DN fragments from the generated YAML and scopes on them too, matching by exact declared name so unrelated fabric noise still cannot fail a run |

---

## 5. Session record — PBR lab build, 2026-09-15

The lab from `docs/Configure PBR LAB.docx`, built through the MCP tools and pushed to the APIC. Recorded here because it is the single largest body of live evidence in this document and several rows above cite it.

| Step | Result |
|---|---|
| Nautobot intent written via MCP tools | `vCenter_VMM_Pool`, `vCenter_VMM` (controller-less), `DB_BD` 10.0.2.254/24, `Backup_BD` 10.0.9.254/24, `DB_EPG` (vid 14), `Backup_EPG` (vid 15), `FW` (VIRTUAL/FW/GoTo), `DB_PBR` 10.0.2.253, `Backup_PBR` 10.0.9.253, `Web_Fltr` (tcp/80 + tcp/443), `FW_SGT`, `FW_Ct` |
| Generator | Clean after a real bug fix — see below. 1 tenant, 4 prefixes, 4 VLANs, 3 fabric nodes |
| `terraform plan` | `93 to add, 0 to change, 0 to destroy` |
| `terraform apply` | `93 added, 0 changed, 0 destroyed` |
| Fault delta | **FAIL — 10 new faults**, all under `tn-sales`, all rooted in `vnsConfIssue-missing-cdev` |
| Pre-existing objects | Untouched. Both static path bindings and all 4 access-policy objects re-written with byte-identical config; nothing deleted |

**Two real defects were found by doing this, neither of them in the lab config:**

1. **`transformer.py` crashed on a declared-but-unset Custom Field.** `.get(key, {})` applies its default only when the key is *absent*; a declared-but-unset Nautobot Custom Field comes back as an explicit `None`, so the default never fired and `None.get()` raised. One line had this form while every other field in the file already used `or {}`. It surfaced the moment `aci_ospf_interface_policies` was declared. Fixed, with a regression test that sets five JSON Custom Fields to `None` at once.

2. **Finding F-01 reproduced live.** The first L4-L7/PBR/graph writes reported OK and were silently discarded — `aci_l4l7_services` was not a declared Custom Field. Four fields were missing (`aci_l4l7_services`, `aci_vrf_route_leaks`, `aci_ospf_interface_policies` on `tenancy.tenant`; `aci_aaa_policies` on `dcim.location`). Declared them, re-ran the writes, verified persistence. This is the exact failure mode §4 still lists as an open gap — it is not theoretical.

**Deviation from the document, deliberate:** `create_pbr_contract` names the subject `FW_Ct-subj` rather than the document's `Web_Subj`. Functionally identical (same filter, same graph). All destructive steps in the document (6, 7, 9, 10, 11) and the vPC/access-policy steps 5–8 were skipped under the standing no-delete constraint.

---

*Last verified against the live registry and both test suites on 2026-09-15 — see `mcp-server/tests/unit/test_registry.py` for the drift guard that keeps §1's counts honest.*
