---
title: "Nautobot as Source of Truth for Cisco ACI with NaC Deployment"
description: "Architecture plan and implementation guide for replacing Excel-driven Ansible with a Nautobot-first, NaC YAML, Terraform pipeline targeting a Cisco ACI simulator."
author: "panos"
ms.date: "2026-06-18"
ms.topic: "how-to"
keywords: ["nautobot", "cisco-aci", "network-as-code", "terraform", "ansible", "ssot", "nac"]
estimated_reading_time: 18
type: architecture
domain: cisco_aci
status: active
tags: [nautobot, netascode, ssot]
owner: platform-engineering-team
last_updated: 2026-07-28
---

## Overview

This document describes the architecture and implementation plan for migrating from an Excel-driven Ansible workflow to a Nautobot-first automation pipeline that targets the ACI simulator at `https://172.30.46.103`.

The existing workflow transforms Excel data into YAML using a Python script, then drives Ansible to configure ACI. The target architecture replaces Excel as the source of truth with Nautobot and replaces direct Ansible execution with Cisco Network as Code (NaC) structured YAML consumed by Terraform.

### Target Pipeline

```
ACI Simulator ──[SSOT sync]──► Nautobot (Source of Truth)
                                       │
                              GraphQL / REST queries
                                       │
                               Generator Script / Job
                                       │
                              NaC YAML files (netascode/aci schema)
                                       │
                         terraform apply (netascode/aci provider)
                                       │
                              ACI APIC REST API
                                       │
                               ACI Fabric state
```

### Migration Path for Existing Ansible Workflow

```
Excel ──► [one-time import] ──► Nautobot
                                    │
                             Generator ──► NaC YAML ──► Terraform
                                    │
                           (parallel) ──► aci_vars.yml ──► Ansible (transition)
```

During transition, the generator can emit your existing `aci_vars.yml` format so
Ansible roles continue working unchanged while the Terraform NaC path matures.

---

## Part 1: Nautobot on Docker Desktop

### Prerequisites

- Docker Desktop with Compose v2 support
- At least 4 GB RAM allocated to Docker
- Git

### Setup Steps

Clone the official Nautobot Docker Compose stack:

```bash
git clone https://github.com/nautobot/nautobot-docker-compose.git
cd nautobot-docker-compose
cp environments/local.env.example environments/local.env
```

Add the ACI SSOT plugin to `local_requirements.txt` in the repo root.

> **Note:** The ACI integration ships inside the `nautobot-ssot` package. The exact
> extras marker (`[aci]`) and minimum version depend on the installed Nautobot version.
> Confirm the current package name on PyPI (`https://pypi.org/project/nautobot-ssot`)
> before pinning a version.

```
# local_requirements.txt
nautobot-ssot[aci]
```

After editing `local_requirements.txt` you must **rebuild the image**. A volume mount
alone does not install Python packages; the requirements file is copied into the image
at build time by the Dockerfile.

```bash
docker compose build
docker compose up -d
docker compose exec nautobot nautobot-server createsuperuser
```

Nautobot UI will be available at `http://localhost:8080`.

### Plugin Registration

Add the plugin to `nautobot_config.py` (mounted or baked into the image):

```python
PLUGINS = [
    "nautobot_ssot",
]

PLUGINS_CONFIG = {
    "nautobot_ssot": {
        # nautobot-ssot itself has no APIC credential keys here.
        # ACI sync credentials are entered as Job parameters in the Nautobot UI
        # when running the "ACI Data Source" sync job.
        # Refer to the nautobot-ssot documentation for any config keys
        # that control which integrations are enabled.
    }
}
```

> ACI APIC credentials (`apic_url`, `apic_username`, `apic_password`, `verify_ssl`)
> are entered in the Nautobot UI as Job variables when running the sync, not as
> static PLUGINS_CONFIG keys. Do not hardcode credentials in `nautobot_config.py`.

---

## Part 2: ACI SSOT Plugin

### What It Syncs

The plugin crawls the APIC and populates Nautobot models. The first sync bootstraps
Nautobot with everything currently in the ACI simulator.

| ACI Object | Nautobot Model |
|---|---|
| Tenant | `Tenant` (Tenancy app) |
| VRF | `VRF` (IPAM app) |
| Bridge Domain (L2 object) | Plugin-managed custom model or Tag |
| BD Subnet / Gateway | `Prefix` + `IPAddress` (IPAM) |
| Node / Leaf / Spine | `Device` (DCIM) |
| Interface | `Interface` (DCIM) |
| VLAN Pool | `VLANGroup` |
| Application Profile | Plugin-managed or Tag on `Tenant` |
| EPG | Plugin-managed custom model |
| Contract | Plugin-managed custom model |

Bridge Domains are Layer 2 constructs and do not map directly to a Nautobot `Prefix`.
Only BD subnets (gateways with masks) map to IPAM Prefixes and IP Addresses.

> **Reality check (2026-07-29, [ADR-020](../adr/ADR-020-ACI-Domain-Coverage-Expansion.md)) — this table is the original plan, not what was actually built.** Confirmed against the live lab and the real `nautobot_ssot` code, two rows above turned out wrong once implementation started:
> - **Node/Leaf/Spine → Device, Interface → Interface**: the plugin's Device/Interface sync was found to have 3 real bugs (`Tenant`/`Tag` content-type filtering, an unguarded `Namespace.objects.create()`, `VRF.MultipleObjectsReturned`) that were never fixed — the team pivoted to **manually creating the 2 real leaf Devices by hand** instead, bypassing the plugin's sync entirely. There is no working, repeatable Device/Interface sync in this lab today.
> - **Application Profile / EPG / Contract → "Plugin-managed custom model"**: none of these ended up modeled by the plugin at all. They're plain Nautobot **`VLAN`** objects (EPG) and **JSON-typed Custom Fields** (`aci_epg_contracts` on `VLAN`, `aci_contracts` on `Tenant`) — a deliberate choice to avoid a new Nautobot plugin/custom model, made *because* the plugin doesn't cover these object types at all, not as an implementation detail of using it.
>
> Tenant, VRF, and BD-subnet-as-Prefix are the only rows in this table that match real, working plugin behavior (confirmed via ADR-001's brownfield note: 3 of the lab's 4 tenants arrived through this exact sync). Everything else in the platform's actual ACI object coverage (VRF/BD attribute depth, Application Profiles, EPGs, Contracts/Filters, L3Out, Access/Fabric Policies) is generic Nautobot objects plus Custom Fields, authored forward through the generator — never synced from the plugin. See [ADR-020](../adr/ADR-020-ACI-Domain-Coverage-Expansion.md) for the authoritative, current state.

### Running the First Sync

1. Open Nautobot UI at `http://localhost:8080`.
2. Navigate to **Plugins > SSoT > Jobs**.
3. Select the **ACI** data source job.
4. Enter APIC URL (`https://172.30.46.103`), username, password, and set verify_ssl to
   false for the simulator.
5. Run **Sync to Nautobot**.
6. Validate that Tenants, VRFs, Prefixes, and Devices appear in the UI.

---

## Part 3: Data Model Enrichment

After the initial sync, enrich Nautobot data to carry ACI-specific attributes that
your Ansible roles currently read from `aci_vars.yml`. These are VRF-level and
Bridge Domain-level attributes. Tenants in ACI carry no equivalent per-tenant policy
fields, so no custom fields are needed on the Tenant model itself.

### Custom Fields on VRF

These attributes come from the `vrfs` sheet in `aci_vars.yml`.

| Field Name | Type | Source in `aci_vars.yml` |
|---|---|---|
| `aci_ip_dataplane_learning` | Text (`enabled` / `disabled`) | `vrfs[].ip_dataplane_learning` |
| `aci_policy_control_direction` | Text (`ingress` / `egress`) | `vrfs[].policy_control_direction` |
| `aci_policy_control_preference` | Text (`enforced` / `unenforced`) | `vrfs[].policy_control_preference` |
| `aci_preferred_group` | Text (`enabled` / `disabled`) | `vrfs[].preferred_group` |

### Custom Fields for Bridge Domains

Bridge Domains carry substantial L2/L3 configuration. Represent them as a custom model
or tag-based grouping with these attributes sourced from the `bds` sheet.

| Field Name | Type | Source in `aci_vars.yml` |
|---|---|---|
| `aci_bd_mac` | Text | `bds[].BD_MAC` |
| `aci_arp_flooding` | Boolean | `bds[].arp_flooding` |
| `aci_unicast_routing` | Boolean | `bds[].routing` |
| `aci_host_based_routing` | Boolean | `bds[].host_routing` |
| `aci_l2_unknown_unicast` | Text (`flood` / `proxy`) | `bds[].l2_unknown_unicast` |
| `aci_l3_unknown_multicast` | Text (`flood` / `opt-flood`) | `bds[].l3_unknown_multicast` |
| `aci_multi_destination` | Text (`bd-flood` / `drop` / `encap-flood`) | `bds[].multi_dest` |
| `aci_ep_move_detect` | Text (`default` / `garp`) | `bds[].endpoint_move_detect` |
| `aci_pim` | Boolean | `bds[].PIM` |
| `aci_igmp_policy` | Text | `bds[].igmp_policy` |

### One-Time Import from Existing `aci_vars.yml`

Run a Python import script to load your existing data from
`/home/panos/devnet/projects/aci/aci_excel_vars_and_roles/vars/aci_vars.yml`
into Nautobot via the REST API:

```python
import yaml
import requests

NAUTOBOT_URL = "http://localhost:8080"
TOKEN = "your-nautobot-token"

headers = {"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"}

with open("vars/aci_vars.yml") as f:
    data = yaml.safe_load(f)

for tenant in data["tenants"]:
    requests.post(
        f"{NAUTOBOT_URL}/api/tenancy/tenants/",
        json={"name": tenant["tenant_name"], "description": tenant.get("description", "")},
        headers=headers,
    )
```

Extend this pattern for VRFs, Bridge Domains, subnets, and contracts.

---

## Part 4: The Generator

The generator reads Nautobot via GraphQL and writes NaC-compatible YAML files.
Two implementation options are available.

### Option A: Nautobot Job (UI-triggered, runs inside Nautobot)

```python
# jobs/generate_nac_yaml.py
import os
import yaml
from nautobot.extras.jobs import Job
from nautobot.ipam.models import VRF, Prefix
from nautobot.tenancy.models import Tenant
from collections import defaultdict


class GenerateACINaCYAML(Job):
    class Meta:
        name = "Generate ACI NaC YAML"
        description = "Export Nautobot data as netascode/aci-compatible YAML"

    def run(self):
        output = {"apic": {"tenants": []}}

        prefixes_by_tenant = defaultdict(list)
        for pfx in Prefix.objects.select_related("tenant", "vrf"):
            if pfx.tenant:
                prefixes_by_tenant[pfx.tenant.pk].append(pfx)

        for tenant in Tenant.objects.all():
            t = {
                "name": tenant.name,
                "description": tenant.description or "",
                "vrfs": [],
                "bridge_domains": [],
            }

            for vrf in VRF.objects.filter(tenant=tenant):
                cf = vrf.cf  # Nautobot 2.x custom fields accessor
                t["vrfs"].append({
                    "name": vrf.name,
                    "ip_dataplane_learning": cf.get("aci_ip_dataplane_learning", "enabled") == "enabled",
                    "contract_enforcement_preference": cf.get(
                        "aci_policy_control_preference", "enforced"
                    ),
                    "preferred_group": cf.get("aci_preferred_group", "disabled") == "enabled",
                })

            bds_seen = {}
            for pfx in prefixes_by_tenant[tenant.pk]:
                bd_name = pfx.description or str(pfx.prefix)
                if bd_name not in bds_seen:
                    bds_seen[bd_name] = {
                        "name": bd_name,
                        "vrf": pfx.vrf.name if pfx.vrf else "",
                        "subnets": [],
                    }
                bds_seen[bd_name]["subnets"].append({"ip": str(pfx.prefix)})

            t["bridge_domains"] = list(bds_seen.values())
            output["apic"]["tenants"].append(t)

        # Write to a filesystem path accessible from the container
        output_path = "/opt/nautobot/nac/tenants.yaml"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            yaml.dump(output, f, default_flow_style=False)
        self.logger.info(f"Wrote {output_path}")
```

> Nautobot Jobs do not have a `create_file()` method on `self`. Write to a filesystem
> path accessible from the container, or return YAML as log output and capture it
> from the CI runner via the Job Results API.

### Option B: External Python Script (CI/CD-friendly, recommended for GitOps)

Query Nautobot GraphQL from a pipeline runner and write structured YAML to disk.

> In Nautobot's GraphQL schema, `prefixes` are not a nested relation under `tenants`.
> Query them as a top-level list with a `tenant` filter.

```python
import os
import yaml
import requests
from collections import defaultdict

NAUTOBOT_URL = os.environ.get("NAUTOBOT_URL", "http://localhost:8080")
TOKEN = os.environ.get("NAUTOBOT_TOKEN")
headers = {"Authorization": f"Token {TOKEN}"}

TENANT_QUERY = """
{
  tenants {
    name
    description
  }
}
"""

VRF_QUERY = """
{
  vrfs {
    name
    tenant { name }
    custom_fields
  }
}
"""

PREFIX_QUERY = """
{
  prefixes {
    prefix
    description
    tenant { name }
    vrf { name }
  }
}
"""


def gql(query):
    resp = requests.post(
        f"{NAUTOBOT_URL}/api/graphql/",
        json={"query": query},
        headers=headers,
    )
    return resp.json()["data"]


tenants_data = gql(TENANT_QUERY)["tenants"]
vrfs_data = gql(VRF_QUERY)["vrfs"]
prefixes_data = gql(PREFIX_QUERY)["prefixes"]

vrfs_by_tenant = defaultdict(list)
for vrf in vrfs_data:
    if vrf["tenant"]:
        vrfs_by_tenant[vrf["tenant"]["name"]].append(vrf)

prefixes_by_tenant = defaultdict(list)
for pfx in prefixes_data:
    if pfx["tenant"]:
        prefixes_by_tenant[pfx["tenant"]["name"]].append(pfx)

output = {"apic": {"tenants": []}}

for tenant in tenants_data:
    t = {
        "name": tenant["name"],
        "description": tenant.get("description") or "",
        "vrfs": [],
        "bridge_domains": [],
    }

    for vrf in vrfs_by_tenant[tenant["name"]]:
        cf = vrf.get("custom_fields") or {}
        t["vrfs"].append({
            "name": vrf["name"],
            "ip_dataplane_learning": cf.get("aci_ip_dataplane_learning", "enabled") == "enabled",
            "contract_enforcement_preference": cf.get("aci_policy_control_preference", "enforced"),
            "preferred_group": cf.get("aci_preferred_group", "disabled") == "enabled",
        })

    bds_seen = {}
    for pfx in prefixes_by_tenant[tenant["name"]]:
        bd_name = pfx.get("description") or pfx["prefix"]
        vrf_name = pfx["vrf"]["name"] if pfx.get("vrf") else ""
        if bd_name not in bds_seen:
            bds_seen[bd_name] = {"name": bd_name, "vrf": vrf_name, "subnets": []}
        bds_seen[bd_name]["subnets"].append({"ip": pfx["prefix"]})

    t["bridge_domains"] = list(bds_seen.values())
    output["apic"]["tenants"].append(t)

os.makedirs("nac", exist_ok=True)
with open("nac/tenants.yaml", "w") as f:
    yaml.dump(output, f, default_flow_style=False)

print("Generated nac/tenants.yaml")
```

---

## Part 5: NaC YAML Schema

The `netascode/nac-aci` Terraform module expects YAML files with this structure.
The generator output must conform to this schema.

### Tenants, VRFs, Bridge Domains, EPGs

The BD example below reflects the full set of L2/L3 attributes present in your
`aci_vars.yml`, mapped to the NaC schema field names.

```yaml
# nac/tenants.yaml
apic:
  tenants:
    - name: Prod
      description: Production Tenant
      vrfs:
        - name: IT_VRF
          ip_dataplane_learning: true
          contract_enforcement_preference: enforced
          preferred_group: true
      bridge_domains:
        - name: BD_100
          vrf: IT_VRF
          mac: "00:22:BD:F8:19:FF"
          arp_flooding: true
          unicast_routing: false
          host_based_routing: false
          unknown_unicast: flood
          unknown_multicast: flood
          multi_destination: bd-flood
          ep_move_detection: default
          pim: false
          subnets:
            - ip: 192.168.100.254/24
              scope: [private]
              primary: true
              ip_dataplane_learning: true
            - ip: 172.16.100.254/25
              scope: [public, shared]
              primary: false
              ip_dataplane_learning: true
        - name: BD_300
          vrf: Reg_VRF
          mac: "00:00:00:11:33:33"
          arp_flooding: false
          unicast_routing: true
          host_based_routing: true
          unknown_unicast: proxy
          unknown_multicast: opt-flood
          multi_destination: drop
          ep_move_detection: garp
          pim: true
          subnets:
            - ip: 10.30.30.254/24
              scope: [public]
              primary: true
              ip_dataplane_learning: false
      application_profiles:
        - name: IT
          description: IT Application Profile
          endpoint_groups:
            - name: EPG_100
              bridge_domain: BD_100
              preferred_group_member: false
              physical_domains: [Dom01]
              vmm_domains:
                - name: vCenter1
                  deploy_immediacy: immediate
                  resolution_immediacy: immediate
              static_ports:
                - node_id: 101
                  port: "1/1"
                  type: fex
                  fex_id: 101
                  mode: native
                  vlan: 100
                  deployment_immediacy: immediate
                - node_ids: [101, 102]
                  channel: SrvA-VPC
                  type: vpc
                  mode: access
                  vlan: 3100
                  deployment_immediacy: immediate
```

### Fabric Policies

```yaml
# nac/fabric_policies.yaml
apic:
  fabric_policies:
    vlan_pools:
      - name: VLAN-Pool-1
        allocation_mode: dynamic
        ranges:
          - from: 100
            to: 199
            allocation_mode: dynamic
      - name: VLAN-Pool-2
        allocation_mode: static
        ranges:
          - from: 200
            to: 250
            allocation_mode: static
```

### Access Policies

```yaml
# nac/access_policies.yaml
apic:
  access_policies:
    physical_domains:
      - name: Domain-1
        vlan_pool: VLAN-Pool-1
        vlan_pool_allocation_mode: dynamic
    vmm_domains:
      - name: Domain-2
        vm_provider: vmware
        vlan_pool: VLAN-Pool-1
        vlan_pool_allocation_mode: dynamic
    aaeps:
      - name: AEP-Fabric
        physical_domains: [Domain-1]
        infra_vlan: true
    leaf_interface_policy_groups:
      - name: Access_1G_IPG
        type: access
        aaep: AEP-Fabric
    leaf_interface_profiles:
      - name: Leaf1-IntPrf
        selectors:
          - name: Leaf1-Eth_3
            policy_group: Access_1G_IPG
            port_blocks:
              - name: portblk1
                from_port: 3
                to_port: 3
    leaf_profiles:
      - name: Leaf1-Prf
        selectors:
          - name: Leaf1
            node_blocks:
              - name: Leaf1
                from: 101
                to: 101
```

### Mapping from Existing `aci_vars.yml`

| `aci_vars.yml` sheet / key | NaC YAML path |
|---|---|
| `tenants[].tenant_name` | `apic.tenants[].name` |
| `vrfs[].vrf` | `apic.tenants[].vrfs[].name` |
| `vrfs[].ip_dataplane_learning` | `apic.tenants[].vrfs[].ip_dataplane_learning` |
| `vrfs[].policy_control_preference` | `apic.tenants[].vrfs[].contract_enforcement_preference` |
| `vrfs[].preferred_group` | `apic.tenants[].vrfs[].preferred_group` |
| `bds[].BD_name` | `apic.tenants[].bridge_domains[].name` |
| `bds[].BD_MAC` | `apic.tenants[].bridge_domains[].mac` |
| `bds[].arp_flooding` | `apic.tenants[].bridge_domains[].arp_flooding` |
| `bds[].routing` | `apic.tenants[].bridge_domains[].unicast_routing` |
| `bds[].host_routing` | `apic.tenants[].bridge_domains[].host_based_routing` |
| `bds[].l2_unknown_unicast` | `apic.tenants[].bridge_domains[].unknown_unicast` |
| `bds[].l3_unknown_multicast` | `apic.tenants[].bridge_domains[].unknown_multicast` |
| `bds[].multi_dest` | `apic.tenants[].bridge_domains[].multi_destination` |
| `bds[].endpoint_move_detect` | `apic.tenants[].bridge_domains[].ep_move_detection` |
| `bds[].PIM` | `apic.tenants[].bridge_domains[].pim` |
| `bd_subnets[].Gateway` / `Subnet_Mask` | `apic.tenants[].bridge_domains[].subnets[].ip` (CIDR) |
| `bd_subnets[].Scope` | `apic.tenants[].bridge_domains[].subnets[].scope` |
| `bd_subnets[].Make_This_IP_Primary` | `apic.tenants[].bridge_domains[].subnets[].primary` |
| `bd_subnets[].IP_Data_Plane_Learning` | `apic.tenants[].bridge_domains[].subnets[].ip_dataplane_learning` |
| `aps[].ap` | `apic.tenants[].application_profiles[].name` |
| `epgs[].EPG_Name` | `apic.tenants[].application_profiles[].endpoint_groups[].name` |
| `epgs[].BD` | `apic.tenants[].application_profiles[].endpoint_groups[].bridge_domain` |
| `epgs[].preferred_group` | `apic.tenants[].application_profiles[].endpoint_groups[].preferred_group_member` |
| `epgs_and_phy_domains[].domain` | `apic.tenants[].application_profiles[].endpoint_groups[].physical_domains[]` |
| `epgs_and_vmm_domains[]` | `apic.tenants[].application_profiles[].endpoint_groups[].vmm_domains[]` |
| `epgs_static_paths[]` | `apic.tenants[].application_profiles[].endpoint_groups[].static_ports[]` |
| `vlan_pools[].vpool_name` | `apic.fabric_policies.vlan_pools[].name` |
| `vlan_pools[].pool_alloc_mode` | `apic.fabric_policies.vlan_pools[].allocation_mode` |
| `domains[]` | `apic.access_policies.physical_domains[]` or `vmm_domains[]` |
| `aeps[].aep_name` | `apic.access_policies.aaeps[].name` |
| `Interface_Selectors[]` | `apic.access_policies.leaf_interface_profiles[].selectors[]` |
| `Leaf_Profiles[]` | `apic.access_policies.leaf_profiles[]` |

> The generator must reconstruct the NaC hierarchy (Tenant → AP → EPG) from the flat
> lists in `aci_vars.yml`. For EPGs, join on `tenant` + `AP` + `EPG_Name`. For static
> ports, join `epgs_static_paths` on `tenant` + `AP` + `EPG`. For BD subnets, join
> `bd_subnets` on `Tenant` + `BD`.

---

## Part 6: Terraform NaC Configuration

### Directory Structure

```
terraform-aci-nac/
├── main.tf
├── variables.tf
├── terraform.tfvars        # credentials only, not committed
├── .gitignore
└── nac/                    # generator output
    ├── tenants.yaml
    ├── fabric_policies.yaml
    └── access_policies.yaml
```

### `main.tf`

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aci = {
      source  = "netascode/aci"
      version = ">= 0.2.0"
    }
  }
}

provider "aci" {
  username = var.aci_username
  password = var.aci_password
  url      = var.aci_url
  insecure = true  # simulator uses a self-signed certificate
}

module "aci" {
  source  = "netascode/nac-aci/aci"
  version = ">= 0.8.0"

  yaml_directories = ["./nac/"]
}
```

### `variables.tf`

```hcl
variable "aci_username" {
  type      = string
  sensitive = true
}

variable "aci_password" {
  type      = string
  sensitive = true
}

variable "aci_url" {
  type    = string
  default = "https://172.30.46.103"
}
```

### `.gitignore`

```
terraform.tfvars
.terraform/
*.tfstate
*.tfstate.backup
.terraform.lock.hcl
```

### First Terraform Run

```bash
cd terraform-aci-nac

# Initialise providers and module
terraform init

# Dry-run against the simulator
terraform plan

# Apply configuration
terraform apply
```

---

## Part 7: Implementation Phases

### Phase 1: Nautobot Bootstrap (estimated 1-2 days)

- [ ] Clone `nautobot-docker-compose` and add `nautobot-ssot[aci]` to `local_requirements.txt`
- [ ] Run `docker compose build` to install the plugin, then `docker compose up -d`
- [ ] Create superuser and confirm Nautobot UI at `http://localhost:8080`
- [ ] Confirm `nautobot_ssot` is listed under **Plugins** in the UI
- [ ] Run the ACI SSOT sync job against `172.30.46.103` with simulator credentials
- [ ] Validate: Tenants, VRFs, Prefixes, and Devices populated in the UI

### Phase 2: Data Model Enrichment (estimated 2-3 days)

- [ ] Create Custom Fields on `VRF` for the four VRF-level ACI attributes
- [ ] Design and create a BD custom model or tag scheme for the ten BD attributes
- [ ] Write and run the one-time import script from `vars/aci_vars.yml` to populate all data
- [ ] Validate all tenants, VRFs, BDs, EPGs, APs, and access policies visible in Nautobot

### Phase 3: Generator Development (estimated 3-4 days)

- [ ] Implement the generator script (Option B as external script for CI is recommended)
- [ ] Cover all NaC YAML sections: tenants, VRFs, BDs with full L2/L3 attrs, EPGs, static paths, fabric and access policies
- [ ] Implement the join logic to reconstruct the NaC hierarchy from flat `aci_vars.yml` lists
- [ ] Run `yamllint` and `terraform validate` on the generator output
- [ ] Test `terraform plan` against the simulator using generated YAML; confirm no unexpected changes
- [ ] Test `terraform plan` against simulator using generated YAML

### Phase 4: Terraform NaC Validation (estimated 1-2 days)

- [ ] Set up `terraform-aci-nac/` directory with `main.tf`, `variables.tf`
- [ ] Run `terraform plan` and confirm no unintended drift
- [ ] Run `terraform apply` and validate ACI objects in the simulator APIC GUI
- [ ] Compare resulting configuration with current Ansible-deployed state

### Phase 5: GitOps Pipeline (ongoing)

- [ ] Configure Nautobot webhook on object-change events
- [ ] CI/CD pipeline: webhook triggers generator, commits YAML, runs `terraform apply`
- [ ] Add `terraform plan` as a pull-request check before applying
- [ ] Document runbook for day-2 operations

---

## Part 8: Coexistence with Existing Ansible Roles

The existing Ansible roles (`cisco.aci` collection) under
`/home/panos/devnet/projects/aci/aci_excel_vars_and_roles/roles/` do not need to
change during the transition. The generator can emit your existing `aci_vars.yml`
format as a compatibility output:

```python
# In the generator, alongside NaC YAML output, also write aci_vars.yml format
ansible_output = {
    "tenants": [{"tenant_name": t["name"], "description": t["description"]} for t in tenants],
    "vrfs": [...],
}
with open("vars/aci_vars.yml", "w") as f:
    yaml.dump(ansible_output, f, default_flow_style=False)
```

This lets you run both in parallel:

```bash
# Ansible path (existing, unchanged)
ansible-playbook main.yml

# Terraform NaC path (new)
python generate.py && terraform apply
```

Once Terraform NaC covers all scenarios, retire the Ansible path.

---

## Part 9: Key References

| Resource | URL |
|---|---|
| nautobot-docker-compose | `https://github.com/nautobot/nautobot-docker-compose` |
| nautobot-ssot (includes ACI integration) | `https://github.com/nautobot/nautobot-app-ssot` |
| nautobot-ssot PyPI page (verify ACI extras) | `https://pypi.org/project/nautobot-ssot` |
| netascode/nac-aci Terraform module | `https://github.com/netascode/terraform-aci-nac-aci` |
| netascode/aci Terraform provider | `https://registry.terraform.io/providers/netascode/aci` |
| NaC ACI YAML schema reference | `https://netascode.github.io/terraform-aci-nac-aci` |
| cisco.aci Ansible collection | `https://galaxy.ansible.com/cisco/aci` |

---

## Part 10: Decision Points

These items require a decision before implementation can proceed.

| Decision | Options | Recommendation |
|---|---|---|
| SSOT sync direction | ACI → Nautobot only, or bidirectional | Start ACI → Nautobot for bootstrap; enable Nautobot → ACI after data is fully authoritative |
| BD model in Nautobot | Custom Fields on Prefix, dedicated plugin model, or separate BD custom model | Use the ACI SSOT plugin model if it tracks BDs natively; fall back to Custom Fields if not |
| Application Profile / EPG model | Tags, Custom Fields, or plugin-managed model | Use the plugin model where available; extend with Custom Fields for attributes the plugin misses |
| Generator trigger | Manual Nautobot Job, Git webhook, or scheduled CI | Webhook for real-time GitOps; scheduled job as fallback |
| Terraform state backend | Local, GitLab HTTP, or Terraform Cloud | GitLab HTTP backend matches the existing SC pipeline approach |
| Ansible retirement timeline | Immediate cutover or phased | Phased: run both in parallel until Terraform NaC covers all roles cleanly |

---

## Appendix: `aci_vars.yml` Sheet Inventory

All sheets present in the existing Excel/YAML file and their coverage status in this plan.

| Sheet | Key Field | Coverage in NaC Plan |
|---|---|---|
| `tenants` | `tenant_name` | Covered — `apic.tenants[].name` |
| `vrfs` | `vrf` | Covered — `apic.tenants[].vrfs[]` |
| `aps` | `ap` | Covered — `apic.tenants[].application_profiles[]` |
| `bds` | `BD_name` | Covered — `apic.tenants[].bridge_domains[]` (full L2/L3 attrs) |
| `bd_subnets` | `BD` + `Gateway` | Covered — `apic.tenants[].bridge_domains[].subnets[]` |
| `epgs` | `EPG_Name` | Covered — `apic.tenants[].application_profiles[].endpoint_groups[]` |
| `epgs_and_phy_domains` | `domain` | Covered — `endpoint_groups[].physical_domains[]` |
| `epgs_and_vmm_domains` | `vmm_domain` | Covered — `endpoint_groups[].vmm_domains[]` |
| `epgs_static_paths` | `EPG` | Covered — `endpoint_groups[].static_ports[]` |
| `vlan_pools` | `vpool_name` | Covered — `apic.fabric_policies.vlan_pools[]` |
| `domains` | `domain_name` | Covered — `apic.access_policies.physical_domains[]` or `vmm_domains[]` |
| `aeps` | `aep_name` | Covered — `apic.access_policies.aaeps[]` |
| `domain_aep_bindings` | `domain_name` + `aep_name` | Covered — via `aaeps[].physical_domains[]` |
| `domain_vlan_bindings` | `domain_name` + `vpool_name` | Covered — via domain definition |
| `Interface_Selectors` | `port_selector_name` | Covered — `apic.access_policies.leaf_interface_profiles[].selectors[]` |
| `Leaf_Profiles` | `leaf_prf_name` | Covered — `apic.access_policies.leaf_profiles[]` |
