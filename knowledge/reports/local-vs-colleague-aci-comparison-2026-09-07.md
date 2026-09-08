# Local vs Colleague Repository Comparison

Date: 2026-09-07
Remote repository: `panosnaz/infra-automation-platform`, branch `master`, observed HEAD `09b02c8` (`feat(aci): Syslog/Fault monitoring policies (ADR-020 Phase G)`)
Local repository: `C:\MCP\INFRA-AUTOMATION-PLATFORM`

## Executive Summary

The two repositories share the same Platform v2 architecture and execution model, but they have diverged in feature focus. The colleague's repository is ahead in platform-wide ACI coverage: RBAC/security domains/local users, COOP/ISIS, and fault/syslog monitoring policies. The local checkout is ahead in the feature work developed during this session: physical/protocol L3Out intent, BGP/OSPF peer and interface modeling, VRF route-leak intent, L4-L7/PBR/service graphs, one-arm ADC graphs, OSPF interface policies, and editable lab templates.

This is a comparison, not a merge recommendation. Remote code was inspected read-only; no fetch, pull, merge, or copy was performed.

## Shared Foundation

Both repositories use the same architectural boundaries:

- Nautobot is the source of truth.
- A generator produces NetAsCode-style YAML.
- Terraform consumes the generated YAML and manages APIC desired state.
- GitLab provides validation, policy, plan, approval, apply, verification, and knowledge capture stages.
- Vault supplies runtime secrets.
- MCP tools write intent to Nautobot rather than directly orchestrating Terraform.
- Unit tests protect transformer/schema/tool behavior.

## Feature Comparison

| Area | Local checkout | Colleague remote HEAD |
|---|---|---|
| Core Tenant/VRF/BD/EPG | Implemented and tested | Implemented and tested |
| Contracts/Filters/Subjects | Implemented | Implemented |
| Logical L3Out | Implemented | Implemented |
| VLAN pools, Physical Domains, AAEP, IPG | Implemented | Implemented/refined |
| Leaf profiles/selectors/static paths | Implemented locally in current worktree; plan-validated | Access-policy work is present in remote history and MCP catalogue |
| VMM Domain | Implemented locally; plan-validated | Implemented, with refined domain-binding API |
| Physical/protocol L3Out | Local implementation includes node/interface profiles, SVI/path attachment, BGP peers, OSPF interfaces, and OSPF policy | Not evident in the inspected remote Terraform/MCP excerpts; verify before porting any related work |
| VRF route leaking | Local `create_vrf_route_leak`, generator, `aci_vrf_leak_epg_bd_subnet`, two-scenario fixture | Not evident in inspected remote excerpts |
| L4-L7/PBR/Service Graph | Local logical two-arm and one-arm support with PBR bindings | Not evident in inspected remote excerpts |
| OSPF interface policy | Local tool/resource supports network type, timers, passive flag, auth metadata | Not evident in inspected remote excerpts |
| RBAC/security domains/local users | Not present in local current implementation | Implemented in remote Phase F |
| COOP/ISIS/Pod Policy Groups | Not present locally | Implemented in remote Phase E |
| Fault lifecycle/syslog monitoring | Not present locally | Implemented in remote Phase G |
| EVPN domain | Implemented locally and live-verified | Implemented and live-verified |

## Detailed Difference Tables

### Platform and Architecture

| Difference | Local checkout | Colleague remote | Assessment |
|---|---|---|---|
| Primary ACI baseline | Platform v2 pipeline plus locally developed ACI extensions | Same Platform v2 baseline, with later ADR-020 phases | Architecture is shared; differences are feature phases, not a competing design |
| Source of truth | Nautobot objects and JSON Custom Fields | Nautobot objects and JSON Custom Fields | Equivalent principle |
| Desired-state artifact | Generated NetAsCode-style YAML under `platform/netascode/aci/` | Same artifact and path | Compatible contract; schema changes must be reconciled |
| Pipeline ownership | GitLab pipeline owns validation, policy, plan, approval, apply, verification, capture | Same lifecycle | Equivalent |
| MCP responsibility | Writes intent; does not orchestrate Terraform | Same documented boundary | Equivalent |
| ACI coverage emphasis | Physical/protocol L3Out, route leaks, L4-L7/PBR, OSPF policy | RBAC, COOP/ISIS, fault/syslog monitoring | Complementary feature priorities |
| Remote progress marker | Local report date: 2026-09-07 | Remote HEAD `09b02c8`, Syslog/Fault Phase G, observed 4 days before report date | Remote has newer upstream feature history in platform-wide policy areas |

### Terraform Module Differences

| Capability | Local Terraform implementation | Remote evidence observed | Difference / action |
|---|---|---|---|
| Tenant/VRF/BD/Subnet | `aci_tenant`, `aci_vrf`, `aci_bridge_domain`, `aci_subnet` | Same resource family | No material difference identified |
| EPGs | `aci_application_profile`, `aci_application_epg` | Same Phase A family; remote tests also cover EPG domains | Compare relation schema before reconciliation |
| Contracts/Filters | `aci_filter`, `aci_filter_entry`, `aci_contract`, `aci_contract_subject`, `aci_epg_to_contract` | Same Phase A family | No material difference identified |
| Logical L3Out | `aci_l3_outside`, external EPG, external subnet | Same logical L3Out baseline | Both require physical/protocol extensions for full routing |
| VLAN/access objects | VLAN pools, ranges, physical domains, AAEPs, IPGs | Remote has refined Access/Fabric Policy work | Remote may have better append/update semantics; compare exact JSON schemas |
| IPG policy resources | CDP, LLDP, link-level, spanning-tree, port-security | Remote access-policy work is present | Local added dedicated policy relations and provider enum mappings |
| Leaf interface path | Leaf profile, access selector, EPG static path | Remote access-policy work exists in history/catalogue | Compare physical path resource semantics before merging |
| EPG domain binding | Local separate physical/VMM binding paths | Remote consolidated `bind_epg_domain` API and domain-aware schema | API consolidation opportunity; not a safe mechanical merge |
| VMM | VMM domain/controller/credential and VLAN-pool relation | Remote VMM with refined EPG/domain semantics | Compare credential relation and EPG relation handling |
| BGP L3Out | Logical node/profile, fabric node, interface profile, path/SVI attachment, BGP protocol and peer resources | Not evident in inspected remote excerpts | Local feature appears ahead; confirm with full remote file-level diff before merge |
| OSPF L3Out | OSPF interface profile and typed OSPF policy | Not evident in inspected remote excerpts | Local feature appears ahead |
| OSPF interface policy | `aci_ospf_interface_policy`, provider enum translation `point-to-point -> p2p`, `broadcast -> bcast` | Not evident in inspected remote excerpts | Local feature appears ahead |
| VRF route leaking | `aci_vrf_leak_epg_bd_subnet` with destination VRF, subnet, advertisement flag | Not evident in inspected remote excerpts | Local feature appears ahead; source-VRF provider limitation remains |
| L4-L7/PBR | Logical device, graph, logical contexts, redirect policies/destinations | Not evident in inspected remote excerpts | Local feature appears ahead in inspected scope |
| One-arm ADC graph | Dedicated one-arm tool and one-context Terraform path | Not evident in inspected remote excerpts | Local feature appears ahead |
| COOP/ISIS | Not present locally | Remote typed `aci_coop_policy`, `aci_isis_domain_policy` and Pod Policy Groups | Remote ahead; candidate feature to port conceptually |
| RBAC | Not present locally | Remote AAA/security-domain/local-user Terraform resources | Remote ahead; secrets need careful local adaptation |
| Fault/syslog monitoring | Not present locally | Remote Phase G singleton policies with destroy-safe handling | Remote ahead; preserve `content_on_destroy` safety pattern |

### MCP Tool and Schema Differences

| MCP area | Local checkout | Colleague remote | Difference / action |
|---|---|---|---|
| Core tools | Tenant, VRF, BD, EPG, Contract, L3Out, route leak | Same core plus refined access APIs | Shared baseline |
| VLAN pool | `create_vlan_pool` exists in local current worktree | Remote has `create_vlan_pool` with append-range semantics | Remote API is more mature; compare range merge/idempotency |
| Physical domain | `create_physical_domain` | Remote `create_physical_domain` | Compare defaults and prerequisite validation |
| AAEP | `create_aaep` | Remote `create_aep` naming | Naming/API compatibility issue; choose one canonical public name or alias |
| IPG | `create_leaf_interface_policy_group` | Remote same concept | Compare policy relation fields |
| Leaf profiles/selectors | Local tools exist | Remote access-policy catalogue exists | Compare exact request schema and live inventory validation |
| Static path | Local `create_static_path_binding` | Remote access-policy work present | Compare path DN, encapsulation, and update semantics |
| EPG domain bindings | Separate `bind_epg_to_physical_domain` and `bind_epg_to_vmm_domain` | Consolidated `bind_epg_domain` with `domain_type` | Remote API is more general; local split API is more explicit |
| VMM | `create_vmm_domain` | `create_vmm_domain` | Remote schema/docs are more mature |
| L3Out protocols | Local BGP/OSPF L3Out, node/interface, peer, OSPF policy tools | Not evident in inspected remote tools | Local appears ahead |
| VRF leak | Local `create_vrf_route_leak` | Not evident in inspected remote tools | Local appears ahead |
| L4-L7/PBR | Local two-arm and one-arm tools | Not evident in inspected remote tools | Local appears ahead |
| RBAC/security | Not present locally | `create_security_domain`, `create_local_user` | Remote ahead |
| Status | `show_status` | `show_status` and same pipeline-status concept | Shared |
| Secret boundary | Local avoids raw VMM/OSPF secrets in MCP; uses references/runtime variables | Remote local-user password also uses Terraform-sensitive runtime input | Same security direction; reconcile secret variable names carefully |

### Generator and Intent Schema Differences

| Intent surface | Local checkout | Colleague remote | Difference / action |
|---|---|---|---|
| Location fabric policies | VLAN pools, domains, AAEPs, IPGs, leaf profiles/selectors, VMM, policy settings | Also expanded with COOP/ISIS, Pod Policy Groups, monitoring policies | Remote has broader fabric policy schema |
| Tenant policy | VRFs, BDs, EPGs, contracts, L3Outs, route leaks, L4-L7 services, OSPF policies | Same baseline plus remote Phase F/G surfaces | Schemas need additive merge, not replacement |
| EPG custom fields | Physical/VMM bindings and static paths | Remote uses domain-aware `aci_epg_domains` style in inspected tests | This is a likely reconciliation hotspot |
| L3Out schema | Node profiles, interface profiles, interfaces, BGP peers, OSPF entries | Remote baseline excerpts did not show equivalent full protocol path | Validate before combining |
| Generator tests | 25 transformer tests in latest local focused run | Remote transformer tests cover additional COOP/ISIS, AAA, Pod Policy, syslog/fault keys | Remote has broader generator coverage |

### Test and Validation Differences

| Test/validation layer | Local checkout | Colleague remote | Difference / action |
|---|---|---|---|
| Transformer unit tests | `tests/unit/test_transformer.py`; 25 passing in latest focused run | Same file covers more remote phases, including AAA and monitoring | Remote has broader current test surface |
| MCP schema tests | `mcp-server/tests/unit/test_schemas_aci.py` | Same file with more Phase F/access schemas | Remote ahead in catalogue coverage |
| MCP tool tests | `mcp-server/tests/unit/test_tools_aci.py` | Same file covers VLAN pools, AAEP/IPG, VMM/domain binding, RBAC | Remote ahead in those areas |
| Registry tests | `mcp-server/tests/unit/test_registry.py` | Same registry/signature checks | Shared quality gate |
| EVPN tests | Local EVPN transformer/MCP/pyATS-equivalent tests | Remote EVPN tests and live validation | Both have second-domain coverage |
| Terraform validation | Local `fmt`, `validate`, APIC-backed temporary-state plans for new local fixtures | Remote repository documents broader Phase E/F/G implementation; full local execution not performed from this comparison | Run both suites after reconciliation |
| Physical L3Out validation | Local plan validated `22 to add, 0 to change, 0 to destroy` for combined access/L3Out fixture | Not established from inspected remote excerpts | Local plan evidence exists; apply still requires approval |
| OSPF policy validation | Local APIC-backed plan validated `23 to add, 0 to change, 0 to destroy` | Not established from inspected remote excerpts | Local plan evidence exists |
| IPG policy validation | Local APIC-backed plan validated `27 to add, 0 to change, 0 to destroy` | Not established from inspected remote excerpts | Local plan evidence exists |
| Live apply status | No apply performed for the newly developed local access/protocol/L4-L7 scope | Remote README/history documents live verification for several earlier domains and newer platform phases | Do not infer apply readiness from plan alone |

### Operational and Documentation Differences

| Area | Local checkout | Colleague remote | Difference / action |
|---|---|---|---|
| Local Nautobot endpoint | Isolated instance on port 8081 in current workspace | Remote README contains older port-8080/default credential references in its active-lab section | Use local administration guide, not remote README values |
| Provider version | Local ACI provider pinned to 2.20.0 and schema-checked locally | Remote uses the same project lineage but version must be checked before merge | Re-run provider schema comparison |
| Current ADR state | Local ADR-020 includes locally developed Phase D-G style additions from this session | Remote ADR-020/commits contain its own Phase E/F/G progression | Reconcile ADR history manually; do not overwrite decisions |
| Templates | Local four-file ACI lab templates under `knowledge/runbooks/templates/aci/` | Not established in inspected remote tree | Keep local templates as scenario-specific input aids |
| Report confidence | Local counts and plan results verified in this worktree | Remote comparison based on public page/raw files and commit/tree evidence | Full commit-level diff still requires a separately approved read-only clone/fetch process |

## Difference Summary

| Category | Local advantage | Remote advantage |
|---|---|---|
| New network-service features | Full physical/protocol L3Out path, route leaks, L4-L7/PBR, one-arm ADC, OSPF policy | None identified in inspected scope |
| Platform-wide ACI policy | None identified for COOP/ISIS, RBAC, monitoring | COOP/ISIS, Pod Policy Groups, RBAC/security domains/local users, fault/syslog monitoring |
| MCP API maturity | More detailed L3Out/L4-L7 operations | More consolidated/refined access and RBAC APIs |
| Generator coverage | Local new service-chain and route-leak intent | Broader platform-policy intent and tests |
| Validation evidence | Local APIC-backed plans for newly added scopes | Remote documented/live evidence for several established phases |

## Recommended Reconciliation Order

1. Compare remote Phase E/F/G Terraform resources and transformer sections against local `main.tf`/`transformer.py` manually.
2. Port concepts, not files: COOP/ISIS, RBAC, and monitoring resources should be adapted to the local isolated-stack paths and secret conventions.
3. Preserve local L3Out protocol, VRF-leak, L4-L7/PBR, OSPF policy, and template work unless remote has a verified newer equivalent.
4. Reconcile MCP naming, especially remote `bind_epg_domain` versus local split physical/VMM binding tools.
5. Add/merge unit tests before changing generated YAML schema.
6. Run both local test suites and Terraform validation.
7. Run APIC-backed plans with temporary state.
8. Apply only after explicit review and approval.

## Local Terraform References

Primary module:

- [platform/terraform/aci/main.tf](../../platform/terraform/aci/main.tf)
- [platform/terraform/aci/providers.tf](../../platform/terraform/aci/providers.tf)
- [platform/terraform/aci/variables.tf](../../platform/terraform/aci/variables.tf)

The local ACI module currently contains 52 Terraform resource blocks. Relevant resource families include:

- Core: `aci_tenant`, `aci_vrf`, `aci_bridge_domain`, `aci_subnet`, `aci_application_profile`, `aci_application_epg`
- Policy: `aci_filter`, `aci_filter_entry`, `aci_contract`, `aci_contract_subject`, `aci_epg_to_contract`
- Logical L3Out: `aci_l3_outside`, `aci_external_network_instance_profile`, `aci_l3_ext_subnet`
- Access: `aci_vlan_pool`, `aci_ranges`, `aci_physical_domain`, `aci_attachable_access_entity_profile`, `aci_leaf_access_port_policy_group`
- IPG policies: `aci_cdp_interface_policy`, `aci_lldp_interface_policy`, `aci_link_level_interface_policy`, `aci_spanning_tree_interface_policy`, `aci_port_security_interface_policy`
- Physical access: `aci_leaf_interface_profile`, `aci_access_port_selector`, `aci_epg_to_domain`, `aci_epg_to_static_path`
- L3Out protocol path: `aci_logical_node_profile`, `aci_logical_node_to_fabric_node`, `aci_logical_interface_profile`, `aci_l3out_path_attachment`, `aci_l3out_floating_svi`, `aci_l3out_bgp_protocol_profile`, `aci_bgp_peer_connectivity_profile`, `aci_l3out_ospf_interface_profile`, `aci_ospf_interface_policy`
- VMM/L4-L7: VMM domain/controller/credential resources, L4-L7 device/interface, service graph, logical contexts, redirect policies/destinations
- VRF leaks: `aci_vrf_leak_epg_bd_subnet`

The local provider is pinned to `CiscoDevNet/aci` 2.20.0 in `providers.tf` and all new resource fields were checked against its local schema.

## Local MCP References

Primary files:

- [mcp-server/src/mcp_server/tools/aci.py](../../mcp-server/src/mcp_server/tools/aci.py)
- [mcp-server/src/mcp_server/schemas/aci.py](../../mcp-server/src/mcp_server/schemas/aci.py)
- [mcp-server/src/mcp_server/clients/nautobot.py](../../mcp-server/src/mcp_server/clients/nautobot.py)

Local feature families include:

- Core: `create_tenant`, `create_vrf`, `create_bridge_domain`, `create_epg`
- Policy/L3Out: `create_contract`, `create_l3out`, `create_vrf_route_leak`
- Access: `create_vlan_pool`, `create_physical_domain`, `create_aaep`, `create_leaf_interface_policy_group`, `create_leaf_interface_profile`, `create_interface_selector`, `create_static_path_binding`, `bind_epg_to_physical_domain`, `bind_epg_to_vmm_domain`
- L3Out protocols: `create_bgp_l3out`, `create_ospf_l3out`, `create_l3out_node_profile`, `create_l3out_interface_profile`, `create_l3out_interface`, `create_bgp_peer`, `create_ospf_interface`, `create_ospf_interface_policy`
- VMM: `create_vmm_domain`
- L4-L7: `create_l4l7_device`, `create_service_graph`, `create_one_arm_service_graph`, `create_pbr_policy`, `create_pbr_contract`
- Status: `show_status`

Remote MCP comparison: the inspected remote branch explicitly includes refined `create_vlan_pool`, `create_physical_domain`, `create_aep`, `create_leaf_interface_policy_group`, `bind_epg_domain`, `create_security_domain`, and `create_local_user` APIs. Its access schemas use append/update semantics and domain-type-aware EPG bindings. The local names are compatible in intent but should not be blindly copied because the local worktree has additional L3Out/L4-L7 behavior and a different schema evolution.

## Unit-Test References

Local test files:

- [tests/unit/test_transformer.py](../../tests/unit/test_transformer.py): generator regression and emitted YAML coverage, including VRF/BD depth, EPGs, contracts, L3Outs, access policies, VMM, L4-L7, and route leaks.
- [mcp-server/tests/unit/test_schemas_aci.py](../../mcp-server/tests/unit/test_schemas_aci.py): Pydantic validation for ACI MCP requests.
- [mcp-server/tests/unit/test_tools_aci.py](../../mcp-server/tests/unit/test_tools_aci.py): tool-to-client argument/response behavior.
- [mcp-server/tests/unit/test_registry.py](../../mcp-server/tests/unit/test_registry.py): catalogue and schema-signature guarantees.
- [tests/unit/test_evpn_transformer.py](../../tests/unit/test_evpn_transformer.py) and EVPN MCP tests: second-domain regression coverage.

The last local focused validation recorded during this work was 25 transformer tests and 39 MCP schema/tool/registry tests passing. The local combined access/L3Out plan validated `22 to add, 0 to change, 0 to destroy`; the OSPF policy plan validated `23 to add, 0 to change, 0 to destroy`; the IPG policy plan validated `27 to add, 0 to change, 0 to destroy`.

Remote test references observed in the repository tree and raw files:

- `tests/unit/test_transformer.py`: broad transformer coverage, including access policies, VMM, COOP/ISIS, Pod Policy Groups, fault/syslog policies, and AAA policy emission.
- `mcp-server/tests/unit/test_tools_aci.py`: tool-level tests for VLAN pools, Physical Domains, AAEPs, IPGs, VMM, domain binding, Security Domains, and Local Users.
- `mcp-server/tests/unit/test_schemas_aci.py`: request validation for the expanded remote tool catalogue.
- `mcp-server/tests/unit/test_registry.py`: MCP registry/signature checks.
- EVPN transformer, MCP, integration, and pyATS-equivalent tests remain present in both project lines.

## Recommended Reconciliation

1. Treat the remote branch as the reference for Phase E/F/G ACI coverage: COOP/ISIS, RBAC/security domains/local users, and fault/syslog monitoring.
2. Preserve the local L3Out protocol, VRF-leak, L4-L7/PBR, one-arm service graph, OSPF-policy, and lab-template work unless the remote branch has a newer equivalent after direct file comparison.
3. Compare schema/API changes before any merge. In particular, remote `bind_epg_domain` is a consolidated physical/VMM operation, while the local checkout currently has separate `bind_epg_to_physical_domain` and `bind_epg_to_vmm_domain` tools.
4. Reconcile generated YAML schema changes before combining Terraform modules; do not merge `main.tf` mechanically.
5. Run both repositories' unit suites and Terraform validation after reconciliation.
6. Perform APIC-backed plans with temporary state before any apply.

## Limitations

This report is based on read-only inspection of the public remote repository page/raw files and the current local worktree. It does not claim a commit-level semantic diff of every file. No remote code was fetched, merged, or copied. The remote README contains older operational values in places; use the local repository's current administration guide and isolated-stack configuration for local credentials and endpoints.
