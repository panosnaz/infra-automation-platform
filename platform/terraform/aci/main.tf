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

  # Flat map of all VRFs: "tenant/vrf" => { tenant_name, vrf_name }
  vrfs = merge([
    for tn, t in local.tenants : {
      for vrf in lookup(t, "vrfs", []) :
      "${tn}/${vrf.name}" => {
        tenant_name = tn
        vrf_name    = vrf.name
      }
    }
  ]...)

  # Flat map of all Bridge Domains: "tenant/bd" => { ...bd attrs, tenant_name }
  bridge_domains = merge([
    for tn, t in local.tenants : {
      for bd in lookup(t, "bridge_domains", []) :
      "${tn}/${bd.name}" => merge(bd, { tenant_name = tn })
    }
  ]...)

  # Flat map of all subnets: "tenant/bd/ip" => { ...subnet attrs, tenant_name, bd_name }
  subnets = merge([
    for bd_key, bd in local.bridge_domains : {
      for sn in lookup(bd, "subnets", []) :
      "${bd_key}/${sn.ip}" => merge(sn, {
        tenant_name = bd.tenant_name
        bd_name     = bd.name
      })
    }
  ]...)
}

# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------
resource "aci_tenant" "this" {
  for_each    = local.tenants

  name        = each.value.name
  description = lookup(each.value, "description", null)
}

# ---------------------------------------------------------------------------
# VRFs
# ---------------------------------------------------------------------------
resource "aci_vrf" "this" {
  for_each  = local.vrfs

  parent_dn = aci_tenant.this[each.value.tenant_name].id
  name      = each.value.vrf_name
}

# ---------------------------------------------------------------------------
# Bridge Domains
# ---------------------------------------------------------------------------
resource "aci_bridge_domain" "this" {
  for_each = local.bridge_domains

  parent_dn       = aci_tenant.this[each.value.tenant_name].id
  name            = each.value.name
  unicast_routing = lookup(each.value, "unicast_routing", true) ? "yes" : "no"

  # relation_fv_rs_ctx links the BD to its VRF; the provider alias relation_to_vrf
  # uses a different schema (object with tn_fv_ctx_name) that varies by version.
  relation_fv_rs_ctx = aci_vrf.this["${each.value.tenant_name}/${each.value.vrf}"].id
}

# ---------------------------------------------------------------------------
# Subnets (BD gateway IPs)
# ---------------------------------------------------------------------------
resource "aci_subnet" "this" {
  for_each  = local.subnets

  parent_dn = aci_bridge_domain.this["${each.value.tenant_name}/${each.value.bd_name}"].id
  ip        = each.value.ip

  scope = compact([
    lookup(each.value, "public", false) ? "public" : null,
    lookup(each.value, "private", false) ? "private" : null,
    lookup(each.value, "shared", false) ? "shared" : null,
  ])
}
