# ---------------------------------------------------------------------------
# Locals — parse NetAsCode YAML and build flat maps for for_each
# ---------------------------------------------------------------------------
locals {
  nac = yamldecode(file(var.netascode_yaml_file))

  # ACI system tenants that Terraform must never recreate.
  # These exist in the YAML (exported from APIC) but are owned by ACI itself.
  _system_tenants = toset(["common", "infra", "mgmt"])

  # Only user-defined tenants are managed.
  tenants = {
    for t in local.nac.apic.tenants :
    t.name => t
    if !contains(local._system_tenants, t.name)
  }

  # Flat map of all VRFs: "tenant/vrf" => { ...vrf attrs, tenant_name, vrf_name }
  vrfs = merge([
    for tn, t in local.tenants : {
      for vrf in lookup(t, "vrfs", []) :
      "${tn}/${vrf.name}" => merge(vrf, {
        tenant_name = tn
        vrf_name    = vrf.name
      })
    }
  ]...)

  # Flat map of all Bridge Domains: "tenant/bd" => { ...bd attrs, tenant_name }
  bridge_domains = merge([
    for tn, t in local.tenants : {
      for bd in lookup(t, "bridge_domains", []) :
      "${tn}/${bd.name}" => merge(bd, { tenant_name = tn })
    }
  ]...)

  # Flat map of all subnets: "tenant/bd/ip" => { ...subnet attrs, tenant_name, bd_name, scope_values }
  subnets = merge([
    for bd_key, bd in local.bridge_domains : {
      for sn in lookup(bd, "subnets", []) :
      "${bd_key}/${sn.ip}" => merge(sn, {
        tenant_name = bd.tenant_name
        bd_name     = bd.name
        scope_values = compact([
          lookup(sn, "public", false) ? "public" : null,
          lookup(sn, "private", false) ? "private" : null,
          lookup(sn, "shared", false) ? "shared" : null,
        ])
      })
    }
  ]...)

  # ADR-020 Phase A item 2 -- Flat map of all Application Profiles:
  # "tenant/ap" => { ...ap attrs, tenant_name, ap_name }
  application_profiles = merge([
    for tn, t in local.tenants : {
      for ap in lookup(t, "application_profiles", []) :
      "${tn}/${ap.name}" => merge(ap, {
        tenant_name = tn
        ap_name     = ap.name
      })
    }
  ]...)

  # Flat map of all EPGs: "tenant/ap/epg" => { ...epg attrs, tenant_name, ap_name }
  endpoint_groups = merge([
    for ap_key, ap in local.application_profiles : {
      for epg in lookup(ap, "endpoint_groups", []) :
      "${ap_key}/${epg.name}" => merge(epg, {
        tenant_name = ap.tenant_name
        ap_name     = ap.ap_name
      })
    }
  ]...)

  # ADR-020 Phase A item 3 -- Flat map of all Filters: "tenant/filter" => {...}
  filters = merge([
    for tn, t in local.tenants : {
      for filt in lookup(t, "filters", []) :
      "${tn}/${filt.name}" => merge(filt, {
        tenant_name = tn
        filter_name = filt.name
      })
    }
  ]...)

  # Flat map of all Filter Entries: "tenant/filter/entry" => {...}
  filter_entries = merge([
    for filt_key, filt in local.filters : {
      for e in lookup(filt, "entries", []) :
      "${filt_key}/${e.name}" => merge(e, {
        tenant_name = filt.tenant_name
        filter_name = filt.filter_name
      })
    }
  ]...)

  # Flat map of all Contracts: "tenant/contract" => {...}
  contracts = merge([
    for tn, t in local.tenants : {
      for c in lookup(t, "contracts", []) :
      "${tn}/${c.name}" => merge(c, {
        tenant_name   = tn
        contract_name = c.name
      })
    }
  ]...)

  # Flat map of all Contract Subjects: "tenant/contract/subject" => {...}
  contract_subjects = merge([
    for c_key, c in local.contracts : {
      for s in lookup(c, "subjects", []) :
      "${c_key}/${s.name}" => merge(s, {
        tenant_name   = c.tenant_name
        contract_name = c.contract_name
      })
    }
  ]...)

  # Flat map of EPG-to-Contract relations, both provided and consumed, built
  # from each EPG's provided_contracts/consumed_contracts lists:
  # "tenant/ap/epg/provided/contract" or ".../consumed/contract" => {...}
  epg_contract_relations = merge([
    for epg_key, epg in local.endpoint_groups : merge(
      {
        for c in lookup(epg, "provided_contracts", []) :
        "${epg_key}/provided/${c}" => {
          tenant_name   = epg.tenant_name
          ap_name       = epg.ap_name
          epg_name      = epg.name
          contract_name = c
          contract_type = "provider"
        }
      },
      {
        for c in lookup(epg, "consumed_contracts", []) :
        "${epg_key}/consumed/${c}" => {
          tenant_name   = epg.tenant_name
          ap_name       = epg.ap_name
          epg_name      = epg.name
          contract_name = c
          contract_type = "consumer"
        }
      }
    )
  ]...)

  # ADR-020 Phase A item 4 -- Flat map of all L3Outs (logical-only MVP: no
  # physical fabric attachment, see main.tf's aci_l3_outside comment for why):
  # "tenant/l3out" => {...}
  l3outs = merge([
    for tn, t in local.tenants : {
      for l3out in lookup(t, "l3outs", []) :
      "${tn}/${l3out.name}" => merge(l3out, {
        tenant_name = tn
        l3out_name  = l3out.name
      })
    }
  ]...)

  # Flat map of all External EPGs: "tenant/l3out/epg" => {...}
  external_epgs = merge([
    for l3out_key, l3out in local.l3outs : {
      for epg in lookup(l3out, "external_epgs", []) :
      "${l3out_key}/${epg.name}" => merge(epg, {
        tenant_name = l3out.tenant_name
        l3out_name  = l3out.l3out_name
      })
    }
  ]...)

  # Flat map of all External EPG subnets: "tenant/l3out/epg/ip" => {...}
  external_epg_subnets = merge([
    for epg_key, epg in local.external_epgs : {
      for sn in lookup(epg, "subnets", []) :
      "${epg_key}/${sn.ip}" => merge(sn, {
        tenant_name = epg.tenant_name
        l3out_name  = epg.l3out_name
        epg_name    = epg.name
      })
    }
  ]...)

  # ADR-020 Phase B -- Fabric/Access Policies (logical-only MVP: no physical
  # interface binding -- see the aci_leaf_access_port_policy_group resource's
  # comment for why). Fabric-wide, not per-tenant, so read directly off
  # apic.fabric_policies/apic.access_policies rather than local.tenants.
  vlan_pools = {
    for p in lookup(lookup(local.nac.apic, "fabric_policies", {}), "vlan_pools", []) :
    p.name => p
  }

  # Flat map of all VLAN Pool ranges: "pool/from" => {...}
  vlan_pool_ranges = merge([
    for pool_name, pool in local.vlan_pools : {
      for r in lookup(pool, "ranges", []) :
      "${pool_name}/${r.from}" => merge(r, { vlan_pool_name = pool_name })
    }
  ]...)

  physical_domains = {
    for d in lookup(lookup(local.nac.apic, "access_policies", {}), "physical_domains", []) :
    d.name => d
  }

  aeps = {
    for a in lookup(lookup(local.nac.apic, "access_policies", {}), "aeps", []) :
    a.name => a
  }

  leaf_interface_policy_groups = {
    for g in lookup(lookup(local.nac.apic, "access_policies", {}), "leaf_interface_policy_groups", []) :
    g.name => g
  }

  # ADR-020 Phase D -- VMM Domain integration (VMware only for this MVP).
  # Fabric-wide, same aci_fabric_policies JSON Custom Field on Location as
  # VLAN Pools/Physical Domains/AEPs above (see main.tf's aci_vmm_domain
  # resources below). Controller and Credential are flattened out of each
  # VMM Domain entry into their own maps, same for_each-flat-map convention
  # used throughout this file.
  vmm_domains = {
    for d in lookup(lookup(local.nac.apic, "fabric_policies", {}), "vmm_domains", []) :
    d.name => d
  }
  vmm_controllers = {
    for name, d in local.vmm_domains :
    name => merge(d.controller, { vmm_domain_name = name })
    if lookup(d, "controller", null) != null
  }

  # ADR-020 Phase C -- POD-wide NTP/DNS/SNMP. Scoped to ACI's real singleton
  # default POD policies only (this lab has one POD) -- see main.tf's
  # aci_rest_managed resources below for the confirmed-live DNs/attributes.
  fabric_pod_policies = lookup(local.nac.apic, "fabric_policies", {})
  ntp_policy          = lookup(local.fabric_pod_policies, "ntp", {})
  ntp_servers = {
    for s in lookup(local.ntp_policy, "servers", []) :
    s.address => s
  }
  dns_policy = lookup(local.fabric_pod_policies, "dns", {})
  dns_servers = {
    for s in lookup(local.dns_policy, "servers", []) :
    s.address => s
  }
  dns_domains = {
    for d in lookup(local.dns_policy, "domains", []) :
    d.name => d
  }
  snmp_policy = lookup(local.fabric_pod_policies, "snmp", {})

  # ADR-020 Phase E -- COOP Group Policy / ISIS Domain Policy are mandatory
  # fabric-wide singletons too (uni/fabric/pol-default, uni/fabric/isisDomP-
  # default), same semantics as ntp/dns/snmp above. Pod Policy Groups are
  # purely additive named objects with no default instance -- ordinary
  # for_each-flat-map, no destroy-safety concern.
  coop_policy = lookup(local.fabric_pod_policies, "coop", {})
  isis_policy = lookup(local.fabric_pod_policies, "isis", {})
  pod_policy_groups = {
    for g in lookup(local.fabric_pod_policies, "pod_policy_groups", []) :
    g.name => g
  }
}

# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------
resource "aci_tenant" "this" {
  for_each = local.tenants

  name        = each.value.name
  description = lookup(each.value, "description", null)
}

# ---------------------------------------------------------------------------
# VRFs
# ---------------------------------------------------------------------------
resource "aci_vrf" "this" {
  for_each = local.vrfs

  parent_dn = aci_tenant.this[each.value.tenant_name].id
  name      = each.value.vrf_name

  # ADR-020 Phase A item 1 -- VRF attribute depth. All three are optional+
  # computed in the CiscoDevNet/aci provider (confirmed via `terraform
  # providers schema -json` against v2.20.0): passing null (the lookup
  # default when the generator omitted the key, i.e. Nautobot's custom
  # field was never set) leaves the attribute unmanaged at ACI's own
  # default, exactly like `description` above already does.
  ip_data_plane_learning               = lookup(each.value, "ip_data_plane_learning", null)
  policy_control_enforcement_direction = lookup(each.value, "policy_control_enforcement_direction", null)
  policy_control_enforcement_mode      = lookup(each.value, "policy_control_enforcement_mode", null)
}

# ---------------------------------------------------------------------------
# Bridge Domains
# ---------------------------------------------------------------------------
resource "aci_bridge_domain" "this" {
  for_each = local.bridge_domains

  parent_dn       = aci_tenant.this[each.value.tenant_name].id
  name            = each.value.name
  unicast_routing = lookup(each.value, "unicast_routing", true) ? "yes" : "no"

  # ADR-020 Phase A item 1 -- Bridge Domain attribute depth. String-valued
  # attributes pass through via lookup(..., null) (unmanaged when unset,
  # same as unicast_routing/description elsewhere in this file); boolean
  # attributes use try(...) since a direct `each.value.x` reference on a
  # for_each object errors (rather than returning null) when the generator
  # omitted that key for this particular BD -- try() converts that error
  # into the same "leave unmanaged" null.
  custom_mac_address            = lookup(each.value, "mac", null)
  arp_flooding                  = try(each.value.arp_flooding ? "yes" : "no", null)
  advertise_host_routes         = try(each.value.advertise_host_routes ? "yes" : "no", null)
  l2_unknown_unicast_flooding   = lookup(each.value, "l2_unknown_unicast", null)
  l3_unknown_multicast_flooding = lookup(each.value, "l3_unknown_multicast", null)
  multi_destination_flooding    = lookup(each.value, "multi_destination", null)
  endpoint_move_detection_mode  = lookup(each.value, "ep_move_detect_mode", null)
  pim                           = try(each.value.pim ? "yes" : "no", null)

  # relation_to_vrf is a nested attribute (not a block) expecting the VRF's
  # name, not its DN. Referencing aci_vrf.this[...].name (rather than the raw
  # YAML string) also creates the implicit dependency edge so Terraform
  # always creates the VRF before setting this relation.
  relation_to_vrf = {
    vrf_name = aci_vrf.this["${each.value.tenant_name}/${each.value.vrf}"].name
  }
}

# ---------------------------------------------------------------------------
# Subnets (BD gateway IPs)
# ---------------------------------------------------------------------------
resource "aci_subnet" "this" {
  for_each = local.subnets

  parent_dn = aci_bridge_domain.this["${each.value.tenant_name}/${each.value.bd_name}"].id
  ip        = each.value.ip

  # ACI rejects an empty scope list, so fall back to "private" if the
  # generator ever emits a subnet with public/private/shared all false.
  scope = length(each.value.scope_values) > 0 ? each.value.scope_values : ["private"]
}

# ---------------------------------------------------------------------------
# Application Profiles (ADR-020 Phase A item 2)
# ---------------------------------------------------------------------------
resource "aci_application_profile" "this" {
  for_each = local.application_profiles

  parent_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  description = lookup(each.value, "description", null)
}

# ---------------------------------------------------------------------------
# Endpoint Groups (ADR-020 Phase A item 2)
# ---------------------------------------------------------------------------
resource "aci_application_epg" "this" {
  for_each = local.endpoint_groups

  parent_dn   = aci_application_profile.this["${each.value.tenant_name}/${each.value.ap_name}"].id
  name        = each.value.name
  description = lookup(each.value, "description", null)

  # Nested relation attribute (not a block) -- referencing the BD resource's
  # own .name (rather than the raw YAML string) creates the implicit
  # dependency edge, same pattern as relation_to_vrf on aci_bridge_domain
  # above.
  relation_to_bridge_domain = {
    bridge_domain_name = aci_bridge_domain.this["${each.value.tenant_name}/${each.value.bridge_domain}"].name
  }

  # Boolean-in-Nautobot -> ACI enum string, same try(...) pattern as the
  # Bridge Domain boolean attributes above. ACI's own default is "exclude".
  preferred_group_member = try(each.value.preferred_group_member ? "include" : "exclude", null)

  # ADR-020 Phase D follow-on -- EPG-to-Domain binding (Physical or VMM).
  # relation_to_domains is the real provider attribute (confirmed via
  # `terraform providers schema -json`): a single Set-of-objects relation
  # that binds an EPG to Physical, VMM, L2 External, or L3 External domains
  # alike, keyed by target_dn. Each Nautobot-side entry carries an explicit
  # domain_type since a Physical Domain and a VMM Domain could share the
  # same name -- resolving against the wrong resource map would silently
  # bind the EPG to an unrelated domain. Left null (unmanaged) when no
  # domains are set, same convention as every other optional relation in
  # this file.
  relation_to_domains = length(lookup(each.value, "domains", [])) > 0 ? [
    for d in each.value.domains : merge(
      {
        target_dn = (
          d.domain_type == "physical"
          ? aci_physical_domain.this[d.name].id
          : aci_vmm_domain.this[d.name].id
        )
      },
      lookup(d, "resolution_immediacy", null) != null ? { resolution_immediacy = d.resolution_immediacy } : {},
      lookup(d, "deployment_immediacy", null) != null ? { deployment_immediacy = d.deployment_immediacy } : {},
    )
  ] : null
}

# ---------------------------------------------------------------------------
# Filters (ADR-020 Phase A item 3)
# ---------------------------------------------------------------------------
resource "aci_filter" "this" {
  for_each = local.filters

  tenant_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  description = lookup(each.value, "description", null)
}

resource "aci_filter_entry" "this" {
  for_each = local.filter_entries

  filter_dn = aci_filter.this["${each.value.tenant_name}/${each.value.filter_name}"].id
  name      = each.value.name

  # String-valued, null-when-unset attributes -- same lookup(...,null)
  # pattern as VRF/BD attribute depth (item 1). Valid value strings (e.g.
  # ether_t: "ip"/"arp"/...; prot: "tcp"/"udp"/"icmp"/...) are left for
  # Terraform/ACI to validate at plan/apply time, not re-validated here.
  ether_t     = lookup(each.value, "ether_type", null)
  prot        = lookup(each.value, "ip_protocol", null)
  d_from_port = lookup(each.value, "dest_from_port", null)
  d_to_port   = lookup(each.value, "dest_to_port", null)
}

# ---------------------------------------------------------------------------
# Contracts + Subjects (ADR-020 Phase A item 3)
# ---------------------------------------------------------------------------
resource "aci_contract" "this" {
  for_each = local.contracts

  tenant_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  scope       = lookup(each.value, "scope", null)
  description = lookup(each.value, "description", null)
}

resource "aci_contract_subject" "this" {
  for_each = local.contract_subjects

  contract_dn = aci_contract.this["${each.value.tenant_name}/${each.value.contract_name}"].id
  name        = each.value.name

  # A Subject's Filter Chain -- relation_vz_rs_subj_filt_att accepts a Set of
  # Filter DNs directly (no separate aci_contract_subject_filter resource
  # needed for the MVP scope here: no per-filter action/directive/priority
  # override). Referencing each filter's own .id (rather than the raw YAML
  # string) creates the implicit dependency edge, same pattern as
  # relation_to_vrf/relation_to_bridge_domain above.
  relation_vz_rs_subj_filt_att = [
    for f in lookup(each.value, "filters", []) :
    aci_filter.this["${each.value.tenant_name}/${f}"].id
  ]
}

# ---------------------------------------------------------------------------
# EPG-to-Contract relations, provided and consumed (ADR-020 Phase A item 3)
# ---------------------------------------------------------------------------
resource "aci_epg_to_contract" "this" {
  for_each = local.epg_contract_relations

  application_epg_dn = aci_application_epg.this["${each.value.tenant_name}/${each.value.ap_name}/${each.value.epg_name}"].id
  contract_dn        = aci_contract.this["${each.value.tenant_name}/${each.value.contract_name}"].id
  contract_type      = each.value.contract_type
}

# ---------------------------------------------------------------------------
# L3Out (ADR-020 Phase A item 4 -- logical-only MVP)
#
# Scope deliberately excludes physical fabric attachment (Logical Node/
# Interface Profiles, routed interfaces, OSPF/BGP protocol config): Nautobot's
# DCIM has zero leaf/spine devices synced today (only the APIC controller
# itself), so a real node/interface path can't be sourced from actual fabric
# inventory yet (that's Phase B's problem -- see ADR-020). This reserves the
# L3Out object, its VRF association, External EPGs, and their
# subnets/contract references -- enough to bind Contracts to external
# traffic classification, but NOT enough alone to pass real external traffic
# without additional manual interface/routing configuration in the APIC.
# ---------------------------------------------------------------------------
resource "aci_l3_outside" "this" {
  for_each = local.l3outs

  tenant_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  description = lookup(each.value, "description", null)

  # Required relation to the L3Out's VRF -- referencing the VRF's own .id
  # (rather than the raw YAML string) creates the implicit dependency edge,
  # same pattern as relation_to_vrf/relation_to_bridge_domain above.
  relation_l3ext_rs_ectx = aci_vrf.this["${each.value.tenant_name}/${each.value.vrf}"].id
}

resource "aci_external_network_instance_profile" "this" {
  for_each = local.external_epgs

  l3_outside_dn = aci_l3_outside.this["${each.value.tenant_name}/${each.value.l3out_name}"].id
  name          = each.value.name
  description   = lookup(each.value, "description", null)

  # Direct Set-of-Contract-DN attributes, same simple pattern as
  # aci_contract_subject.relation_vz_rs_subj_filt_att (item 3) -- no nested
  # relation blocks needed for this MVP scope.
  relation_fv_rs_prov = [
    for c in lookup(each.value, "provided_contracts", []) :
    aci_contract.this["${each.value.tenant_name}/${c}"].id
  ]
  relation_fv_rs_cons = [
    for c in lookup(each.value, "consumed_contracts", []) :
    aci_contract.this["${each.value.tenant_name}/${c}"].id
  ]
}

resource "aci_l3_ext_subnet" "this" {
  for_each = local.external_epg_subnets

  external_network_instance_profile_dn = aci_external_network_instance_profile.this["${each.value.tenant_name}/${each.value.l3out_name}/${each.value.epg_name}"].id
  ip                                   = each.value.ip

  scope     = lookup(each.value, "scope", null)
  aggregate = lookup(each.value, "aggregate", null)
}

# ---------------------------------------------------------------------------
# Fabric Policies: VLAN Pools (ADR-020 Phase B, logical-only MVP)
# ---------------------------------------------------------------------------
resource "aci_vlan_pool" "this" {
  for_each = local.vlan_pools

  name        = each.value.name
  alloc_mode  = each.value.alloc_mode
  description = lookup(each.value, "description", null)
}

resource "aci_ranges" "this" {
  for_each = local.vlan_pool_ranges

  vlan_pool_dn = aci_vlan_pool.this[each.value.vlan_pool_name].id
  from         = each.value.from
  to           = each.value.to
  alloc_mode   = lookup(each.value, "alloc_mode", null)
  role         = lookup(each.value, "role", null)
}

# ---------------------------------------------------------------------------
# Access Policies: Physical Domains, AEPs, Leaf Interface Policy Groups
# (ADR-020 Phase B, logical-only MVP)
#
# Deliberately excludes physical port/interface binding (Leaf/Interface
# Profiles + Access Port Selectors, which require real leaf node/port
# names): this ACI simulator has zero real interface data available at all
# -- confirmed via direct APIC API query (no l1PhysIf objects exist
# anywhere, and node-scoped queries fail with "node marked unavailable",
# meaning this simulator does not proxy queries down to individual switch
# MITs). This models the fabric-wide policy OBJECTS themselves (VLAN Pool,
# Physical Domain, AEP, Leaf Interface Policy Group + their relations to
# each other), which require no physical port data to create, but stops
# short of binding any of them to a real leaf/port.
# ---------------------------------------------------------------------------
resource "aci_physical_domain" "this" {
  for_each = local.physical_domains

  name = each.value.name

  # Relation to the VLAN Pool DN -- referencing the pool's own .id (rather
  # than the raw YAML string) creates the implicit dependency edge, same
  # pattern as relation_to_vrf/relation_to_bridge_domain elsewhere in this
  # file.
  relation_infra_rs_vlan_ns = (
    lookup(each.value, "vlan_pool", null) != null
    ? aci_vlan_pool.this[each.value.vlan_pool].id
    : null
  )
}

resource "aci_attachable_access_entity_profile" "this" {
  for_each = local.aeps

  name = each.value.name

  # Nested relation blocks (list-of-objects, not a plain Set-of-DN) --
  # relation_infra_rs_dom_p is the older, deprecated equivalent attribute;
  # relation_to_domains is the provider's current recommended replacement.
  relation_to_domains = [
    for d in lookup(each.value, "domains", []) :
    { target_dn = aci_physical_domain.this[d].id }
  ]
}

resource "aci_leaf_access_port_policy_group" "this" {
  for_each = local.leaf_interface_policy_groups

  name = each.value.name

  relation_infra_rs_att_ent_p = (
    lookup(each.value, "aep", null) != null
    ? aci_attachable_access_entity_profile.this[each.value.aep].id
    : null
  )
}

# ---------------------------------------------------------------------------
# VMM Domain integration (ADR-020 Phase D, VMware-only MVP)
#
# Real CiscoDevNet/aci 2.20.0 resource/attribute names confirmed via the
# Terraform Registry provider docs (not assumed): `aci_vmm_domain`'s
# `parent_dn` is the fixed provider DN `uni/vmmp-VMware` (vmmProvP is a
# built-in ACI object per vendor, not something Terraform creates);
# `aci_vmm_controller`'s `host_or_ip`/`root_cont_name` (vCenter's Datacenter
# name) are required and create-only; `aci_vmm_credential` stores the
# username directly but excludes `password` from its own state tracking
# (the provider documents this attribute as write-only/untracked). The
# actual vCenter username/password are supplied via the sensitive
# `vmm_vcenter_username`/`vmm_vcenter_password` Terraform variables (see
# variables.tf) -- never through the generated YAML or a Nautobot Custom
# Field, same pattern as this module's own `aci_username`/`aci_password`
# provider credentials.
# ---------------------------------------------------------------------------
resource "aci_vmm_domain" "this" {
  for_each = local.vmm_domains

  parent_dn = "uni/vmmp-${lookup(each.value, "vendor", "VMware")}"
  name      = each.value.name

  # Relation to a VLAN Pool DN -- referencing the pool's own .id (rather
  # than the raw YAML string) creates the implicit dependency edge, same
  # pattern as aci_physical_domain.relation_infra_rs_vlan_ns above.
  relation_to_vlan_pool = (
    lookup(each.value, "vlan_pool", null) != null
    ? { target_dn = aci_vlan_pool.this[each.value.vlan_pool].id }
    : null
  )
}

resource "aci_vmm_credential" "this" {
  for_each = { for name, d in local.vmm_domains : name => d if lookup(d, "credential", null) != null }

  parent_dn = aci_vmm_domain.this[each.key].id
  name      = each.value.credential.name
  username  = var.vmm_vcenter_username
  password  = var.vmm_vcenter_password
}

resource "aci_vmm_controller" "this" {
  for_each = local.vmm_controllers

  vmm_domain_dn  = aci_vmm_domain.this[each.value.vmm_domain_name].id
  name           = each.value.name
  host_or_ip     = each.value.host_or_ip
  root_cont_name = each.value.root_cont_name
  dvs_version    = lookup(each.value, "dvs_version", "unmanaged")

  # Only set the credential relation when this VMM Domain has one -- avoids
  # a broken reference for a domain that (unusually) has a controller but no
  # credential entry.
  relation_vmm_rs_acc = (
    contains(keys(aci_vmm_credential.this), each.value.vmm_domain_name)
    ? aci_vmm_credential.this[each.value.vmm_domain_name].id
    : null
  )
}

# ---------------------------------------------------------------------------
# Fabric Policies: POD-wide NTP/DNS/SNMP (ADR-020 Phase C)
#
# Targets ACI's real singleton default POD policies -- confirmed live
# against the real simulator (not guessed): `uni/fabric/time-default`,
# `uni/fabric/dnsp-default`, `uni/fabric/snmppol-default` all exist by
# default in every ACI fabric. Managed via the generic `aci_rest_managed`
# resource since the CiscoDevNet/aci provider (v2.20.0, confirmed via
# `terraform providers schema -json`) has no dedicated typed resource for
# NTP/DNS Profile -- only `aci_snmp_community`/`aci_snmp_user` exist as
# typed children for SNMP, attached via `parent_dn`. Attribute names
# (`datetimeNtpProv.name`/`preferred`/`minPoll`/`maxPoll`,
# `dnsProv.addr`/`preferred`, `dnsDomain.name`/`isDefault`) were confirmed
# by live-creating and deleting real test objects against the simulator,
# not assumed from documentation. Scoped to the single default POD Policy
# Group only (this lab has one POD) -- custom-named alternate policies with
# explicit POD Policy Group assignment are out of scope.
#
# CRITICAL -- `content_on_destroy` is mandatory on all three resources
# below: `aci_rest_managed`'s default destroy behavior deletes the entire
# target DN, not just the attributes/children this resource added. These
# three DNs are mandatory ACI system singletons that always exist in every
# fabric -- a plain `terraform destroy` was confirmed live to actually
# delete them from the real simulator (not just disable/reset them),
# requiring manual recreation to restore the pre-existing baseline. Never
# remove `content_on_destroy` from these three resources.
# ---------------------------------------------------------------------------
resource "aci_rest_managed" "ntp_policy" {
  count = length(local.ntp_policy) > 0 ? 1 : 0

  dn         = "uni/fabric/time-default"
  class_name = "datetimePol"
  content = {
    adminSt = lookup(local.ntp_policy, "admin_state", "enabled")
  }
  # Resets to this lab's confirmed original defaults on destroy/removal --
  # never deletes the mandatory singleton object itself.
  content_on_destroy = {
    adminSt = "enabled"
  }

  dynamic "child" {
    for_each = local.ntp_servers
    content {
      rn         = "ntpprov-${child.value.address}"
      class_name = "datetimeNtpProv"
      content = {
        name      = child.value.address
        preferred = lookup(child.value, "preferred", false) ? "yes" : "no"
        minPoll   = tostring(lookup(child.value, "min_poll", 4))
        maxPoll   = tostring(lookup(child.value, "max_poll", 6))
      }
    }
  }
}

resource "aci_rest_managed" "dns_profile" {
  count = length(local.dns_policy) > 0 ? 1 : 0

  dn         = "uni/fabric/dnsp-default"
  class_name = "dnsProfile"
  content    = {}
  # Resets to this lab's confirmed original default on destroy/removal --
  # never deletes the mandatory singleton object itself.
  content_on_destroy = {
    IPVerPreference = "IPv4"
  }

  dynamic "child" {
    for_each = local.dns_servers
    content {
      rn         = "prov-[${child.value.address}]"
      class_name = "dnsProv"
      content = {
        addr      = child.value.address
        preferred = lookup(child.value, "preferred", false) ? "yes" : "no"
      }
    }
  }

  dynamic "child" {
    for_each = local.dns_domains
    content {
      rn         = "dom-${child.value.name}"
      class_name = "dnsDomain"
      content = {
        name      = child.value.name
        isDefault = lookup(child.value, "is_default", false) ? "yes" : "no"
      }
    }
  }
}

resource "aci_rest_managed" "snmp_policy" {
  count = length(local.snmp_policy) > 0 ? 1 : 0

  dn         = "uni/fabric/snmppol-default"
  class_name = "snmpPol"
  content = {
    adminSt = lookup(local.snmp_policy, "admin_state", "enabled")
    contact = lookup(local.snmp_policy, "contact", null)
    loc     = lookup(local.snmp_policy, "location", null)
  }
  # Resets to this lab's confirmed original defaults on destroy/removal --
  # never deletes the mandatory singleton object itself.
  content_on_destroy = {
    adminSt = "disabled"
    contact = ""
    loc     = ""
  }
}

resource "aci_snmp_community" "this" {
  for_each = length(local.snmp_policy) > 0 ? { for c in lookup(local.snmp_policy, "communities", []) : c.name => c } : {}

  parent_dn = "uni/fabric/snmppol-default"
  name      = each.value.name

  depends_on = [aci_rest_managed.snmp_policy]
}

# ---------------------------------------------------------------------------
# ADR-020 Phase E -- COOP Group Policy / ISIS Domain Policy (mandatory
# fabric-wide singletons, confirmed via direct APIC query: uni/fabric/pol-
# default and uni/fabric/isisDomP-default respectively). Unlike ntp/dns/snmp
# above, the CiscoDevNet/aci provider exposes these through real *typed*
# resources (aci_coop_policy/aci_isis_domain_policy) rather than the generic
# aci_rest_managed -- confirmed via `terraform providers schema -json`: both
# take no parent_dn (the provider itself always targets the one fixed DN,
# there is only ever one of each in a fabric). Neither typed resource has a
# content_on_destroy-equivalent lever, so a genuine `terraform destroy`
# still risks the same class of incident Phase C hit -- live-verified
# end-to-end in an isolated state before trusting this in the shared fleet.
resource "aci_coop_policy" "this" {
  count = length(local.coop_policy) > 0 ? 1 : 0

  type        = lookup(local.coop_policy, "type", null)
  description = lookup(local.coop_policy, "description", null)
}

resource "aci_isis_domain_policy" "this" {
  count = length(local.isis_policy) > 0 ? 1 : 0

  mtu              = lookup(local.isis_policy, "mtu", null)
  redistrib_metric = lookup(local.isis_policy, "redistrib_metric", null)
  description      = lookup(local.isis_policy, "description", null)
}

# ADR-020 Phase E -- named Pod Policy Groups (fabricPodPGrp). Purely
# additive: no default instance exists in a fresh fabric (confirmed via
# direct APIC class query: 0 pre-existing instances), so ordinary
# aci_rest_managed destroy behavior (delete the DN) is correct here, unlike
# the singleton resources above -- no content_on_destroy needed.
resource "aci_rest_managed" "pod_policy_group" {
  for_each = local.pod_policy_groups

  dn         = "uni/fabric/funcprof/podpgrp-${each.value.name}"
  class_name = "fabricPodPGrp"
  content = {
    name = each.value.name
  }
}

