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
