# Enable Transit Routing — Network Implementation Plan (NIP)

*Cisco ACI · tenant sales · OSPF_L3Out ↔ BGP_L3Out transit*

|  |  |
|---|---|
| Document | Network Implementation Plan (NIP) |
| Change | Implementation of transit routing on the reloaded APIC, from the source of truth |
| Version / date | 1.2 · 30 October 2026 (revision history: Section 4.3) |
| Prepared by | Network Platform Engineering |
| Reference | Enable Transit Routing (DCACIA lab guide). Where this document differs from the guide, this document prevails (Section 4). |
| Implemented through | The Network Platform Engineering Platform: intent in Nautobot, deployment by the GitLab pipeline. No configuration is entered on the APIC by hand. |
| Not in this document | Credentials of any kind; configuration of the external Catalyst and Nexus switches |

## 1  Introduction

### 1.1  Purpose

This document specifies the design and the implementation procedure for enabling **transit routing** through the Cisco ACI fabric. Routes learnt from an external Cisco Catalyst switch over OSPF are re-advertised to an external Cisco Nexus switch over eBGP, and the other way round, under explicit route control and contract policy.

The change is implemented through the platform. Every object below is entered as intent in the source of truth (Nautobot); the GitLab pipeline renders that intent, plans it with Terraform, and applies it to the APIC after an engineer approves the plan.

### 1.2  Scope

**In scope** — everything the transit routing lab needs on the ACI side, in dependency order:

- Fabric inventory: the two border leaves, the spine, and the two external-facing ports.
- Fabric policies: the BGP route-reflector policy and the pod policy group that activates it.
- Access policies for both L3Outs: VLAN pool, L3 domain, AAEP, LLDP interface policy, interface policy group, interface profiles and selectors, switch profiles.
- The CDP interface policy Enable_CDP and its selection on Host_Access_IPG (decision D10).
- Tenant objects: tenant, VRF, bridge domain, filter and contract.
- OSPF_L3Out towards the Catalyst and BGP_L3Out towards the Nexus, with their external EPGs.
- Route control: the export route-control subnet on Cat_ExtNet, and match rules and a route map that decide what is advertised to the Catalyst.

**Out of scope:**

- Configuration of the external Catalyst and Nexus switches. They are preconfigured; their relevant settings are listed in Section 3.3 for reference only.
- The objects of the next two labs (L4-L7 firewall with PBR, VRF route leaking), listed in Section 4.2. They share the tenant and must not be changed by this work, with the single exception of D10.
- The ACI system tenants common, infra and mgmt.

### 1.3  Starting point

The APIC has been reloaded and holds no tenant or access configuration. **Nothing in this document is assumed to exist on the APIC.** Every object is listed, including the ones the reference lab guide treats as preconfigured (VLAN pool, L3 domain, AAEP, interface policy group, interface and switch profiles, route-reflector policy, pod policy group, OSPF_L3Out).

The source of truth may already hold some or all of these objects from an earlier build. Section 5 defines how the implementer handles that: verify first, add only what is missing, change nothing that already exists.

## 2  Design overview

### 2.1  Topology

The fabric sits between two external routing domains. The Catalyst switch peers with **leaf-b** over OSPF area 0. The Nexus switch (labelled “IPN”, AS 65002) peers with **leaf-a** over eBGP, with the border leaf presenting local AS 65003. Both L3Outs belong to the VRF **Presales_VRF** in tenant **sales**.

Figure 1 on the next page shows the topology as configured. It follows the lab guide's drawing, with this plan's values: OSPF_L3Out uses vlan-20 instead of the guide's VLAN 51 (decision D8).

*Figure 1 — Topology: border leaves, external peers, addressing and routing protocols (see the Word or PDF edition).*

### 2.2  How routes cross the fabric

A border leaf redistributes the routes it learns from its external peer into the fabric's MP-BGP (VPNv4). The spine, acting as **BGP route reflector** in the fabric AS **65001**, reflects them to the other leaves. The receiving border leaf then advertises them to its own external peer, but only if the export policy of that L3Out allows it. MP-BGP inside the fabric therefore depends on two fabric policies: the route-reflector policy and a pod policy group that references it, assigned to the pod.

Export policy is different on each side:

- **Towards the Catalyst (OSPF_L3Out)** — the Nexus loopback 172.16.200.200/32 is marked **Export Route Control Subnet** on the external EPG **Cat_ExtNet**. The route map **Uni-Route-Profile-OUT**, applied to Cat_ExtNet in the export direction, also permits it, and explicitly denies 172.16.199.199/32 and the fabric subnet 10.0.3.0/24. Anything else falls to the route map's implicit deny.
- **Towards the Nexus (BGP_L3Out)** — export route-control subnets on the external EPG **Nexus_ExtNet**: the Catalyst loopback 172.16.100.100/32 and the OSPF peering link 172.16.1.0/30.

The OSPF peering link is exported so that the Catalyst can reach the Nexus without sourcing traffic from its loopback. Figure 2 follows every prefix of the lab through the fabric and shows where it is permitted or filtered.

*Figure 2 — Route exchange: what is advertised, and where each filtered prefix stops (see the Word or PDF edition).*

### 2.3  How traffic is allowed

Routing alone does not let traffic cross the fabric: ACI also requires a contract between the two external EPGs. The contract **FileServices_Ct** permits ICMP, SSH and FTP. The Catalyst's external EPG **Cat_ExtNet** consumes it; the Nexus's external EPG **Nexus_ExtNet** provides it. Any other protocol, Telnet for example, is dropped.

An external EPG classifies traffic by the subnets marked **External Subnets for the External EPG** (import-security). These are the source and destination prefixes the contract applies to. Each prefix is classified by one external EPG only: 172.16.200.200/32 and 172.16.199.199/32 by Nexus_ExtNet, 172.16.100.100/32 and 172.16.1.0/30 by Cat_ExtNet. Figure 3 shows the complete tenant policy.

*Figure 3 — Tenant policy model: L3Outs, external EPGs and their subnet flags, contract, route map (see the Word or PDF edition).*

## 3  Addressing, naming and parameters

### 3.1  Fabric nodes

| Name | Role | Node ID | Pod | Serial | Model | External port used |
|---|---|---|---|---|---|---|
| leaf-a | Leaf (border, BGP) | 101 | 1 | FDO23100852 | Nexus 9000v | eth1/4 → Nexus Eth1/2 |
| leaf-b | Leaf (border, OSPF) | 102 | 1 | FDO23041G37 | Nexus 9000v | eth1/1 → Catalyst Gi1/0/4 |
| spine-1 | Spine (BGP route reflector) | 1001 | 1 | FDO2306FG77 | Nexus 9000v | — |

### 3.2  L3Out parameters

| Parameter | OSPF_L3Out (to the Catalyst) | BGP_L3Out (to the Nexus) |
|---|---|---|
| VRF / L3 domain | Presales_VRF / ExtL3Dom | Presales_VRF / ExtL3Dom |
| Border leaf | leaf-b, node 102, pod 1 | leaf-a, node 101, pod 1 |
| Node profile | OSPF_NP | L101 |
| Router ID | 10.1.1.1 (not used as loopback) | 10.3.3.3 (not used as loopback) |
| Interface profile | OSPF_IP | BGP_L3Out_interfaceProfile |
| Interface | SVI on eth1/1, trunk (tagged) | SVI on eth1/4, trunk (tagged) |
| Encapsulation | vlan-20 | vlan-51 |
| IP address / MTU | 172.16.1.1/30 / inherit | 172.16.1.5/30 / inherit |
| Routing protocol | OSPF, area 0.0.0.0 (backbone), regular area, broadcast network | eBGP to 172.16.1.6, remote AS 65002, local AS 65003 |
| External EPG | Cat_ExtNet — consumes FileServices_Ct | Nexus_ExtNet — provides FileServices_Ct |
| Export control | Export route-control subnet 172.16.200.200/32 on Cat_ExtNet, and route map Uni-Route-Profile-OUT | Export route-control subnets on Nexus_ExtNet |
| BGP timers | — | Default (keepalive 60 s, hold 180 s); no BGP Protocol Profile is created |
| Interface policies | Policy group ExtL3_IPG: LLDP Enable_LLDP | Policy group ExtL3_IPG: LLDP Enable_LLDP |

### 3.3  External devices (reference only — not configured by this change)

| Device | Peering address | Routing | Prefixes it originates |
|---|---|---|---|
| Catalyst 3560 (“cat”) | 172.16.1.2/30 on its SVI towards leaf-b | OSPF process 1, area 0 | 172.16.100.100/32 (Loopback0) |
| Nexus (“IPN”) | 172.16.1.6/30 on Vlan51, VRF l3out | BGP AS 65002, neighbour 172.16.1.5 remote-as 65003 | 172.16.200.200/32 and 172.16.199.199/32 |

### 3.4  VLAN plan

| VLAN | Use | Pool / domain | Lab |
|---|---|---|---|
| 20 | OSPF_L3Out SVI on leaf-b eth1/1 | — (see note) | Transit routing (this document) |
| 51 | BGP_L3Out SVI on leaf-a eth1/4 | ExtL3_Pool 51–60, static / ExtL3Dom | Transit routing (this document) |
| 52–60 | Free | ExtL3_Pool | — |
| 11, 13 | Static EPG paths (leaf-a, leaf-b) | Sales_PhyPool 10–30, static / Sales_PhyDom | VRF route leaking (next) |
| 100–199 | Dynamic VMM encapsulation | vCenter_VMM_Pool, dynamic / vCenter_VMM | L4-L7 firewall with PBR (next) |

> **Note on VLAN 20.** OSPF_L3Out keeps the encapsulation used in the previous build, vlan-20 (decision D8). It clashes with no VLAN, port or object of the next two labs. It lies outside ExtL3_Pool (51–60), the pool of the L3 domain the L3Out uses, and inside the range of Sales_PhyPool (10–30). On the lab simulator this has no effect. On physical switches the SVI would not come up until the VLAN is valid for ExtL3Dom. The fix for physical hardware is to move the encapsulation to a free VLAN from 52–60. Do not add VLAN 20 to ExtL3_Pool: the two pools would then overlap. That fix is not part of this change.

### 3.5  Prefixes and their policy

| Prefix | Origin | On Cat_ExtNet | On Nexus_ExtNet | Advertised to the Catalyst | Advertised to the Nexus |
|---|---|---|---|---|---|
| 172.16.100.100/32 | Catalyst loopback (OSPF) | External Subnets for the External EPG | Export Route Control | — (learnt from it) | Yes |
| 172.16.1.0/30 | OSPF peering link | External Subnets for the External EPG | Export Route Control | — | Yes |
| 172.16.200.200/32 | Nexus loopback (BGP) | Export Route Control | External Subnets for the External EPG | Yes — Export Route Control on Cat_ExtNet; route map permit | — (learnt from it) |
| 172.16.199.199/32 | Nexus loopback (BGP) | — | External Subnets for the External EPG | No — route map deny | — |
| 10.0.3.0/24 | DB_BD subnet (fabric) | — | — | No — route map deny (D4) | No — DB_BD is not associated with BGP_L3Out |

## 4  Design decisions

### 4.1  Deviations from the reference lab guide

This design follows the lab guide except where listed below. Each row records a decision taken during the earlier build of this lab; this document prevails over the guide.

| # | The lab guide | This design | Reason |
|---|---|---|---|
| D1 | Tenant Sales | Tenant **sales** (lower case) | The platform's naming policy allows lower-case letters, digits and hyphens only. |
| D2 | Routes exported to the Catalyst with Export Route Control Subnet flags on Cat_ExtNet only | Export Route Control Subnet on 172.16.200.200/32, as in the guide, **plus** the route map **Uni-Route-Profile-OUT** on Cat_ExtNet (export) | Requirement for this build: the routes that must not reach the Catalyst are denied by explicit, auditable policy (D3, D4). |
| D3 | 172.16.199.199/32 filtered only implicitly (not classified, not exported) | Listed explicitly in the deny rule, and classified on Nexus_ExtNet | Correction made after the first build, so that the intent is visible and auditable. |
| D4 | 10.0.3.0/24 advertised to the Catalyst (the guide pings 10.0.3.254 from it) | 10.0.3.0/24 **denied** by the route map | Requirement for this build. Consequence: the Catalyst does not learn 10.0.3.0/24 (Section 8.3). |
| D5 | Pervasive gateway 10.0.3.254/24 on DB_BD | 10.0.3.254/24 added as a **second subnet** on DB_BD | DB_BD's first subnet, 10.0.2.254/24, belongs to the PBR lab and must stay. |
| D6 | 172.16.200.200/32 on Cat_ExtNet with Export Route Control Subnet | **Same as the guide** (revised in 1.1) | Version 1.0 had External Subnets for the External EPG only. Changed by the change owner on 29 October 2026 (Section 4.3). |
| D7 | Interface / switch profiles LEAF101_IFP and LEAF101_SWP | **Leaf101_IntProf** / **Leaf101_SwProf**, and **Leaf102_IntProf** / **Leaf102_SwProf** | The names already used in the source of truth. |
| D8 | OSPF_L3Out encapsulation VLAN 51 | **vlan-20** | Reuse the VLAN of the previous build; checked against the next labs (Section 3.4). |
| D9 | Access policies, route-reflector policy, pod policy group and OSPF_L3Out treated as preconfigured | **Every object specified**; nothing assumed | The APIC is rebuilt from empty. |
| D10 | Not covered (Host_Access_IPG belongs to the VRF route-leaking lab) | CDP interface policy **Enable_CDP** selected on **Host_Access_IPG** | Change-owner request, 30 October 2026. The only object of the next labs this change touches. |

### 4.2  Coexistence with the next two labs

The tenant also holds the objects of the next two labs. They are deployed by the same pipeline (the pipeline deploys everything the source of truth holds), but this change must not create, modify or delete any of them.

| Next lab | Its objects (do not touch) |
|---|---|
| L4-L7 firewall with PBR | VMM domain vCenter_VMM and pool vCenter_VMM_Pool (100–199, dynamic); DB_EPG, Backup_EPG, Backup_BD; contract FW_Ct and filter Web_Fltr; the L4-L7 device, service graph FW_SGT and PBR policies; DB_BD's first subnet 10.0.2.254/24. |
| VRF route leaking | SharedServices_VRF, SharedServices_BD, SharedServices_EPG (subnet 10.0.4.254/24, shared); Web_EPG, Presales_BD; contract WebServices_Ct; physical domain Sales_PhyDom and pool Sales_PhyPool (10–30, static); AAEP HOST_AAEP, policy group Host_Access_IPG (except its CDP policy, D10), selectors Host_Ports; static paths vlan-11 (leaf-a) and vlan-13 (leaf-b); ports eth1/5 on both leaves. |

**Clash check:** VLANs 20 and 51 are not used by either lab. Ports leaf-a eth1/4 and leaf-b eth1/1 are not used by either lab. The only shared objects are Presales_VRF and DB_BD, which this change creates only if missing and otherwise leaves exactly as they are, and Host_Access_IPG, whose CDP policy alone is set (D10).

### 4.3  Design rules and revision history

Two design rules apply throughout:

- **No protocol defaults are configured explicitly.** A BGP Protocol Profile is created under a node profile only when the BGP timers (or the best-path policy) must differ from the default. BGP_L3Out has none, so the default timers apply: keepalive 60 s, hold 180 s.
- **One flag per external-EPG subnet, one classifying EPG per prefix.** No subnet carries Shared Route Control or Shared Security Import: no other VRF imports these routes.

| Version | Date | Change | Deployed by |
|---|---|---|---|
| 1.0 | 27 October 2026 | First edition, as an LLD and MOP, for the rebuild of the lab on the reloaded APIC. | Pipeline 78: 121 objects created |
| 1.1 | 29 October 2026 | Cat_ExtNet subnet scopes corrected by the change owner: 172.16.200.200/32 Export Route Control only (was External Subnets for the External EPG); 172.16.100.100/32 and 172.16.1.0/30 External Subnets for the External EPG only (Shared Route Control and Shared Security Import removed). | Pipeline 80: 3 changed, no new faults |
| 1.2 | 30 October 2026 | LLDP interface policy Enable_LLDP on ExtL3_IPG (as in the lab guide); CDP interface policy Enable_CDP on Host_Access_IPG (D10); the BGP Protocol Profile under L101 removed (default timers). Document renamed Network Implementation Plan (NIP); figures redrawn. | Pipeline 82: 2 created, 2 changed, 1 removed, no new faults |

## 5  Implementation rules

These rules apply to whoever implements Section 6, whether an engineer or the platform's AI agent.

| Rule | Requirement |
|---|---|
| R1 — Through the platform only | Enter every object as intent in the source of truth through the platform. Do not configure the APIC directly. Do not edit the generated YAML or the Terraform code. |
| R2 — Verify before configuring | Before any change, check every step of Section 6 against the source of truth and mark each object **Present** (exists with the values given), **Missing** (does not exist) or **Different** (exists with another value: give both values). Objects marked **Derived** are reported as such. Report the result phase by phase, with a total, and make no change. |
| R3 — Configure only what is missing | After the change owner approves the pre-check, create only the objects marked Missing, in the order of Section 6, one object at a time. Read each object back after writing it: a successful response is not proof that it was stored. |
| R4 — Change nothing that exists | Never modify or delete an existing object, even one marked Different. Report the difference and wait for a decision. |
| R5 — Stay in scope | Do not touch the system tenants common, infra and mgmt, or any object of Section 4.2, except as decision D10 states. |
| R6 — Derived objects | An object marked **Derived** is created by the deployment from a reference in another object. Do not create it separately. |
| R7 — Deployment belongs to the engineer | Do not start, retry or approve a pipeline. Section 7 is carried out by the engineer. |
| R8 — No assumptions | If a value needed for a step is not in this document, ask. Do not assume a default. |

## 6  Implementation procedure

The steps follow the ACI dependency order: an object is configured only after every object it references. The table summarises the order; the steps give the settings.

| Phase | Objects | Depends on |
|---|---|---|
| 6.1 Fabric inventory | leaf-a, leaf-b, spine-1; ports eth1/4 and eth1/1 | — |
| 6.2 Fabric policies | BGP route reflector (AS 65001) → RR node spine-1 → Pod_PG → pod assignment | 6.1 (the RR node must be a registered spine) |
| 6.3 Access policies | VLAN pool → L3 domain → AAEP → LLDP / CDP interface policies → interface policy groups → interface profiles and selectors → switch profiles | 6.1 (switch profiles select nodes) |
| 6.4 Tenant base | Tenant sales → VRF Presales_VRF → bridge domain DB_BD | — |
| 6.5 Contract | Filter FileServices_Fltr → contract FileServices_Ct | 6.4 |
| 6.6 OSPF_L3Out | L3Out → node profile → interface profile and SVI → OSPF interface → Cat_ExtNet → consumed contract | 6.3, 6.4, 6.5 |
| 6.7 BD to L3Out | DB_BD second subnet, advertised through OSPF_L3Out | 6.6 |
| 6.8 BGP_L3Out | L3Out → node profile → interface profile and SVI → BGP peer → Nexus_ExtNet → provided contract | 6.3, 6.4, 6.5 |
| 6.9 Route control | Match rules → route map on OSPF_L3Out → applied to Cat_ExtNet (export) | 6.6 |

### 6.1  Fabric inventory

The platform refuses intent that names a node it does not know, and refuses a route-reflector node that is not a spine. The inventory therefore comes first.

#### Step 1 — Register the border leaf leaf-a

| Setting | Value |
|---|---|
| Name | leaf-a |
| Node ID | 101 |
| Pod | 1 |
| Role | leaf |
| Serial number | FDO23100852 |
| Model | Nexus 9000v |

#### Step 2 — Register the border leaf leaf-b

| Setting | Value |
|---|---|
| Name | leaf-b |
| Node ID | 102 |
| Pod | 1 |
| Role | leaf |
| Serial number | FDO23041G37 |
| Model | Nexus 9000v |

#### Step 3 — Register the spine spine-1

| Setting | Value |
|---|---|
| Name | spine-1 |
| Node ID | 1001 |
| Pod | 1 |
| Role | spine |
| Serial number | FDO2306FG77 |
| Model | Nexus 9000v |

#### Step 4 — Register the two external-facing ports

| Switch | Port | State | Connects to |
|---|---|---|---|
| leaf-a | eth1/4 | Enabled | Nexus “IPN” Eth1/2 (BGP_L3Out) |
| leaf-b | eth1/1 | Enabled | Catalyst Gi1/0/4 (OSPF_L3Out) |

Port eth1/5 on both leaves belongs to the next labs; leave it as it is.

### 6.2  Fabric policies — BGP route reflector

APIC location: System > System Settings > BGP Route Reflector, and Fabric > Fabric Policies > Pods.

#### Step 5 — Set the BGP route-reflector policy

| Setting | Value |
|---|---|
| Policy | default (one per fabric) |
| Autonomous system number | 65001 |

This is the AS of the fabric's internal MP-BGP. The border leaves use it for iBGP with the spine.

#### Step 6 — Add the route-reflector node

| Setting | Value |
|---|---|
| Node | spine-1 (node 1001) |
| Pod | 1 |

#### Step 7 — Create the pod policy group Pod_PG

| Setting | Value |
|---|---|
| Name | Pod_PG |
| BGP Route Reflector Policy | default |

#### Step 8 — Assign Pod_PG to the pod

| Setting | Value |
|---|---|
| Pod profile | default |
| Pod selector | default (all pods) |
| Fabric policy group | Pod_PG |

Without this assignment the route-reflector policy is defined but not active, MP-BGP does not run, and the border leaves cannot exchange external routes: no transit.

### 6.3  Access policies

APIC location: Fabric > Access Policies. The objects form one chain, from the VLAN to the port:

- A **VLAN pool** holds the VLANs that external Layer 3 connections may use.
- An **L3 domain** references the VLAN pool. The L3Outs reference the L3 domain.
- An **AAEP** (Attachable Access Entity Profile) references the L3 domain, and so defines which VLANs may be activated on a port.
- **Interface policies** (here LLDP and CDP) set how the port behaves; they are named and reusable.
- An **interface policy group** gathers the interface policies and binds them to the AAEP.
- An **interface selector**, inside an **interface profile**, picks the port and associates it with the policy group.
- A **switch profile** picks the leaf and associates it with the interface profile.

Figure 4 shows the whole chain, with the fabric policies of Section 6.2.

*Figure 4 — Access and fabric policies: from the VLAN pool to the port, and the route reflector (see the Word or PDF edition).*

#### Step 9 — Create the VLAN pool ExtL3_Pool

| Setting | Value |
|---|---|
| Name | ExtL3_Pool |
| Allocation mode | Static |
| Encapsulation block | VLAN 51 – 60 |
| Block role | External |

#### Step 10 — Create the L3 domain ExtL3Dom

| Setting | Value |
|---|---|
| Name | ExtL3Dom |
| VLAN pool | ExtL3_Pool (static) |

#### Step 11 — Create the AAEP EXTERNAL_SWITCH_AAEP

| Setting | Value |
|---|---|
| Name | EXTERNAL_SWITCH_AAEP |
| Domain | ExtL3Dom (L3 domain) |

#### Step 12 — Create the LLDP interface policy Enable_LLDP

APIC location: Fabric > Access Policies > Policies > Interface > LLDP Interface.

| Setting | Value |
|---|---|
| Name | Enable_LLDP |
| Receive state | Enabled |
| Transmit state | Enabled |

#### Step 13 — Create the CDP interface policy Enable_CDP

APIC location: Fabric > Access Policies > Policies > Interface > CDP Interface.

| Setting | Value |
|---|---|
| Name | Enable_CDP |
| Admin state | Enabled |

ACI names cannot contain spaces, so the policies are Enable_LLDP and Enable_CDP.

#### Step 14 — Create the leaf access-port policy group ExtL3_IPG

| Setting | Value |
|---|---|
| Name | ExtL3_IPG |
| Type | Leaf Access Port |
| AAEP | EXTERNAL_SWITCH_AAEP |
| LLDP policy | Enable_LLDP |
| CDP policy | not set (APIC default) |
| Other interface policies | not set (APIC defaults) |

Enable_LLDP is the LLDP policy the lab guide shows on ExtL3_IPG. Both external ports use this group, so LLDP runs towards the Nexus and the Catalyst.

#### Step 15 — Select Enable_CDP on the policy group Host_Access_IPG (D10)

| Setting | Value |
|---|---|
| Policy group | Host_Access_IPG (VRF route-leaking lab) |
| CDP policy | Enable_CDP |
| Everything else | unchanged |

Host_Access_IPG belongs to the next lab. Only its CDP policy is set here, at the change owner's request.

#### Step 16 — Create the interface profile Leaf101_IntProf with the selector Ext_Nexus

| Setting | Value |
|---|---|
| Interface profile | Leaf101_IntProf |
| Interface selector | Ext_Nexus |
| Selector type | Range |
| Port block | blk1: card 1, port 4 to card 1, port 4 (eth1/4) |
| Policy group | ExtL3_IPG |

Leaf101_IntProf is the container for all access ports on leaf-a; this selector is the BGP_L3Out connection to the Nexus.

#### Step 17 — Create the interface profile Leaf102_IntProf with the selector Ext_Catalyst

| Setting | Value |
|---|---|
| Interface profile | Leaf102_IntProf |
| Interface selector | Ext_Catalyst |
| Selector type | Range |
| Port block | blk1: card 1, port 1 to card 1, port 1 (eth1/1) |
| Policy group | ExtL3_IPG |

This selector is the OSPF_L3Out connection to the Catalyst. Without it, leaf-b eth1/1 has no access policy and the L3Out cannot be deployed to the port.

#### Step 18 — Create the switch profile Leaf101_SwProf

| Setting | Value |
|---|---|
| Switch profile | Leaf101_SwProf |
| Leaf selector | Leaf101_Sel, type Range |
| Node block | blk1: node 101 to node 101 |
| Interface profile | Leaf101_IntProf |

#### Step 19 — Create the switch profile Leaf102_SwProf

| Setting | Value |
|---|---|
| Switch profile | Leaf102_SwProf |
| Leaf selector | Leaf102_Sel, type Range |
| Node block | blk1: node 102 to node 102 |
| Interface profile | Leaf102_IntProf |

### 6.4  Tenant base

APIC location: Tenants > sales.

#### Step 20 — Create the tenant sales

| Setting | Value |
|---|---|
| Name | sales |
| Description | Workbook PBR/L3Out inventory imported; ready for fresh Terraform plan |

#### Step 21 — Create the VRF Presales_VRF

| Setting | Value |
|---|---|
| Tenant | sales |
| Name | Presales_VRF |
| Description | Presales consumer VRF |

#### Step 22 — Create the bridge domain DB_BD

| Setting | Value |
|---|---|
| Tenant / VRF | sales / Presales_VRF |
| Name | DB_BD |
| Unicast routing | Enabled |
| Subnet | 10.0.2.254/24, Private to VRF |

This first subnet belongs to the L4-L7 PBR lab. Create DB_BD only if it is missing; never change it. The transit subnet is added in Step 32.

### 6.5  Contract

APIC location: Tenants > sales > Contracts.

#### Step 23 — Create the filter FileServices_Fltr

| Setting | Value |
|---|---|
| Name | FileServices_Fltr |
| Description | ICMP, SSH and FTP per the lab document |

| Entry | EtherType | IP protocol | Destination ports | Stateful |
|---|---|---|---|---|
| icmp | IP | ICMP | — | No |
| ssh | IP | TCP | 22 – 22 | No |
| ftp | IP | TCP | 20 – 21 | No |

#### Step 24 — Create the contract FileServices_Ct

| Setting | Value |
|---|---|
| Name | FileServices_Ct |
| Scope | VRF |
| Subject | FileServices_Ct-subj |
| Filter | FileServices_Fltr |
| Description | Transit routing between the Catalyst and Nexus external EPGs |

### 6.6  OSPF_L3Out towards the Catalyst

APIC location: Tenants > sales > Networking > L3Outs.

#### Step 25 — OSPF interface policy OSPF_bcast_pol (Derived)

| Setting | Value |
|---|---|
| Name | OSPF_bcast_pol |
| Network type | Broadcast |

**Derived** (rule R6): the deployment creates this policy from the reference in Step 29. It is not entered on its own.

#### Step 26 — Create the L3Out OSPF_L3Out

| Setting | Value |
|---|---|
| Name | OSPF_L3Out |
| VRF | Presales_VRF |
| L3 domain | ExtL3Dom |
| Routing protocol | OSPF |
| External EPG | Cat_ExtNet |
| Description | Workbook OSPF L3Out via leaf-b eth1/1 |

#### Step 27 — Create the node profile OSPF_NP

| Setting | Value |
|---|---|
| Name | OSPF_NP |
| Node | leaf-b, node 102, pod 1 |
| Router ID | 10.1.1.1 |
| Use router ID as loopback | No |

The node profile identifies the border leaf that runs the routing protocol towards the external device.

#### Step 28 — Create the interface profile OSPF_IP with its SVI

| Setting | Value |
|---|---|
| Name | OSPF_IP |
| Interface type | SVI |
| Path | leaf-b (node 102) eth1/1, pod 1 |
| Encapsulation | vlan-20 (see the note in Section 3.4) |
| Mode | Trunk (tagged) |
| IP address | 172.16.1.1/30 |
| MTU | inherit (9216 on ACI switches) |

#### Step 29 — Enable OSPF on the interface profile

| Setting | Value |
|---|---|
| Interface | OSPF_NP / OSPF_IP |
| Name | ospf |
| OSPF interface policy | OSPF_bcast_pol |
| Area ID | 0.0.0.0 (backbone) |
| Area type | Regular |

This is the equivalent of ip router ospf area 0 on the SVI in NX-OS. Without it, OSPF is not enabled on the interface.

#### Step 30 — Add the subnets of the external EPG Cat_ExtNet

| Subnet | Scope | Purpose |
|---|---|---|
| 172.16.200.200/32 | Export Route Control Subnet | Advertise the Nexus loopback to the Catalyst |
| 172.16.100.100/32 | External Subnets for the External EPG | Classify traffic from the Catalyst loopback |
| 172.16.1.0/30 | External Subnets for the External EPG | Classify traffic from the OSPF peering link |

Each subnet carries exactly one flag. 172.16.200.200/32 is not classified here, because Nexus_ExtNet classifies it (Step 37). No subnet carries Shared Route Control or Shared Security Import. The route map of Steps 39–42 is applied on top (D2).

#### Step 31 — Cat_ExtNet consumes the contract FileServices_Ct

| Setting | Value |
|---|---|
| External EPG | Cat_ExtNet (OSPF_L3Out) |
| Consumed contract | FileServices_Ct |
| Provided contracts | None |

### 6.7  Bridge domain to L3Out

#### Step 32 — Add the transit subnet to DB_BD and associate it with OSPF_L3Out

| Setting | Value |
|---|---|
| Bridge domain | DB_BD |
| Subnet | 10.0.3.254/24 (second subnet, D5) |
| Scope | Advertised Externally (public) |
| Associated L3Out | OSPF_L3Out |

The subnet is advertised externally and associated with OSPF_L3Out, but the route map in Step 41 denies 10.0.3.0/24 towards the Catalyst (D4). The first subnet, 10.0.2.254/24, stays as it is.

### 6.8  BGP_L3Out towards the Nexus

The Nexus is preconfigured with AS 65002 and a neighbour 172.16.1.5 in AS 65003 (Section 3.3).

#### Step 33 — Create the L3Out BGP_L3Out

| Setting | Value |
|---|---|
| Name | BGP_L3Out |
| VRF | Presales_VRF |
| L3 domain | ExtL3Dom |
| Routing protocol | BGP |
| External EPG | Nexus_ExtNet |
| Description | Workbook BGP L3Out via leaf-a eth1/4 |

#### Step 34 — Create the node profile L101

| Setting | Value |
|---|---|
| Name | L101 |
| Node | leaf-a, node 101, pod 1 |
| Router ID | 10.3.3.3 |
| Use router ID as loopback | No |
| BGP Protocol Profile | None — default BGP timers |

No loopback is configured on the border leaf: only the router ID is mandatory. A loopback would be needed only if the BGP session were sourced from one.

Do not select **Create BGP Protocol Profile** on the node profile. Without one the default BGP timers apply (keepalive 60 s, hold 180 s). Create it only when the timers must differ from the default (Section 4.3).

#### Step 35 — Create the interface profile BGP_L3Out_interfaceProfile with its SVI

| Setting | Value |
|---|---|
| Name | BGP_L3Out_interfaceProfile |
| Interface type | SVI |
| Path | leaf-a (node 101) eth1/4, pod 1 |
| Encapsulation | vlan-51 |
| Mode | Trunk (tagged) |
| IP address | 172.16.1.5/30 |
| MTU | inherit |

VLAN 51 belongs to ExtL3_Pool, the pool of the L3 domain this L3Out uses.

#### Step 36 — Create the BGP peer connectivity profile

| Setting | Value |
|---|---|
| Attached to | interface 101/1/4 of BGP_L3Out_interfaceProfile |
| Peer address | 172.16.1.6 |
| Remote AS | 65002 |
| Local AS | 65003 |
| eBGP multihop TTL | 1 |
| Weight | 0 |
| Allowed self-AS count | 3 |
| Admin state | Enabled |

The local AS decouples the eBGP AS seen by the Nexus (65003) from the fabric's internal AS (65001). Without it, the border leaf would peer from AS 65001.

#### Step 37 — Add the subnets of the external EPG Nexus_ExtNet

Nexus_ExtNet is not the default EPG for all external networks (0.0.0.0/0 is not classified).

| Subnet | Scope | Purpose |
|---|---|---|
| 172.16.200.200/32 | External Subnets for the External EPG | Classify traffic from the Nexus loopback |
| 172.16.199.199/32 | External Subnets for the External EPG | Classified (D3); never advertised to the Catalyst |
| 172.16.100.100/32 | Export Route Control Subnet | Advertise the Catalyst loopback to the Nexus |
| 172.16.1.0/30 | Export Route Control Subnet | Advertise the OSPF peering link to the Nexus |

#### Step 38 — Nexus_ExtNet provides the contract FileServices_Ct

| Setting | Value |
|---|---|
| External EPG | Nexus_ExtNet (BGP_L3Out) |
| Provided contract | FileServices_Ct |

### 6.9  Route control towards the Catalyst

APIC location: Tenants > sales > Policies > Protocol > Match Rules, and the OSPF_L3Out's Route map for import and export route control.

#### Step 39 — Create the match rule match-permit-prefix-out

| Setting | Value |
|---|---|
| Name | match-permit-prefix-out |
| Description | Nexus loopback advertised to the Catalyst over OSPF |

| Prefix | Aggregate | Greater-than mask | Less-than mask |
|---|---|---|---|
| 172.16.200.200/32 | No | 0 | 0 |

#### Step 40 — Create the match rule deny-prefix-out

| Setting | Value |
|---|---|
| Name | deny-prefix-out |
| Description | BD pervasive gateway subnet, must not reach OSPF |

| Prefix | Aggregate | Greater-than mask | Less-than mask | Prefix description |
|---|---|---|---|---|
| 10.0.3.0/24 | No | 0 | 0 | — |
| 172.16.199.199/32 | No | 0 | 0 | Nexus loopback that must NOT reach the Catalyst |

#### Step 41 — Create the route map Uni-Route-Profile-OUT on OSPF_L3Out

| Setting | Value |
|---|---|
| Name | Uni-Route-Profile-OUT |
| L3Out | OSPF_L3Out |
| Type | Match Routing Policy Only |
| Description | Export control for OSPF_L3Out; implicit deny drops 172.16.199.199/32 |

| Order | Context | Action | Match rule |
|---|---|---|---|
| 0 | permit-explicit | Permit | match-permit-prefix-out |
| 1 | explicit-deny-out | Deny | deny-prefix-out |

#### Step 42 — Apply the route map to Cat_ExtNet

| Setting | Value |
|---|---|
| External EPG | Cat_ExtNet (OSPF_L3Out) |
| Route control profile | Uni-Route-Profile-OUT |
| Direction | Export |

## 7  Deployment (engineer)

Carried out by the engineer, not the AI agent (rule R7). Commands run from the repository root. Figure 5 shows the path from intent to the APIC.

*Figure 5 — Implementation flow: intent in Nautobot, deployment by the GitLab pipeline after approval (see the Word or PDF edition).*

#### Step 43 — Pre-change checks

- The lab containers are running: Nautobot with its worker, GitLab and its runner, Vault, OPA, MinIO and the MCP server.
- The source-of-truth schema is complete: `python platform/workflows/scripts/bootstrap_nautobot.py --verify` prints OK.
- The APIC is reachable and its login, read from Vault, still works after the reload.

#### Step 44 — Re-arm the configuration backup

Every apply is preceded by an APIC configuration backup, and a reload removes the APIC's AES export passphrase. Without it the backup fails closed and nothing is applied.

```
source platform/terraform/aci/scripts/load-vault-creds.sh
python platform/workflows/scripts/apic_backup.py --enable-encryption
```

#### Step 45 — Run the pipeline

In GitLab, project root/nautobot-infra-automation > Build > Pipelines > Run pipeline, on branch **copilot/aci-platform-comparison**. The pipeline renders the intent from Nautobot, validates it, checks policy and runs terraform plan.

#### Step 46 — Review the plan

```
cd reasoning
$env:PYTHONPATH = 'src'
.venv/Scripts/python -m platform_reasoning review-plan
```

**Expected:** creates only (no changes, no deletes); the count matches Terraform's own Plan line. The plan also recreates the next labs' objects, because the pipeline deploys everything in the source of truth.

#### Step 47 — Approve the apply

Approve the manual terraform_apply job. The pipeline takes the APIC backup first, then applies.

#### Step 48 — Post-change checks

```
$env:PLATFORM_ENVIRONMENT = 'simulator'
.venv/Scripts/python -m platform_reasoning diagnose --tenant sales --environment simulator
```

Repeat with --object for OSPF_L3Out, BGP_L3Out, Cat_ExtNet, Nexus_ExtNet, Uni-Route-Profile-OUT, match-permit-prefix-out, deny-prefix-out, FileServices_Ct and DB_BD. See Section 8.2 for the expected result.

## 8  Verification

### 8.1  Configuration on the APIC

| APIC location | Expected |
|---|---|
| System > System Settings > BGP Route Reflector | AS 65001; route-reflector node 1001 (spine-1), pod 1 |
| Fabric > Fabric Policies > Pods > Policy Groups | Pod_PG, BGP Route Reflector Policy resolved to default |
| Fabric > Fabric Policies > Pods > Profiles > Pod Profile default | Pod selector default uses Pod_PG |
| Fabric > Access Policies > Pools > VLAN | ExtL3_Pool, static, 51–60 |
| Fabric > Access Policies > Physical and External Domains > L3 Domains | ExtL3Dom with ExtL3_Pool |
| Fabric > Access Policies > Policies > Global > AAEP | EXTERNAL_SWITCH_AAEP with ExtL3Dom |
| Fabric > Access Policies > Policies > Interface > LLDP Interface / CDP Interface | Enable_LLDP (receive and transmit enabled); Enable_CDP (enabled) |
| Fabric > Access Policies > Interfaces > Leaf Interfaces > Policy Groups > Leaf Access Port | ExtL3_IPG with EXTERNAL_SWITCH_AAEP and LLDP policy Enable_LLDP; Host_Access_IPG with CDP policy Enable_CDP |
| Fabric > Access Policies > Interfaces > Leaf Interfaces > Profiles | Leaf101_IntProf with Ext_Nexus (1/4); Leaf102_IntProf with Ext_Catalyst (1/1) |
| Fabric > Access Policies > Switches > Leaf Switches > Profiles | Leaf101_SwProf (node 101), Leaf102_SwProf (node 102) |
| Tenants > sales > Networking > L3Outs > OSPF_L3Out | Node 102, router ID 10.1.1.1; SVI 172.16.1.1/30 on eth1/1 vlan-20; OSPF area 0.0.0.0; Cat_ExtNet with 172.16.100.100/32 and 172.16.1.0/30 (External Subnets for the External EPG) and 172.16.200.200/32 (Export Route Control Subnet), consuming FileServices_Ct; route map Uni-Route-Profile-OUT (export) |
| Tenants > sales > Networking > L3Outs > BGP_L3Out | Node 101, router ID 10.3.3.3; SVI 172.16.1.5/30 on eth1/4 vlan-51; BGP peer 172.16.1.6, remote AS 65002, local AS 65003; no BGP Protocol Profile under L101; Nexus_ExtNet with four subnets, providing FileServices_Ct |
| Tenants > sales > Policies > Protocol > Match Rules | match-permit-prefix-out, deny-prefix-out |
| Tenants > sales > Networking > Bridge Domains > DB_BD | Subnets 10.0.2.254/24 (private) and 10.0.3.254/24 (public); L3Out OSPF_L3Out |

### 8.2  Platform checks

Each diagnose run shows [ok] on layers 1 to 3 (intent, rendered YAML, Terraform). Layer 4 (the APIC) shows either no fault or only one of the known simulator families:

- F1298 “Node Cannot Deploy” and F0699 “Node Not Leaf For Infra Policies” — the switches are not registered in the simulator.
- F1893 “Only spine nodes can be BGP Route-Reflectors” on the route-reflector node, for the same reason.
- The ten L4-L7 faults (missing-cdev, no vCenter) from the PBR lab's objects, which the same pipeline deploys.

The access policies are not followed by diagnose, which reads tenant intent only. Check them in the APIC GUI (Section 8.1).

### 8.3  Functional tests (physical lab only)

These tests need real switches and external peers. They reproduce the lab guide's verification, adjusted to the decisions in Section 4. The VRF appears on the leaves as sales:Presales_VRF.

| # | On | Command | Expected result |
|---|---|---|---|
| T1 | leaf-b | show ip ospf neighbors vrf sales:Presales_VRF | 172.16.100.100 FULL/DR on Vlan20 |
| T2 | IPN | show bgp sessions vrf l3out | Neighbour 172.16.1.5, AS 65003, Established |
| T3 | leaf-a | show bgp vpnv4 unicast vrf sales:Presales_VRF | 172.16.200.200/32 and 172.16.199.199/32 external (path 65003 65002); 172.16.100.100/32 internal |
| T4 | IPN | show ip route bgp vrf l3out | 172.16.100.100/32 and 172.16.1.0/30 via 172.16.1.5 |
| T5 | cat | show ip route ospf | 172.16.200.200/32 O E2 via 172.16.1.1. Not present: 172.16.199.199/32, 10.0.3.0/24 (D4) |
| T6 | IPN | ping 172.16.100.100 source 172.16.200.200 vrf l3out | Success |
| T7 | cat | ping 172.16.200.200 · ssh 172.16.200.200 | Success · password prompt |
| T8 | cat | telnet 172.16.200.200 | Fails: Telnet is not in FileServices_Ct |
| T9 | cat | ping 172.16.199.199 | Fails: no route, denied by the route map |
| T10 | cat | ping 10.0.3.254 | Fails: 10.0.3.0/24 is not advertised to the Catalyst (D4) |
| T11 | cat | show lldp neighbors | leaf-b on Gi1/0/4, port Eth1/1 (Enable_LLDP) |
| T12 | IPN | show lldp neighbors | leaf-a on Eth1/2, port Eth1/4 (Enable_LLDP) |
| T13 | IPN | show bgp ipv4 unicast neighbors 172.16.1.5 vrf l3out | Hold time 180, keepalive interval 60 seconds (default timers) |

### 8.4  Limits of the lab simulator

The demo APIC is a simulator with no switches. It stores and validates every object above, and relations to switch ports remain unformed. No OSPF or BGP session forms, no route is exchanged and no ping works, so the functional tests in Section 8.3 cannot be run in this lab. That is a property of the lab, not of the design or the platform.

## 9  Rollback

- **APIC:** every apply is preceded by a configuration backup, kept as the pipeline artifact apic-backup.json. Restore it with the runbook knowledge/runbooks/ACI-Restore-From-Pre-Apply-Backup.md.
- **Source of truth:** objects added under rule R3 are removed only on an explicit request from the change owner, never automatically.

## Appendix A — Object checklist in dependency order

One row per object, in the order of Section 6. Use it for the pre-check of rule R2.

| Object | Type | Key values | Step |
|---|---|---|---|
| leaf-a | Fabric node | 101, pod 1, leaf, FDO23100852 | 1 |
| leaf-b | Fabric node | 102, pod 1, leaf, FDO23041G37 | 2 |
| spine-1 | Fabric node | 1001, pod 1, spine, FDO2306FG77 | 3 |
| leaf-a eth1/4, leaf-b eth1/1 | Fabric ports | enabled | 4 |
| BGP route reflector default | Fabric policy | AS 65001 | 5 |
| RR node spine-1 | Fabric policy | node 1001, pod 1 | 6 |
| Pod_PG | Pod policy group | BGP RR policy default | 7 |
| Pod profile default | Pod assignment | Pod_PG | 8 |
| ExtL3_Pool | VLAN pool | static, 51–60, external | 9 |
| ExtL3Dom | L3 domain | ExtL3_Pool | 10 |
| EXTERNAL_SWITCH_AAEP | AAEP | ExtL3Dom | 11 |
| Enable_LLDP | LLDP interface policy | receive and transmit enabled | 12 |
| Enable_CDP | CDP interface policy | admin state enabled | 13 |
| ExtL3_IPG | Leaf access-port policy group | EXTERNAL_SWITCH_AAEP, LLDP Enable_LLDP | 14 |
| Host_Access_IPG → Enable_CDP | Policy group CDP selection | D10 — next lab's group | 15 |
| Leaf101_IntProf / Ext_Nexus | Interface profile / selector | 1/4, ExtL3_IPG | 16 |
| Leaf102_IntProf / Ext_Catalyst | Interface profile / selector | 1/1, ExtL3_IPG | 17 |
| Leaf101_SwProf | Switch profile | node 101, Leaf101_IntProf | 18 |
| Leaf102_SwProf | Switch profile | node 102, Leaf102_IntProf | 19 |
| sales | Tenant | — | 20 |
| Presales_VRF | VRF | — | 21 |
| DB_BD | Bridge domain | 10.0.2.254/24 private | 22 |
| FileServices_Fltr | Filter | icmp, ssh 22, ftp 20–21 | 23 |
| FileServices_Ct | Contract | scope VRF, FileServices_Fltr | 24 |
| OSPF_bcast_pol | OSPF interface policy | broadcast — Derived | 25 |
| OSPF_L3Out | L3Out | Presales_VRF, ExtL3Dom, OSPF | 26 |
| OSPF_NP | Node profile | node 102, 10.1.1.1 | 27 |
| OSPF_IP | Interface profile / SVI | eth1/1, vlan-20, 172.16.1.1/30 | 28 |
| ospf | OSPF interface | OSPF_bcast_pol, area 0.0.0.0 | 29 |
| Cat_ExtNet subnets | External EPG subnets | 172.16.100.100/32, 172.16.1.0/30 import-security; 172.16.200.200/32 export-rtctrl | 30 |
| Cat_ExtNet → FileServices_Ct | Consumed contract | — | 31 |
| DB_BD 10.0.3.254/24 | BD subnet + L3Out | public, OSPF_L3Out | 32 |
| BGP_L3Out | L3Out | Presales_VRF, ExtL3Dom, BGP | 33 |
| L101 | Node profile | node 101, 10.3.3.3, no BGP Protocol Profile | 34 |
| BGP_L3Out_interfaceProfile | Interface profile / SVI | eth1/4, vlan-51, 172.16.1.5/30 | 35 |
| 172.16.1.6 | BGP peer | remote AS 65002, local AS 65003 | 36 |
| Nexus_ExtNet subnets | External EPG subnets | 4 subnets | 37 |
| Nexus_ExtNet → FileServices_Ct | Provided contract | — | 38 |
| match-permit-prefix-out | Match rule | 172.16.200.200/32 | 39 |
| deny-prefix-out | Match rule | 10.0.3.0/24, 172.16.199.199/32 | 40 |
| Uni-Route-Profile-OUT | Route map | 0 permit, 1 deny | 41 |
| Cat_ExtNet ← Uni-Route-Profile-OUT | Route map binding | export | 42 |

## Appendix B — Using this document with the platform's AI agent

This document names no platform tool on purpose. The agent reads the prose and tables, maps each step to the platform's tools itself, and turns them into typed, structured intent in the source of truth. The agent reads the Markdown copy of this document, Enable-Transit-Routing-NIP.md, because VS Code cannot read a Word file.

In VS Code Copilot Chat, Agent mode, persona Network Platform Operator:

**Prompt A — pre-check (rule R2):**

```
Read #file:docs/Enable-Transit-Routing-NIP.md. You are the implementer of Section 6 and Section 5 binds you. Do the pre-check of rule R2 only: compare every step of Section 6 with the source of truth (fabric intent, and tenant intent for tenant sales), and mark each object Present, Missing, Different or Derived. Reply with one table per phase and a total. Make no change.
```

**Prompt B — configure what is missing (rule R3), after reviewing the pre-check:**

```
Approved. Configure only the objects you marked Missing, in the order of Section 6, one at a time, and read each one back. Change nothing else and do not start a pipeline.
```

**Prompt C — status, after the pipeline:**

```
What is the deployment status of tenant sales? Did the last pipeline apply, and were there new APIC faults?
```
