---
type: adr
domain: vxlan_evpn
status: active
tags: [evpn, nexus, vxlan, domain-expansion, generator, terraform, nxos]
owner: platform-engineering-team
last_updated: 2026-07-31
---

# ADR-021 — Domain Expansion Phase 2: Cisco Nexus VXLAN EVPN

**Status:** Accepted — schema, generator, Terraform module, and Ansible playbooks are complete; **live verification achieved (2026-07-30)** — a real `terraform apply`/`plan`/`destroy` cycle succeeded against a genuine Nexus 9000v device (`DC1-Leaf`) via a jump host inside the CML lab network. 3 of 4 real nodes have working NX-API. A real destroy-safety bug was found in `nxos_feature` (see §6) and mitigated with `lifecycle { prevent_destroy = true }` (§7, 2026-07-31) — no attribute-level fix exists in the provider's real schema.

**Date:** 2026-07-29

**Decision Makers:** Platform Engineering Team

**Related ADRs:**

- ADR-002 — Terraform as the Declarative Provisioning Engine (this ADR is the second domain proving that role generalizes)
- ADR-003 — Ansible Day-2 Operations (same generalization, for Day-2)
- ADR-007 — Cisco NetAsCode as the Canonical Engineering Model (EVPN gets its own dialect, per that ADR's explicit design)
- ADR-017 — Execution Framework (the pipeline this expansion reuses unchanged)
- ADR-018 — NetAsCode YAML as the Authoritative Intent Artifact (governs how EVPN's YAML is produced: by a generator reading Nautobot, never a parallel schema)
- ADR-019 — Three Truths Principle (EVPN objects fit Nautobot's DCIM/IPAM model, per its own worked example — this ADR is the proof)
- ADR-020 — ACI Domain Coverage Expansion (the direct precedent this ADR replicates the pattern of)

---

# Context

[Roadmap.md](../architecture/Roadmap.md) has named Cisco Nexus VXLAN EVPN as "Phase 2" of Infrastructure Domain Expansion since this repository's earliest planning documents — EVPN is referenced as a planned future domain in over a dozen architecture documents and ADRs (ADR-001, ADR-002, ADR-003, ADR-007, ADR-012, ADR-014, ADR-018, ADR-019, ADR-020, `Platform-v2-Reference-Architecture.md`, `Domain-Expansion-Model.md`, among others). Until now, none of that had been implemented — no generator, no Terraform module, no Ansible playbooks, no pipeline file, no Nautobot data model decisions. This ADR is the first concrete design and implementation for this domain.

With ADR-020 complete, the Execution Framework's mechanism (generator → GitLab CI → Terraform/Ansible/pyATS → Nautobot/MinIO) has now been proven twice for a single domain (Cisco ACI, across Phase A tenant-policy-depth and Phase B access/fabric-policy work). Per ADR-018's design intent ("no change to the MCP Server's dispatcher, the GitLab shared stage templates, or Nautobot's core setup is required" for a new domain), EVPN is the natural next step to prove that the mechanism — not just the ACI domain — actually generalizes, which is the whole architectural point of this platform.

## The simulator gap — stated honestly, not glossed over

Cisco ACI has a real simulator reachable in this lab (`172.30.46.103`), which is what let ADR-020's work be live-verified end to end (real `terraform apply`/`destroy` proofs for every item). **No equivalent Nexus/NX-OS simulator exists anywhere in this lab today.** The `CiscoDevNet/nxos` Terraform provider (confirmed via the Terraform Registry, not assumed) is tested against "Nexus 9Kv" — Cisco's virtual Nexus appliance, distributed as a VM image (qcow2/OVA), not a Docker container. Standing one up is a real infrastructure project of its own, out of scope for this ADR.

**Decision (confirmed with the user before starting this work):** proceed with the schema, generator, Terraform module, and Ansible playbooks now, verified only via `terraform validate`/`plan`-level correctness against the real provider's schema — not a live `apply`. Live verification (`terraform apply`, pyATS) is deferred until a Nexus 9Kv instance (or equivalent) is stood up and reachable. This mirrors, but is more fundamental than, ADR-020 Phase B's "logical-only" scope (which still had a real simulator to plan/apply against for everything except physical interfaces) — here, nothing can be applied at all yet.

---

# Decision

## 1. Terraform provider — confirmed real, not assumed

[`CiscoDevNet/nxos`](https://registry.terraform.io/providers/CiscoDevNet/nxos/latest/docs) (latest: v0.13.1), communicating via NX-API REST (`feature nxapi` required on the target device). Key resources for this domain's first slice, confirmed against the provider's own "Supported Objects" guide:

| Terraform resource | NX-OS DME object(s) | Purpose |
|---|---|---|
| `nxos_feature` | `fmEvpn`, `fmBgp`, `fmNvo`, `fmVnSegment`, `fmInterfaceVlan` | Enable the features EVPN/VXLAN requires before anything else can be configured |
| `nxos_vrf` | `l3Inst`, `rtctrlDom`, `rtctrlDomAf` | L3 VRF (tenant separation) |
| `nxos_bridge_domain` | `l2BD` | L2 bridge domain (the VLAN equivalent in NX-OS's data model) |
| `nxos_nvo` | `nvoNw`, `nvoEp`, `nvoIngRepl` | VNI-to-bridge-domain mapping, NVE/VTEP config, ingress replication (the core VXLAN overlay piece) |
| `nxos_evpn` | `rtctrlL2Evpn`, `rtctrlBDEvi` | EVPN route-target and Bridge-Domain-EVI (EVI) mapping |
| `nxos_bgp` | `bgpEntity`, `bgpInst`, `bgpDom`, `bgpDomAf` | BGP, including the L2VPN EVPN address-family that actually distributes MAC/IP routes |
| `nxos_svi_interface` | `sviIf` | SVI gateway interfaces for each bridge domain |

All other NX-OS objects not in this table remain out of scope for this first slice (interfaces/VPC/routing-protocol depth follow the same "add when proven needed" discipline ADR-020 already established for ACI).

## 2. Nautobot data model mapping (per ADR-019's rule: EVPN fits Nautobot's DCIM/IPAM model, so it lives there — no new SoT)

Reuses existing Nautobot models exactly like ACI does, with a distinct namespace prefix so ACI and EVPN objects never collide in the same Nautobot instance:

| EVPN concept | Nautobot object | Notes |
|---|---|---|
| Fabric/tenant | `Tenant` (name prefixed `EVPN:`, stripped by the generator exactly like `ACI:` is) | Mirrors ADR-020's existing `_strip_aci_prefix`-style convention — generalized to a per-domain prefix |
| VRF | `VRF` (existing IPAM model) | Same object Nautobot already has; a VRF used for EVPN vs. ACI is disambiguated purely by which Tenant it belongs to |
| L3 VNI (per-VRF) | `VRF.custom_fields.evpn_l3_vni` | New Custom Field, JSON-free (plain integer) since it's a single scalar per VRF — simpler than ACI's JSON-custom-field pattern (used there because Contracts/L3Outs are structured, nested data; a VNI is not) |
| Bridge Domain / VLAN | `VLAN` (existing IPAM model, not `Prefix` as ACI's Bridge Domain uses — EVPN's bridge domain is fundamentally VLAN-based, not prefix-derived) | New usage of an existing Nautobot model — ACI's generator never touched `VLAN` for Bridge Domains (it used `Prefix`); EVPN's does, since NX-OS bridge domains are literally VLANs |
| L2 VNI (per-VLAN) | `VLAN.custom_fields.evpn_l2_vni` | New Custom Field, plain integer |
| BD gateway IP (SVI) | `Prefix` scoped to the VLAN (Nautobot's existing VLAN↔Prefix relationship) | Reuses the exact same "first host = gateway" convention `transformer.py` already established for ACI Bridge Domains |
| Fabric-wide BGP ASN / EVPN config | `Device.custom_fields.evpn_bgp_asn`, `evpn_role` (`leaf`/`spine`/`border-leaf`) | `Device` is the correct Nautobot object here (not `Location`, unlike ADR-020 Phase B's fabric policies) — EVPN's BGP ASN and role are genuinely per-device, not fabric-wide |

No new Nautobot plugin or custom model is required — this follows ADR-020's own precedent exactly (Custom Fields on existing models, nothing more, until real usage proves a first-class model is worth the cost).

## 3. Generator, Terraform module, Ansible, pipeline — file layout (mirrors ACI exactly, per ADR-018's "same pattern, new files" rule)

| Layer | ACI (existing) | EVPN (this ADR) |
|---|---|---|
| Generator | `platform/python/generate_aci.py` + `generator/{client,transformer}.py` | `platform/python/generate_evpn.py` + `generator/evpn_{client,transformer}.py` |
| NetAsCode-equivalent YAML | `platform/netascode/aci/tenants.yaml` | `platform/netascode/evpn/fabric.yaml` |
| Terraform module | `platform/terraform/aci/` | `platform/terraform/evpn/` |
| Ansible | `platform/ansible/aci/` | `platform/ansible/evpn/` |
| GitLab pipeline | `pipelines/aci.gitlab-ci.yml` | `pipelines/evpn.gitlab-ci.yml` (extends the same `pipelines/includes/common.gitlab-ci.yml` shared stage templates, unchanged) |
| pyATS | `tests/pyats/aci/` | `tests/pyats/evpn/` (scaffolded now, real tests deferred to the simulator-gap resolution) |
| OPA policy domain | `data.platform.cisco_aci.decision` | `data.platform.vxlan_evpn.decision` — exactly the extension point ADR-014 already named in advance |

## 4. MCP tools — added and live-verified (2026-07-30)

Following the exact `tools/aci.py` pattern: `schemas/evpn.py` (thin per-tool Pydantic schemas, VNI range validated against `nxos_nvo`'s confirmed 1-16777214 range) and `tools/evpn.py` (`create_evpn_tenant`, `create_evpn_vrf`, `create_evpn_bridge_domain`), each a direct Nautobot write with no shared intent envelope, exactly as ADR-018 mandates. Domain-isolated from `tools/aci.py` (neither imports the other). Live-verified over the real MCP protocol (not just unit tests): rebuilt and restarted the `mcp-server` container, connected a real `mcp.ClientSession` over `streamable-http`, and called all three tools in sequence (tenant → VRF → bridge domain) — all three wrote correctly to Nautobot with proper `EVPN:` prefixing and VNI Custom Fields set. Test data cleaned up afterward.

## 5. Live verification against a real CML instance (2026-07-30) — genuine progress, genuine blocker found

**The "no Nexus 9Kv simulator exists" gap from the Context section above is now partially closed**: a real Cisco Modeling Labs instance (`172.30.46.250`, CML 2.10.0, Personal license) was found with an already-running `VXLAN-EVPN-MultiSite` lab — 4 genuine Nexus 9000v nodes (`DC1-Leaf`, `DC1-BGW`, `DC2-Leaf`, `DC2-BGW`), 2 DC sites, BGW-to-BGW DCI eBGP EVPN, matching this ADR's topology almost exactly. This is real Nexus virtualization (Cisco's own NX-OS image), not a mock — confirmed via CML's REST API (`/api/v0/labs`, `/api/v0/nodes`), not assumed.

**Real progress made:**
- Confirmed via CML's own pyATS testbed export (`GET /labs/{lab}/pyats_testbed`) that only console access existed initially — no `mgmt0`/NX-API path for Terraform to reach these nodes.
- Console-configured (via CML's SSH terminal-server proxy, `ssh admin@172.30.46.250 "open /VXLAN-EVPN-MultiSite/<node>/0"`) `mgmt0` + `feature nxapi` + `nxapi https port 443` on 3 of 4 nodes — `DC1-Leaf` (`172.30.46.220`), `DC2-Leaf` (`172.30.46.222`), `DC2-BGW` (`172.30.46.223`) — each confirmed live via `show interface mgmt0` and saved to `startup-config`. `DC1-BGW` deferred — its console had an unrelated stuck paginated command from a prior session that could not be cleared in reasonable time.
- Built an out-of-band management network in the lab topology itself (one `external_connector` + one `unmanaged_switch` hub, all 4 nodes' `mgmt0` wired to it) via the CML REST API (`POST .../nodes`, `POST .../interfaces`, `POST .../links`).

**Two real, sequential blockers found (both confirmed via evidence, not guessed):**
1. **Bridge-mode external connectivity does not work on this CML instance.** The `external_connector` node accepted a `"Bridge"` configuration and returned `204` on start, but never left `DEFINED_ON_CORE`/`boot_progress: "Not running"` — confirmed via repeated state polling, not a one-off. Switching the same node to `"NAT"` mode let it reach `STARTED` immediately, isolating the problem to Bridge mode specifically (not a generic external-connector failure). NAT mode is outbound-only by CML's own design (confirmed in the CML 2.10 release notes), so it doesn't solve inbound reachability — this is a real, currently-unexplained CML host/network configuration gap, not something fixable via the REST API alone.
2. **The CML host is genuinely out of memory.** Pivoted to running Terraform from a jump host inside the lab's own network (same OOB-switch as the 4 real nodes) instead of relying on Bridge mode. The jump host (`ubuntu`, needs 2 GB) never scheduled — confirmed via the CML controller's own log (`journalctl -u virl2-controller`, obtained by the user via Cockpit): `ERROR: core_controller:1610:Failed to choose a suitable compute host: ... Not enough memory: needed 2.0 GB, available 1.25 MB` (repeated across multiple retries, 57.6 KB–14 MB free each time). Checked whether a lighter node would fit: `alpine` needs 512 MB per its own node definition — still far more than the ~1–14 MB actually free. The 4 running Nexus 9000v nodes have consumed nearly all of this host's RAM; the host log shows it oscillating between `overloaded`/`no longer overloaded`.

**Not fixed, deliberately not brute-forced further**: per this ADR's own established discipline (state real blockers honestly, don't guess past them), both issues were diagnosed with concrete evidence and then stopped, rather than continuing to guess at CML host configuration or reducing the running topology to force a fit. The stuck/unschedulable jump-host node was cleaned up (stopped + deleted) to stop it retrying forever and spamming the controller log. The OOB-switch + NAT-mode external-connector were left in place (both are lightweight/license-exempt node types, no ongoing cost) for reuse once the underlying constraints are resolved.

**What would actually unblock this** (tracked as pending, not attempted in this pass): (a) more RAM added to the CML host (infrastructure change, not a code/config fix), or freeing capacity by stopping one of the 4 real EVPN nodes temporarily (undesirable — defeats the point of testing the full 4-node Multi-Site topology); (b) understanding why Bridge-mode external connectivity doesn't work on this specific CML instance, likely requiring System Administration Cockpit access this session didn't have, to check for a host-level Bridge/external-network configuration step CML may require beyond what the per-lab REST API exposes.

## 6. First real `terraform apply` against live Nexus 9000v hardware — historic milestone, plus a real destroy bug found (2026-07-30, same day)

**Blocker (a) from §5 was resolved within the same session**: the CML host's RAM was increased to 128 GB (from a host that had ~64 GB, of which the 4 running Nexus 9000v nodes alone consumed 48 GB — each needs 12 GB, confirmed via its node definition, not assumed). After the increase, the `alpine` node type (512 MB, far lighter than the `ubuntu` node originally tried) scheduled and booted immediately — no more indefinite `QUEUED` state.

**Blocker (b) from §5 (Bridge-mode networking) was sidestepped, not fixed** — the jump-host-inside-the-lab-network approach (proposed as a fallback in §5) is what actually worked:
- `alpine` jump host wired with two NICs: one to the OOB-management hub (same L2 segment as the 4 real switches' `mgmt0`), one to the NAT-mode `external_connector` (confirmed working in §5) for outbound package access.
- Confirmed real NX-API reachability from the jump host to all 3 configured switches: `wget --no-check-certificate https://<ip>/ins` returned `401 Unauthorized` (the correct response without credentials) on `DC1-Leaf`/`DC2-Leaf`/`DC2-BGW` — proof NX-API is genuinely live and answering, not just that the port is open.
- **Provider binary transfer was its own real blocker**: `registry.terraform.io` (Terraform's own strict TLS client) and `github.com` (via `wget`, both with and without a browser User-Agent) were both blocked/403'd from the lab's NAT egress path — two distinct, confirmed failures, not a single fluke. Resolved via CML's own SCP/SFTP dropfolder (confirmed real via CML's 2.10 release notes security-fix entries): `sftp`'d the provider zip (mirrored locally first via `terraform providers mirror`, only 8.8 MB compressed — much smaller than assumed) to the CML controller's dropfolder over the external address, then discovered the **same dropfolder is also reachable from inside the lab network** via the NAT gateway's own address (`192.168.255.1`, the same IP CML's own release notes describe as the internal NAT/DHCP address) — `sftp get` from the alpine jump host pulled the file across entirely within the lab, no external network dependency at all. Extracted and pointed Terraform's CLI config (`~/.terraformrc`, `provider_installation { filesystem_mirror { path = ... } }`) at it — `terraform init` succeeded using **only** the local mirror.
- **Real, live `terraform plan` → `apply` → `plan` (0 diff) → `destroy` cycle against `DC1-Leaf`** (a genuine Nexus 9000v, not a mock), using the exact `nxos_feature` resource and attributes already committed in this ADR's `main.tf` (`bgp`, `evpn`, `nv_overlay`, `vn_segment`, `interface_vlan`, all `"enabled"`): `terraform apply` reported `Apply complete! Resources: 1 added`; a follow-up `terraform plan` reported `No changes. Your infrastructure matches the configuration` (correctly read real device state back); independently confirmed live via two different channels — direct NX-API JSON query (`show feature` via `POST /ins`) and the device's own CLI — that `bgp`/`interface-vlan` were genuinely `enabled`, not just reported enabled by Terraform.

**Real bug found via the destroy step (same class as ADR-020 Phase C's `aci_rest_managed` finding)**: `terraform destroy` reported `Destruction complete after 0s` / `Resources: 1 destroyed`, but an independent NX-API query immediately after (and a second one, ruling out a caching fluke) showed `bgp`/`interface-vlan` **still `enabled`** on the real device — `nxos_feature`'s destroy did not actually revert device state, only Terraform's own tracking of it. Manually reverted both features to `disabled` via direct NX-API `cli_conf` calls (`no feature bgp ; no feature interface-vlan`), confirmed via a third independent query. **Not yet fixed in the Terraform module** — tracked as a new pending item (§2 of `Platform-Status-and-Pending-Items.md`): the real fix needs investigation into whether `nxos_feature` supports something equivalent to `aci_rest_managed`'s `content_on_destroy`, or whether disabling NX-OS features on destroy needs to be handled as an explicit `provisioner`/lifecycle step instead, since silently leaving features enabled after a reported-successful destroy is a real safety hazard for a shared lab device.

**This closes the core, defining gap this ADR opened with** ("no live verification until a Nexus 9Kv simulator exists") — a genuine `terraform apply` against real Cisco Nexus 9000v hardware, through the actual `CiscoDevNet/nxos` provider, is now proven. Remaining work (DC1-BGW's stuck console, BGP peer config, SVI IP addressing, the destroy-safety bug just found, and OPA/pipeline wiring) are enumerated in `Platform-Status-and-Pending-Items.md` §2, not this ADR's Accepted status.

The full step-by-step procedure (building the OOB network, the jump host, transferring the provider binary, and every gotcha hit) is written up as a reusable runbook: [`CML-EVPN-Lab-Jump-Host.md`](../runbooks/CML-EVPN-Lab-Jump-Host.md) — consult it before repeating any of this rather than rediscovering it from this ADR's narrative.

---

## 7. `nxos_feature` destroy bug — investigated, mitigated with `prevent_destroy` (2026-07-31)

Followed up on §6's finding by querying the real `CiscoDevNet/nxos` v0.13.1 provider schema directly (`terraform providers schema -json`, using the provider binary already cached locally from §6's mirror transfer, no network dependency): `nxos_feature` has **no `content_on_destroy`-equivalent attribute** — every one of its ~35 attributes (`bgp`, `evpn`, `interface_vlan`, etc.) is a plain `enabled`/`disabled` string, unlike `aci_rest_managed`'s generic-REST-object model that made ADR-020 Phase C's fix possible. There is no Terraform-attribute-level fix available for this resource as currently designed by the provider.

**Mitigation applied**: added `lifecycle { prevent_destroy = true }` to `nxos_feature.fabric` in `main.tf`. This does not fix the provider's destroy behavior — it stops the module from allowing a destroy that's now confirmed to silently no-op on shared, foundational fabric state (feature flags every other resource in this module depends on). A genuine fix would require either an upstream provider fix or a destroy-time provisioner issuing the `no feature ...` NX-API calls directly (not attempted here — out of scope without live device access to verify against in this session).

---

## 8. SVI IP addressing — implemented via `nxos_ipv4` (2026-07-31)

Closes the SVI-IP-addressing gap left open in §6's Consequences note. Queried the real provider schema the same way as §7 (`terraform providers schema -json` against the cached local `CiscoDevNet/nxos` v0.13.1 binary): `nxos_ipv4` is a device-wide singleton resource shaped `vrfs.<vrf_name>.interfaces.<interface_id>.addresses.<address>` — `interfaces`' map key must match `nxos_svi_interface`'s own naming (`vlan<id>`), and `vrfs`' map key is the plain VRF name (matching `nxos_vrf.fabric`'s `on_device_name`, not `nxos_svi_interface`'s `sys/inst-<name>` DN format — two different naming conventions for the same VRF concept, confirmed from the schema, not assumed consistent).

Added `nxos_ipv4.fabric` to `main.tf`, grouping `local.bds_with_gateway` (Bridge Domains with a `gateway_ip` set) by VRF. Verified with a real `terraform plan` against a hand-built sample fabric YAML (one tenant/VRF/BD with `gateway_ip = "10.10.10.1/24"`) using the cached provider mirror — resource count went from 7 to 8, and the plan output showed exactly the expected shape (`vrfs.acme_acme-vrf.interfaces.vlan100.addresses["10.10.10.1/24"]`). Not live-`apply`-tested against a real device this pass (no lab access this session) — the exact string format Terraform expects for `addresses`' map key (e.g., whether the prefix length must be included, as assumed here from `bd.gateway_ip`'s existing format) is confirmed structurally via the schema but not proven end-to-end against real NX-API yet.

---

# Consequences

- **Proves the Execution Framework generalizes**, not just the ACI domain — the actual architectural point of building this platform this way. If EVPN needs new pipeline stages, new GitLab CI logic, or changes to the MCP Server's dispatcher, that would be a real finding contradicting ADR-018's design; the design predicts it will not. **Confirmed (2026-07-30)**: adding EVPN's MCP tools required zero changes to `main.py`'s dispatcher, `tools/registry.py`, or any GitLab CI shared stage template — only new files, exactly as ADR-018 predicted.
- **New Nautobot Custom Fields required**: `VRF.evpn_l3_vni`, `VLAN.evpn_l2_vni`, `Device.evpn_bgp_asn`, `Device.evpn_role` — plain scalar fields, not JSON, unlike ACI's Contract/L3Out Custom Fields (those needed JSON because Contracts/L3Outs are nested structures; VNIs and ASNs are not).
- **`VLAN` is now used by the platform's generator tooling for the first time** — ACI's generator only ever read `Tenant`/`VRF`/`Prefix` (Bridge Domains) and `VLAN` for EPGs (ADR-020 Phase A item 2, read-only association). EVPN's generator reads `VLAN` as the primary Bridge-Domain-equivalent object. No conflict: ACI and EVPN Tenants are disjoint (different name prefixes), so the same Nautobot instance safely holds both domains' data.
- **Terraform module deepened (2026-07-30)**: added `nxos_bgp` (global ASN + default VRF's `l2vpn-evpn` address-family + each tenant VRF's `ipv4-ucast` address-family with `advertise_l2vpn_evpn` — the actual EVPN control-plane piece that was missing from the first pass) and `nxos_svi_interface` (SVI existence + VRF binding per Bridge Domain). Both confirmed against the real provider schema (`terraform validate` + `terraform plan`, resource count went from 5 to 7 with no errors). **Still deliberately out of scope, not invented**: actual BGP neighbor/peer configuration (no Nautobot Interface/Cable data model exists yet to source real peer IPs from — inventing them would violate this ADR's own "verify before coding" discipline). **SVI IP-address assignment added (2026-07-31, §8)** via `nxos_ipv4`, resource count now 8 — schema-confirmed and `plan`-verified, not yet `apply`-verified against a real device.
- **OPA policy written and tested (2026-07-30)**: `docker/platform-api/policy/vxlan_evpn/tenant_naming.rego` — tenant naming convention (same as `cisco_aci`), VNI range validation (1-16777214, matching `nxos_nvo`'s confirmed schema), and VNI global-uniqueness checking (VNIs are globally unique on a single NX-OS device, unlike ACI's per-tenant VRF names — a real, distinct failure mode from ADR-020's `web-vrf`/`new-app-vrf` duplicate-VRF incident). Verified with the real `opa eval` CLI (via the `openpolicyagent/opa` image already used by this lab) against 4 scenarios (valid, bad name, duplicate VNI, out-of-range VNI) — a real Rego compile bug (`var vni declared above`, from reusing one variable name across two `some ... in` clauses) was caught and fixed during this verification, not left undiscovered.
- **Live verification achieved (2026-07-30)**: a real `terraform apply`/`plan`/`destroy` cycle succeeded against genuine Nexus 9000v hardware via a jump host inside the CML lab network (see §6) — this closes the core gap this ADR opened with. A real destroy-safety bug was found in `nxos_feature` (destroy doesn't actually revert device state), confirmed via the real provider schema to have no attribute-level fix available, and mitigated with `lifecycle { prevent_destroy = true }` (see §7) rather than left unaddressed.
- **OPA policy** (`data.platform.vxlan_evpn.decision`) needs its own Rego package once real policy rules are identified for this domain — not written in this ADR, since no naming/attribute conventions exist yet to write meaningful rules against (unlike `cisco_aci`'s tenant-naming rule, which came from real debris encountered in this lab).
- **Pending, tracked separately**: standing up a Nexus 9Kv (or equivalent) simulator is real infrastructure work, not a documentation or code task — it is not scoped by this ADR and should be tracked as its own decision (VM sizing, image licensing/availability, network placement) when someone is ready to unblock live verification.
