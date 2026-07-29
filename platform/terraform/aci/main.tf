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
