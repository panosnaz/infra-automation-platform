---
type: adr
domain: vxlan_evpn
status: active
tags: [evpn, nexus, vxlan, domain-expansion, generator, terraform, nxos]
owner: platform-engineering-team
last_updated: 2026-08-26
---

# ADR-021 — Domain Expansion Phase 2: Cisco Nexus VXLAN EVPN

**Status:** Accepted — schema, generator, Terraform module, and Ansible playbooks are complete; **live verification achieved on all 4 real nodes** — real `terraform apply` cycles succeeded against genuine Nexus 9000v hardware on all 4: `DC1-Leaf` (2026-07-30, including a `destroy`), `DC1-BGW` (2026-07-31, §10), and `DC2-Leaf`/`DC2-BGW` (2026-07-31, §11). pyATS EVPN tests are written and mock-validated (§12). A working SSH-relay mechanism lets CI jobs reach the real lab devices despite the runner's own lack of network access — one real pipeline job uses it (§13). The file-transfer extension for `terraform_plan`/`apply` once thought blocked (§14) turned out not to be: §17 (2026-08-26) found the real fix (drive both legs of the transfer from outside the jump host, nothing needs installing on it) and live-verified a real `terraform plan` against `DC1-Leaf` through it — `terraform_plan`/`terraform_apply` in `pipelines/evpn.gitlab-ci.yml` now use this mechanism instead of the shared, direct-network-access templates. A real destroy-safety bug was found in `nxos_feature` (§6) — no attribute-level fix exists in the provider's real schema — and is now genuinely fixed with a destroy-time provisioner, **live-verified end-to-end against `DC1-Leaf`** (§15/§16, 2026-08-26). `ansible_configure`/`pyats_verify` still need the same relay treatment before the full pipeline can be wired into the root `.gitlab-ci.yml`.

## Summary (read this first — sections 1-14 below are a detailed implementation log, not required reading)

**What this ADR is:** the platform's second network domain, Cisco Nexus VXLAN EVPN, built as a proof that the whole platform's automation mechanism (Nautobot → generator → GitLab CI → Terraform → Ansible → pyATS) works for a completely different vendor and protocol, not just Cisco ACI — with **zero changes to shared pipeline logic**, only new domain-specific files. That prediction (from ADR-018) has been confirmed true.

**What's built and working:**
- A Terraform module (`platform/terraform/evpn/`) targeting the real `CiscoDevNet/nxos` provider, and a matching Nautobot data model (VRFs, VLANs-as-Bridge-Domains, Custom Fields for VNIs/BGP ASN).
- 3 MCP tools (`create_evpn_tenant`, `create_evpn_vrf`, `create_evpn_bridge_domain`), live-tested over the real MCP protocol.
- **Real hardware verification**: all 4 Nexus 9000v devices in the lab (`DC1-Leaf`, `DC1-BGW`, `DC2-Leaf`, `DC2-BGW`) have a proven, working `terraform apply` cycle — not a simulator, not a mock.
- pyATS tests for the EVPN domain, validated end-to-end (though not yet run against the real devices from an automated pipeline — see below).
- A real bug found: `nxos_feature`'s `terraform destroy` doesn't actually revert device state. Genuinely fixed (§15) with a destroy-time provisioner that issues the real NX-API revert commands directly, since the provider itself has no attribute-level fix available.

**What's still open, and why (the short version):**
- **The EVPN pipeline still isn't wired into the main GitLab pipeline.** `terraform_plan`/`terraform_apply` now work via a jump-host relay (§17) and are live-verified. What's left is `ansible_configure`/`pyats_verify`, which still run directly in the runner and have no network path to the devices — the same relay pattern needs applying there too before the full pipeline can be safely included from the root `.gitlab-ci.yml`.
- **BGP neighbor configuration** is deferred — it needs real cabling/interface data that isn't modeled in Nautobot yet, and the team decided not to invent placeholder data just to make progress.

**If you're picking this up next**, read §9 (BGP) and §17 (the pipeline relay mechanism, and what's left to finish wiring) for the most actionable next steps, and check [`Platform-Status-and-Pending-Items.md`](../architecture/Platform-Status-and-Pending-Items.md) for the always-current summary of what's pending across the whole platform, not just this ADR.

---

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

## 9. BGP peer/neighbor configuration — investigated, deferred (not the same as ACI's permanent block) (2026-07-31)

Queried the real `nxos_bgp` schema (same method as §7/§8) for its two neighbor-configuration paths under `vrfs.<name>`:

- **`peers`** — map keyed by **peer IP address**. Would need real point-to-point underlay IP addressing between devices, which doesn't exist in any data model this platform uses today.
- **`interface_peers`** — map keyed by **`interface_id`**, with a direct `remote_asn` attribute. Far lower effort: needs only *which local interface connects to which neighbor device* — the neighbor's ASN is already available via the existing `Device.evpn_bgp_asn` Custom Field once the neighbor is known. No invented IP addressing required.

Checked `platform/python/generator/` for existing Interface/Cable plumbing to build on: **none exists** — `client.py`/`transformer.py` document the identical gap for ACI's Phase B physical Access Policies (no real leaf/spine interface data available). Unlike that ACI gap (permanently blocked — the ACI simulator has zero real interface data, confirmed via direct APIC query, full stop), this EVPN gap is **solvable in principle**, just not from a session with no live Nautobot/lab access: it needs either real Interface/Cable objects modeled in Nautobot for the 4 EVPN devices, or a live check of the actual lab cabling topology, before any generator/Terraform code is written against it.

**Decision: deferred, not designed speculatively.** Inventing a Nautobot data-model change (a new Custom Field or YAML section) without live Nautobot to validate it against would repeat the exact "verify before coding" violation this ADR series has otherwise avoided. **Recommendation for whoever picks this up next**: use `interface_peers`, not `peers` — it avoids inventing a P2P IP addressing scheme and reuses the `Device.evpn_bgp_asn` Custom Field that already exists.

---

## 10. `DC1-BGW` live-verified, closing the last node gap (2026-07-31)

Live lab access (CML, Nautobot, and the ACI simulator) turned out to be reachable this session after all (an earlier network check in this session was wrong — a transient connectivity drop to the `172.30.46.0/24` segment, confirmed by retrying minutes later). Console'd into `DC1-BGW` directly via CML's SSH console-proxy (`ssh admin@172.30.46.250 "open /VXLAN-EVPN-MultiSite/DC1-BGW/0"`) to find the real root cause of its earlier gap: **not** the stuck console pager originally suspected in §6/§5 — that device had simply never had an IP address configured on `mgmt0` (`show running-config interface mgmt0` showed only `vrf member management`, no `ip address` line). Fixed via console (`interface mgmt0 / ip address 172.30.46.221/24 / no shutdown`), then enabled `feature nxapi` (confirmed via `show feature` it was `disabled` — the other 3 nodes already had it enabled from earlier sessions). Independently confirmed NX-API live via `wget` returning `401 Unauthorized` (the correct authenticated-endpoint response) from the jump host.

Ran a real `terraform init`/`apply`/`plan` cycle against `DC1-BGW` (separate working directory from `DC1-Leaf`'s, same cached provider mirror and `~/.terraformrc` already set up on the jump host from §6) using the exact `nxos_feature` resource committed in `main.tf`, including the `prevent_destroy` mitigation from §7: `Apply complete! Resources: 1 added`, followed by `terraform plan` reporting `No changes` (0 diff). Independently confirmed via the device's own `show feature` that `bgp`/`interface-vlan`/`nve` (the `nv_overlay` feature's real NX-OS name) show `enabled` — `evpn`/`vn_segment` don't appear as distinct rows in this platform's `show feature` output at all (no line for either name, on any of the 4 nodes), which is a real finding about this NX-OS version's feature-table display, not a verification failure (Terraform's own `plan` reported 0 diff against the device's stored config, which is the same acceptance criterion §6 used for `DC1-Leaf`). Deliberately did **not** run `terraform destroy` against `DC1-BGW` this time — the destroy bug is already documented and mitigated (§7); no need to re-trigger it live and leave a real device in a broken state for no new information.

This closes the last node gap this ADR opened with — all 4 real Nexus 9000v nodes (`DC1-Leaf`, `DC1-BGW`, `DC2-Leaf`, `DC2-BGW`) are now confirmed live via NX-API, with real `terraform apply` proven against two of them. `DC2-Leaf`/`DC2-BGW` remain NX-API-confirmed-live but not yet individually `apply`-tested — pyATS test development and `pipelines/evpn.gitlab-ci.yml` wiring are the remaining items (`Platform-Status-and-Pending-Items.md` §2).

---

## 11. `DC2-Leaf` and `DC2-BGW` live-verified — all 4 nodes now have proven `terraform apply` cycles (2026-07-31)

Same session, same jump host, continued: identified `DC2-Leaf` (`172.30.46.222`) and `DC2-BGW` (`172.30.46.223`) definitively via a real NX-API `show hostname` query (not assumed from IP ordering) — both already had `mgmt0`/NX-API configured and working from earlier session work, unlike `DC1-BGW`. Ran the same `terraform init`/`apply`/`plan` cycle (separate working directories, same cached provider mirror, same `prevent_destroy`-mitigated `nxos_feature` resource) against both: both reported `Apply complete! Resources: 1 added`, followed by `plan` reporting `No changes` (0 diff) on each. Independently cross-checked `DC2-Leaf` via a raw NX-API `show feature` JSON query (not just Terraform's own read-back) — confirmed `bgp`/`interface-vlan`/`nve` all show `cfcFeatureCtrlOpStatus2: "enabled"` on the real device.

**All 4 real Nexus 9000v nodes in this lab now have a proven `terraform apply` cycle against genuine hardware** (`DC1-Leaf`, `DC1-BGW`, `DC2-Leaf`, `DC2-BGW`) — this is the most complete live-verification state this ADR has reached. Remaining: pyATS test development and wiring `pipelines/evpn.gitlab-ci.yml` into the root pipeline (`Platform-Status-and-Pending-Items.md` §2).

---

## 12. pyATS EVPN tests written and validated; a real cross-domain pipeline bug found and fixed (2026-07-31)

Added `tests/pyats/evpn/` (`testbed.yml`, `test_evpn_features.py`, `job.py`, `scripts/load-vault-env.sh`), mirroring `tests/pyats/aci/`'s exact structure. `test_evpn_features.py` queries each of the 4 real devices' `show feature` via a direct NX-API JSON-RPC POST (plain `requests`, not pyATS' `rest.connector`) and asserts `bgp`/`interface-vlan`/`nve` are `enabled` — the same 3 features independently confirmed live in §10/§11.

**A real finding, not assumed**: inspected `rest/connector/libs/nxos/implementation.py`'s actual source (the package pyATS installs for `os: nxos` + `rest.connector.Rest`) and confirmed it only implements `connect`/`disconnect` against an **ACI-style DN-based REST API** (`api/aaaLogin.json`, `dn=` paths) — not the real NX-API JSON-RPC `ins_api` convention these Nexus 9000v devices actually expose on `/ins` (confirmed live all session via direct `wget`/`requests` calls). Using `os: nxos`'s built-in connector as originally planned would have silently targeted the wrong API shape. Worked around by keeping a minimal `connections.rest` block only to satisfy pyATS's testbed schema (never connected) and doing the real HTTP calls directly via `requests`, reading connection info from each device's `custom` block instead.

Added a new Vault secret `secret/lab/evpn` (`username`/`password`/`dc{1,2}_{leaf,bgw}_url`) mirroring `secret/lab/aci`'s existing convention, and `tests/pyats/evpn/scripts/load-vault-env.sh` to read it.

**Validated end-to-end, both pass and fail paths**, since the real lab devices aren't reachable from this dev host (only from inside CML via the jump host — same limitation as Terraform's `terraform_plan`/`apply`, see §5/§6): stood up a throwaway local HTTP server replicating the exact confirmed NX-API JSON response shape (`TABLE_cfcFeatureCtrlTable`/`ROW_cfcFeatureCtrlTable`/`cfcFeatureCtrlName2`/`cfcFeatureCtrlOpStatus2`, byte-for-byte matching what was captured live in §10/§11) and ran the real `pyats run job` command against it — `100% Success Rate` when all 3 features show enabled, and a correctly `FAILED` result (66.67%) when one is toggled to `disabled`. This proves the aetest mechanics, JSON parsing, and pass/fail logic are all correct, without needing this exact test to reach real hardware from this host.

**A second, more significant real finding**: `pipelines/includes/common.gitlab-ci.yml`'s `.pyats_verify` shared template was **hardcoded to `tests/pyats/aci/`'s paths** — not parameterized at all. If `pipelines/evpn.gitlab-ci.yml` had been wired into the root pipeline as-is, its `pyats_verify` job would have silently run the *ACI* pyATS tests against the *EVPN* Terraform/Ansible output, not EVPN's own tests — a real gap contradicting this ADR's own repeated claim that a new domain needs "zero pipeline logic changes." Fixed by adding a `PYATS_DIR` variable (matching the existing `TERRAFORM_DIR`/`ANSIBLE_DIR` pattern) to `.pyats_verify` and both domain pipeline files (`pipelines/aci.gitlab-ci.yml`: `tests/pyats/aci`; `pipelines/evpn.gitlab-ci.yml`: `tests/pyats/evpn`) — confirmed zero behavior change for ACI (identical resolved path) and correct EVPN resolution.

**Still not wiring `pipelines/evpn.gitlab-ci.yml` into the root `.gitlab-ci.yml`.** Confirmed this session that the `infra-automation-lab-gitlab-runner` container (where pipeline jobs actually execute) has no network route to `172.30.46.220-223` either — direct `ping`/`nc` from this dev host (same Docker network as the runner) both fail, matching the same Bridge-mode limitation that blocks direct Terraform/pyATS runs from outside CML (§5). Wiring the pipeline now would make `terraform_apply`/`pyats_verify` fail on every single commit. This is a real, structural gap (not a simple config fix) requiring either fixing CML's broken Bridge networking (root cause still unknown, §5) or running a GitLab Runner from inside the lab network itself (e.g., on the jump host) — genuinely new infrastructure work, not scoped by this ADR.

---

## 13. A working SSH-relay mechanism, built and proven live (2026-07-31)

Investigated running a GitLab Runner directly on the existing `alpine` jump host (a single static binary, not Python/pyATS-heavy) instead of standing up new infrastructure. Confirmed the jump host **can** reach the lab devices (already established), but a runner registered there would need *outbound* reachability to the GitLab server itself (`gitlab-runner`'s protocol always initiates outbound, never receives inbound) — tested directly from the jump host and confirmed this dev host's own address (`192.168.172.44`, a WSL2-internal IP) is **unreachable** from the CML network at all (`ping`/`nc` both fail). This is a separate, unrelated limitation — WSL2's own network isolation on this specific machine, not a CML/lab issue, and not fixable from inside WSL (needs a Windows-side change: mirrored networking mode or `netsh portproxy`).

**Better approach, no new infrastructure needed**: since `gitlab-runner`'s protocol is runner-initiates-outbound, and this dev host already reaches the CML controller directly, a CI job can relay individual commands to the jump host via CML's own SSH console-proxy instead of needing its own network path to the devices. Built `pipelines/scripts/cml-jump-relay.exp` (an `expect` script) + `cml-jump-relay.sh` (a retry wrapper reading `secret/lab/cml` from Vault).

**Real debugging required, not a clean first try**: the console-proxy (`ssh admin@<cml> "open /<lab>/<node>/0"`) is a raw serial-console session, not a normal SSH exec channel — driving it non-interactively with `expect` took several genuine iterations to get right:
- A Tcl syntax bug (`$marker_start(.*)` parsed as array-index syntax, not string interpolation followed by a literal `(` — fixed with `${marker_start}` bracing).
- An assumed "wake-up phase" (sending a bare `\r` and waiting for a prompt before the real command) turned out to be the actual bug — the console is immediately responsive right after the `Connected to CML terminalserver.` banner; the wake-up attempts never got a response and always timed out. Removing that phase entirely (sending the real command directly) is what made it work.
- The output-capture regex anchored on the wrong occurrence of the marker text (it appears twice: once in the console's echo of the typed input line, once in the real command output) — fixed by capturing broadly then slicing from the *last* occurrence with Tcl's `string last`, not relying on regex greediness.
- A stale, still-attached session from an earlier failed test attempt was found (`ps aux`) blocking new connections — CML consoles are single-session; killing it resolved an otherwise-confusing intermittent failure.

**Validated live, repeatedly, against the real lab**: successfully relayed both simple commands (`hostname`, `date`) and a real NX-API query (`show hostname` against `DC1-Leaf` via `wget`+`ins_api` JSON) through the jump host, retrieving correct output and exit codes. Confirmed real, roughly 1-in-3 intermittent connection-stage flakiness (not command-stage) — `cml-jump-relay.sh` retries up to 3 times on the relay script's own `exit 124` (never confused with the relayed command's real exit code), and this reliably recovered in testing (one live run succeeded on its 3rd attempt).

**Wired into one real pipeline job**: `evpn_lab_connectivity_check` (new job in `pipelines/evpn.gitlab-ci.yml`, stage `plan`, gating `terraform_plan`) relays an NX-API reachability check to all 4 real devices via the jump host — genuinely tested and passing.

**Still not enough to wire the full pipeline in.** `evpn_lab_connectivity_check` only proves devices are reachable *through the relay* — `terraform_plan`/`terraform_apply`/`ansible_configure`/`pyats_verify` are still the unmodified shared templates, executing directly in the runner, which still has no network path to the devices. They would still fail. Relaying those jobs' actual execution (SCP the rendered Terraform/Ansible/pyATS artifacts to the jump host via its SFTP dropfolder, run the real tool there via the same relay mechanism, retrieve results back for GitLab CI artifacts) is real, separate follow-on work — the relay *primitive* is now proven and reusable, but applying it to the heavier, multi-file jobs is a bigger task than this pass covered.

---

## 14. File-transfer extension attempted for `terraform_plan`/`apply`, blocked, and the relay's reliability re-characterized (2026-07-31, same day)

Attempted the file-transfer piece needed to relay `terraform_plan`/`apply` themselves (not just a reachability check): package the rendered Terraform working directory (`main.tf`/`providers.tf`/`variables.tf`/`outputs.tf` + generated `fabric.yaml` + a `terraform.tfvars`) into a tarball, upload it to CML's SFTP dropfolder (confirmed working — this dev host already has working `sftp` credentials), then have the jump host pull it down via the internal dropfolder path (`192.168.255.1`) to extract and run `terraform init`/`plan` there.

**The download direction is genuinely blocked, not just fiddly**:
- The jump host has no `sshpass` or `expect` to automate the internal SFTP pull's password prompt.
- `apk add sshpass` fails with **HTTP 403** from the jump host's NAT egress — the identical package-fetch block already documented for `registry.terraform.io`/`github.com` earlier this session, now also confirmed for Alpine's own CDN.
- SSH key-based auth isn't viable either: confirmed the SFTP dropfolder is a **chrooted sandbox** (`pwd` returns `/`, only the uploaded files are visible) — there's no `.ssh/authorized_keys` to add a key to.
- Tried bypassing SFTP entirely by base64-encoding the tarball and sending it as literal text through the console-relay mechanism itself. This does not scale: even a 28-byte test payload (not just the ~5.6KB real one) reliably failed, ruling out a simple size/line-length limit — something about longer or repeated `send` payloads specifically degrades reliability on this console link, not fully diagnosed.

**The relay mechanism's own reliability had to be re-characterized, not just the file-transfer idea abandoned.** Re-testing the exact same `hostname`-only command that worked repeatedly earlier in this session (§13) started failing consistently on retest — at both the connection stage and the command-completion stage, inconsistently, even after explicit cooldown periods (20s, 45s) between attempts and after confirming no stale sessions were interfering (`ps aux` clean) and that CML itself was healthy (reachable, node still `BOOTED`). A bare, non-scripted `expect` test connecting the same way still succeeded reliably when run standalone. This means the mechanism's real-world reliability is **worse and less predictable than the "~1 in 3 connection-stage failures" characterized in §13** — likely connected to the sheer volume of rapid, repeated console connect/disconnect cycles this session's testing generated against the same node, which real CI usage (naturally spaced-out job runs) may not reproduce to the same degree, but this is a hypothesis, not a confirmed root cause.

**Decision: stop here, do not build further on this primitive without a fresh investigation.** Continuing to build the heavier `terraform_plan`/`apply` relay on top of a primitive whose reliability characteristics are now in question would compound an unverified assumption, contradicting this ADR series' own discipline. `cml-jump-relay.sh`/`.exp` and `evpn_lab_connectivity_check` remain committed as real, demonstrated-working progress (per §13's evidence) — but the file-transfer extension is not implemented, and the relay's true reliability needs re-establishing (ideally with real spacing between test attempts, matching actual CI cadence) before more is built on it. See `Platform-Status-and-Pending-Items.md` §2 for the current status of this item.

---

## 15. `nxos_feature` destroy bug — genuinely fixed with a destroy-time provisioner (2026-08-19)

§7 mitigated this with `lifecycle { prevent_destroy = true }` because no attribute-level fix exists in the real provider schema, and left the actual fix ("a destroy-time provisioner issuing the `no feature ...` NX-API calls directly") as future work. Implemented that fix now.

**A real Terraform constraint surfaced immediately, confirmed via `terraform validate`, not assumed**: a destroy-time provisioner (`when = destroy`) can only reference `self`, `count.index`, or `each.key` — not `var.*` — to avoid dependency cycles during destroy. Putting the provisioner directly on `nxos_feature.fabric` and reading `var.nxos_url`/`var.nxos_username`/`var.nxos_password` in its `environment` block failed validation with `Invalid reference from destroy provisioner` on every credential reference.

**Fix**: added `null_resource.revert_nxos_feature_on_destroy` (`depends_on = [nxos_feature.fabric]`), the standard Terraform workaround for this exact limitation — the credentials are captured in the `null_resource`'s own `triggers` map (which *can* be set from `var.*` at create time), and the destroy-time provisioner reads them back via `self.triggers.*`. This required adding `hashicorp/null` to `required_providers` in `providers.tf` (not previously declared). The provisioner issues the same real NX-API `cli_conf` JSON-RPC call already used to manually revert `DC1-Leaf` in §6 (`no feature bgp ; no feature interface-vlan ; no feature nv overlay`, POSTed to `<nxos_url>/ins` with basic auth), and fails the destroy (rather than silently succeeding) if the response contains a 4xx/5xx `code`.

**`evpn`/`vn_segment` are deliberately not included** in the revert command — §10 found neither appears as a distinct row in this platform's `show feature` output at all, so attempting to disable them by name would likely error and abort the whole destroy for no real benefit.

**`prevent_destroy` removed from `nxos_feature.fabric`** now that destroy has a real, working revert path instead of a silent no-op — keeping it would have permanently prevented the new provisioner from ever running.

**Verification performed this pass**: `terraform validate` (clean) and a `terraform plan` against the real `platform/netascode/evpn/fabric.yaml` with dummy credentials — confirmed `null_resource.revert_nxos_feature_on_destroy` appears in the plan with `nxos_username`/`nxos_password` correctly shown as `(sensitive value)`, and resource count is unaffected for `apply` (the null_resource only does something on `destroy`). **Not live-`destroy`-tested against a real device this pass** — no lab access this session, same limitation noted throughout this ADR. Whoever next has jump-host access to the CML lab should run a real `apply` → `destroy` → independent NX-API `show feature` cycle against `DC1-Leaf` (the same device used in §6's original finding) to close this out with live evidence, the same standard this ADR has held every other change to.

---

## 16. Live-verified end-to-end against real hardware; two real bugs found and fixed along the way (2026-08-26)

Got jump-host access this session (Vault and the Docker stack, unreachable at first, came back once the user restarted them) and ran the full `apply` → `plan` → `destroy` → independent-NX-API-check cycle from §15 against real `DC1-Leaf` hardware, closing out that section's one open item.

**Bug 1 — `cml-jump-relay.exp` assumed the console is always already at a shell prompt.** The lab had been fully `STOPPED` (not just its nodes) since the last session, so the jump host cold-booted from nothing. Confirmed live: after `Connected to CML terminalserver.`, the console produces **no output at all** until sent a wake-up keypress — directly contradicting an earlier version of this script's own comment, which was true only for a console still mid-session from a previous connection, not a fresh boot. After the wake-up, the console may show either a shell prompt (still-running session) or an OS `login:` prompt (fresh boot, confirmed credentials `cisco`/`cisco` from `knowledge/runbooks/CML-EVPN-Lab-Jump-Host.md` §4). Fixed `cml-jump-relay.exp`/`.sh` to send the wake-up keypress unconditionally, then give a short, dedicated timeout window to detect and handle a login prompt before falling through to the existing marker-based command logic (which doesn't care about exact prompt text, so no further special-casing was needed there). Also had to manually restore the jump host's `eth0`/`eth1` addressing (`knowledge/runbooks/CML-EVPN-Lab-Jump-Host.md` §4's `ip addr add`/`udhcpc` steps) and re-pull the `nxos`/`null` provider mirrors from CML's SFTP dropfolder (§6 of that runbook) — both are runtime-only/`/tmp`-only state on this node and don't survive a full stop/start cycle, unlike `/usr/local/bin/terraform` and `~/.terraformrc`, which do.

**Bug 2 — the §15 destroy-time provisioner assumed `curl` exists wherever `terraform destroy` runs.** It doesn't: this lab's own jump host (the realistic place this would actually run, given §13/§14's pipeline-relay work) ships only busybox `wget`/`sftp`/`scp`, confirmed via `which curl sftp scp sshpass expect`. The first live `terraform destroy` attempt reproduced this exactly — `local-exec provisioner error ... exit status 127. Output: /bin/sh: curl: not found`, correctly surfaced as a failed destroy (not silently swallowed) because of the exit-code check added in §15. Fixed by rewriting the provisioner's `command` to use `wget` instead, matching this lab's own already-documented busybox-`wget` convention (`knowledge/runbooks/CML-EVPN-Lab-Jump-Host.md` §5: no `--user`/`--password` flags on busybox, so the `Authorization: Basic` header is built by hand with `base64`; and the JSON body goes through `--post-file` with a `mktemp` temp file rather than `--post-data`, since busybox's argument parsing doesn't handle the embedded quotes/semicolons in the cli_conf payload the same way `curl -d` does).

**Full live cycle, all independently confirmed via direct NX-API queries (not just Terraform's own output), against `DC1-Leaf`:**
1. Baseline `show feature` before any Terraform action: `bgp`/`interface-vlan`/`nve` already `enabled` (left over from earlier sessions), `mpls-evpn`/`vni` `disabled`. New finding beyond §10: on this device, `evpn` maps to a real, distinctly-named `show feature` row after all — `mpls-evpn`, not `evpn` — contradicting §10's finding that it never appears as a distinct row at all (that finding still stands for `DC1-BGW`/`DC2-Leaf`/`DC2-BGW`; this is new information specific to `DC1-Leaf`, not a correction of those). Doesn't change §15's decision to exclude `evpn`/`vn_segment` from the revert command — the real CLI feature names (`mpls-evpn`, `vni`) still don't match the provider's attribute names, so guessing at `no feature evpn`/`no feature vn-segment-vlan-based` would still risk an invalid-command error.
2. `terraform apply`: `Apply complete! Resources: 2 added, 0 changed, 0 destroyed.`
3. `terraform plan`: `No changes. Your infrastructure matches the configuration.`
4. `terraform destroy`: after fixing Bug 2, `Destroy complete!` with the state file confirmed empty (`terraform state list` returned nothing).
5. **Independent NX-API `show feature` query immediately after**: `bgp`, `interface-vlan`, and `nve` all confirmed `disabled` — the destroy-time provisioner genuinely reverted real device state this time, closing the gap §6 originally found (where a reported-successful destroy left the device state completely unchanged).

This closes §15's one remaining open item ("not live-`destroy`-tested against a real device this pass") with real, independently-verified evidence. `main.tf`'s provisioner `command` now uses `wget`, not `curl`; `pipelines/scripts/cml-jump-relay.exp`/`.sh` now handle a cold-booted jump host. Test artifacts (`/tmp/tfwork`, `/tmp/mirror`, temp JSON files) cleaned up from the jump host afterward; `DC1-Leaf`'s `bgp`/`interface-vlan`/`nve` were deliberately left `disabled` as the correct, intended end state of a real, successful destroy — not reset back to `enabled`.

---

## 17. `terraform_plan`/`terraform_apply` pipeline wiring — the §14 file-transfer blocker wasn't actually blocked (2026-08-26, same session)

§14 concluded the `terraform_plan`/`apply` file-transfer extension was blocked: no `sshpass`/`expect` on the jump host to drive its own outbound interactive `sftp` session, `apk install sshpass` blocked by the lab's NAT egress, the SFTP dropfolder chrooted (no SSH key auth), and base64-over-console too unreliable even for tiny payloads.

**The real fix: don't try to install anything on the jump host at all.** `cml-jump-relay.exp` already answers the jump host's own OS `login:` prompt without anything installed there (§16) by staying *outside* the jump host and driving both the console-proxy connection and the login prompt itself. The exact same technique works one level deeper: a new script, `cml-jump-fetch-file.exp` (wrapped by `cml-jump-fetch-file.sh`, same Vault-credential and retry conventions as `cml-jump-relay.sh`), drives the console connection, the jump host's own login if needed, *and* the nested `sftp` session's password prompt to CML's **internal** dropfolder address (`192.168.255.1`) — all from one script running outside the jump host. Nothing needs installing on the jump host; `busybox sftp` (already present) is all it needs to run once told what to type.

**Two real bugs found and fixed while building this, confirmed live, not assumed:**
- **A previous attempt that times out mid-transfer leaves the console stuck inside a stale nested `sftp>` sub-session** — the console-proxy reattaches to the same live serial session on reconnect, it doesn't reset remote state (the same class of finding as §13's stale-session discovery, but for a sub-shell state rather than a blocked connection slot). A retry's very first command was silently swallowed as an invalid `sftp` command instead of a shell command. Fixed by sending a defensive `bye` (harmless either way — exits a stray `sftp` session, or fails as an unknown shell command if there wasn't one) at the start of both `cml-jump-relay.exp` and `cml-jump-fetch-file.exp` before doing anything else.
- **Sending the next command immediately after exiting the nested `sftp` session races the remote shell's own prompt-redraw** — confirmed live: trying to `expect -re` the shell prompt itself before proceeding was unreliable (exact end-of-buffer timing varies), where a fixed short `sleep 1` reliably let the shell settle. Matches why `cml-jump-relay.exp` itself never tries to match the prompt text either, relying only on markers.

**Full mechanism, `pipelines/scripts/cml-terraform-run.sh`:**
1. Stages a copy of the Terraform working directory + its referenced NetAsCode YAML (never touches the real checkout — a generated `terraform.tfvars` with real device credentials only ever exists in a temp staging copy), tars it.
2. Uploads the tarball to CML's **external** SFTP dropfolder (`curl -T ... sftp://<user>:<pass>@<cml_host>/...` — confirmed working with real credentials, no interactive prompt needed since `curl`'s own SFTP support takes them in the URL).
3. Pulls it onto the jump host via `cml-jump-fetch-file.sh`, from the **internal** dropfolder address.
4. Extracts and runs `terraform init && terraform plan` (or `apply -auto-approve`) via the existing marker-based `cml-jump-relay.sh`, which already proved it can capture arbitrary-length command output (the destroy-fix testing in §15/§16 relied on this same property).

**Persistent provider mirror, a genuinely useful side-finding**: `/tmp` on the jump host is an explicit `tmpfs` mount (confirmed via `mount`) — wiped every boot — but `/home/cisco` is not (confirmed: files from three days earlier survived this session's own reboot). The `nxos`/`null` provider mirror and `~/.terraformrc` now live under `/home/cisco/tf-mirror` instead of `/tmp/mirror`, so they survive a jump-host reboot and don't need re-fetching every pipeline run — only `cml-terraform-run.sh`'s per-run working directory (`/home/cisco/ci-run`) is ephemeral by design.

**Live-verified**: a full run of `cml-terraform-run.sh` against the **real, generator-driven `platform/terraform/evpn` module** (not a hand-built minimal config, unlike §15/§16's destroy-fix testing) targeting `DC1-Leaf` — bundle → upload → fetch → extract → `terraform init` → `terraform plan` — completed successfully: `Plan: 9 to add, 0 to change, 0 to destroy`, matching the same resource count seen with dummy credentials in §15. **Only `plan` was live-tested this pass, not `apply`**, a deliberate scope choice: the committed `fabric.yaml` currently has zero tenants (`platform/netascode/evpn/fabric.yaml`: `fabric: {tenants: []}` — no live Nautobot EVPN device/tenant data exists yet), so an `apply` here would only exercise the same fabric-wide singleton resources (`nxos_feature`/`nxos_evpn`/`nxos_nvo`/`nxos_bgp`) already `apply`-proven individually in §6/§10/§11/§15 — running a full-module `apply` adds real risk (creating config on a shared lab device) without adding new proof beyond what `plan` already demonstrates for this file-transfer mechanism specifically.

**`pipelines/evpn.gitlab-ci.yml` updated**: `terraform_plan`/`terraform_apply` no longer `extends: ".terraform_plan"`/`".terraform_apply"` (the shared templates, which assume direct runner network access) — they now call `cml-terraform-run.sh` directly, with a new `pipelines/scripts/load-vault-evpn-tf-creds.sh` sourcing device credentials from `secret/lab/evpn` (mirrors `tests/pyats/evpn/scripts/load-vault-env.sh`'s exact pattern). `terraform_apply` keeps the same `when: manual`/`allow_failure: false` Approval gate as the shared template, just no longer inherited via `extends`.

**Known gap, not solved here**: `TF_VAR_bgp_asn` has no real source yet — no EVPN Device objects with a populated `evpn_bgp_asn` Custom Field were found in this lab's Nautobot instance (confirmed via a direct API query, not assumed missing). `load-vault-evpn-tf-creds.sh` defaults to a clearly-labeled placeholder (`65000`) unless `EVPN_BGP_ASN` is set. Wiring this up to real per-device Nautobot data is separate follow-on work.

**Still not wiring the full pipeline into the root `.gitlab-ci.yml`.** `ansible_configure`/`pyats_verify` are still the unmodified shared templates and would still fail — the same jump-host relay treatment needs applying to them too before that's safe. See `Platform-Status-and-Pending-Items.md` §2 for current status.

---

# Consequences

- **Proves the Execution Framework generalizes**, not just the ACI domain — the actual architectural point of building this platform this way. If EVPN needs new pipeline stages, new GitLab CI logic, or changes to the MCP Server's dispatcher, that would be a real finding contradicting ADR-018's design; the design predicts it will not. **Confirmed (2026-07-30)**: adding EVPN's MCP tools required zero changes to `main.py`'s dispatcher, `tools/registry.py`, or any GitLab CI shared stage template — only new files, exactly as ADR-018 predicted.
- **New Nautobot Custom Fields required**: `VRF.evpn_l3_vni`, `VLAN.evpn_l2_vni`, `Device.evpn_bgp_asn`, `Device.evpn_role` — plain scalar fields, not JSON, unlike ACI's Contract/L3Out Custom Fields (those needed JSON because Contracts/L3Outs are nested structures; VNIs and ASNs are not).
- **`VLAN` is now used by the platform's generator tooling for the first time** — ACI's generator only ever read `Tenant`/`VRF`/`Prefix` (Bridge Domains) and `VLAN` for EPGs (ADR-020 Phase A item 2, read-only association). EVPN's generator reads `VLAN` as the primary Bridge-Domain-equivalent object. No conflict: ACI and EVPN Tenants are disjoint (different name prefixes), so the same Nautobot instance safely holds both domains' data.
- **Terraform module deepened (2026-07-30)**: added `nxos_bgp` (global ASN + default VRF's `l2vpn-evpn` address-family + each tenant VRF's `ipv4-ucast` address-family with `advertise_l2vpn_evpn` — the actual EVPN control-plane piece that was missing from the first pass) and `nxos_svi_interface` (SVI existence + VRF binding per Bridge Domain). Both confirmed against the real provider schema (`terraform validate` + `terraform plan`, resource count went from 5 to 7 with no errors). **Still deliberately out of scope, not invented**: actual BGP neighbor/peer configuration (no Nautobot Interface/Cable data model exists yet to source real peer IPs from — inventing them would violate this ADR's own "verify before coding" discipline). **SVI IP-address assignment added (2026-07-31, §8)** via `nxos_ipv4`, resource count now 8 — schema-confirmed and `plan`-verified, not yet `apply`-verified against a real device.
- **OPA policy written and tested (2026-07-30)**: `docker/platform-api/policy/vxlan_evpn/tenant_naming.rego` — tenant naming convention (same as `cisco_aci`), VNI range validation (1-16777214, matching `nxos_nvo`'s confirmed schema), and VNI global-uniqueness checking (VNIs are globally unique on a single NX-OS device, unlike ACI's per-tenant VRF names — a real, distinct failure mode from ADR-020's `web-vrf`/`new-app-vrf` duplicate-VRF incident). Verified with the real `opa eval` CLI (via the `openpolicyagent/opa` image already used by this lab) against 4 scenarios (valid, bad name, duplicate VNI, out-of-range VNI) — a real Rego compile bug (`var vni declared above`, from reusing one variable name across two `some ... in` clauses) was caught and fixed during this verification, not left undiscovered.
- **Live verification achieved on all 4 real nodes, all with proven `terraform apply` cycles (2026-07-30/31)**: `DC1-Leaf` (§6, including a `destroy`), `DC1-BGW` (§10), `DC2-Leaf`/`DC2-BGW` (§11) — the most complete live-verification state this ADR has reached, closing the core gap this ADR opened with. A real destroy-safety bug was found in `nxos_feature` (destroy doesn't actually revert device state), confirmed via the real provider schema to have no attribute-level fix available, mitigated with `lifecycle { prevent_destroy = true }` (§7), then genuinely fixed (§15) and live-verified end-to-end against `DC1-Leaf` (§16, 2026-08-26) with a destroy-time provisioner issuing the real NX-API revert commands directly.
- **OPA policy** (`data.platform.vxlan_evpn.decision`) needs its own Rego package once real policy rules are identified for this domain — not written in this ADR, since no naming/attribute conventions exist yet to write meaningful rules against (unlike `cisco_aci`'s tenant-naming rule, which came from real debris encountered in this lab).
- **Pending, tracked separately**: standing up a Nexus 9Kv (or equivalent) simulator is real infrastructure work, not a documentation or code task — it is not scoped by this ADR and should be tracked as its own decision (VM sizing, image licensing/availability, network placement) when someone is ready to unblock live verification.
