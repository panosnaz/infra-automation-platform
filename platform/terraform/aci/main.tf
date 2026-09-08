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

  # Tenant-scoped L4-L7/PBR services. The structure is emitted from each
  # Tenant's aci_l4l7_services JSON Custom Field; unlike VMM credentials,
  # this data contains no runtime secrets.
  l4l7_devices = merge([
    for tn, t in local.tenants : {
      for device in lookup(lookup(t, "services", {}), "devices", []) :
      "${tn}/${device.name}" => merge(device, {
        tenant_name = tn
        device_name = device.name
      })
    }
  ]...)

  l4l7_logical_interfaces = merge([
    for device_key, device in local.l4l7_devices : {
      for interface in lookup(device, "logical_interfaces", []) :
      "${device_key}/${interface.name}" => merge(interface, {
        tenant_name = device.tenant_name
        device_name = device.device_name
      })
    }
  ]...)

  service_graphs = merge([
    for tn, t in local.tenants : {
      for graph in lookup(lookup(t, "services", {}), "service_graphs", []) :
      "${tn}/${graph.name}" => merge(graph, {
        tenant_name = tn
        graph_name  = graph.name
      })
    }
  ]...)

  # One logical interface context per Service Graph arm. Each arm binds the
  # graph's logical device context to a logical interface and PBR policy.
  service_graph_interface_contexts = merge([
    for graph_key, graph in local.service_graphs : {
      for side in ["consumer", "provider"] :
      "${graph_key}/${side}" => merge(graph[side], {
        tenant_name = graph.tenant_name
        graph_name  = graph.graph_name
        device_name = graph.device
        side        = side
      })
      if lookup(graph, side, null) != null
    }
  ]...)

  redirect_policies = merge([
    for tn, t in local.tenants : {
      for policy in lookup(lookup(t, "services", {}), "redirect_policies", []) :
      "${tn}/${policy.name}" => merge(policy, {
        tenant_name = tn
        policy_name = policy.name
      })
    }
  ]...)

  redirect_destinations = merge([
    for policy_key, policy in local.redirect_policies : {
      for destination in lookup(policy, "destinations", []) :
      "${policy_key}/${destination.ip}" => merge(destination, {
        tenant_name = policy.tenant_name
        policy_name = policy.policy_name
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

  l3out_bgp_policies  = { for k, l in local.l3outs : k => l if lookup(l, "protocol", "") == "bgp" }
  l3out_ospf_policies = { for k, l in local.l3outs : k => l if lookup(l, "protocol", "") == "ospf" }
  ospf_interface_policies = merge([
    for tn, t in local.tenants : {
      for p in lookup(t, "ospf_interface_policies", []) :
      "${tn}/${p.name}" => merge(p, { tenant_name = tn })
    }
  ]...)

  # Tenant-scoped VRF route leaks. The provider resource creates the leak
  # route under the destination VRF; source_vrf remains explicit intent
  # metadata because this provider version exposes no source-VRF argument.
  vrf_route_leaks = merge([
    for tn, t in local.tenants : {
      for leak in lookup(t, "vrf_route_leaks", []) :
      "${tn}/${leak.name}" => merge(leak, {
        tenant_name = tn
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

  ipg_cdp_policies = {
    for g in lookup(lookup(local.nac.apic, "access_policies", {}), "leaf_interface_policy_groups", []) :
    g.name => merge(lookup(g, "policies", {}).cdp, { ipg_name = g.name })
    if lookup(lookup(g, "policies", {}), "cdp", null) != null
  }
  ipg_lldp_policies = {
    for g in lookup(lookup(local.nac.apic, "access_policies", {}), "leaf_interface_policy_groups", []) :
    g.name => merge(lookup(g, "policies", {}).lldp, { ipg_name = g.name })
    if lookup(lookup(g, "policies", {}), "lldp", null) != null
  }
  ipg_link_policies = {
    for g in lookup(lookup(local.nac.apic, "access_policies", {}), "leaf_interface_policy_groups", []) :
    g.name => merge(lookup(g, "policies", {}), { ipg_name = g.name })
    if lookup(lookup(g, "policies", {}), "speed", null) != null || lookup(lookup(g, "policies", {}), "duplex", null) != null
  }
  ipg_stp_policies = {
    for g in lookup(lookup(local.nac.apic, "access_policies", {}), "leaf_interface_policy_groups", []) :
    g.name => merge(lookup(g, "policies", {}), { ipg_name = g.name })
    if lookup(lookup(g, "policies", {}), "spanning_tree", null) != null
  }
  ipg_port_security_policies = {
    for g in lookup(lookup(local.nac.apic, "access_policies", {}), "leaf_interface_policy_groups", []) :
    g.name => merge(lookup(g, "policies", {}), { ipg_name = g.name })
    if lookup(lookup(g, "policies", {}), "port_security", false) == true
  }

  leaf_interface_profiles = {
    for p in lookup(lookup(local.nac.apic, "access_policies", {}), "leaf_interface_profiles", []) :
    p.name => p
  }
  interface_selectors = {
    for s in lookup(lookup(local.nac.apic, "access_policies", {}), "interface_selectors", []) :
    s.name => s
  }

  epg_domain_bindings = merge([
    for epg_key, epg in local.endpoint_groups : merge(
      { for d in lookup(epg, "physical_domains", []) :
      "${epg_key}/physical/${d}" => { epg = epg, domain = d, kind = "physical" } },
      { for d in lookup(epg, "vmm_domains", []) :
      "${epg_key}/vmm/${d.name}" => { epg = epg, domain = d.name, kind = "vmm", details = d } },
    )
  ]...)

  static_path_bindings = merge([
    for epg_key, epg in local.endpoint_groups : {
      for p in lookup(epg, "static_paths", []) :
      "${epg_key}/${p.node_id}/${p.module}/${p.port}" => merge(p, {
        tenant_name = epg.tenant_name
        ap_name     = epg.ap_name
        epg_name    = epg.name
      })
    }
  ]...)

  l3out_node_profiles = merge([
    for l3out_key, l3out in local.l3outs : {
      for p in lookup(l3out, "node_profiles", []) :
      "${l3out_key}/${p.name}" => merge(p, { tenant_name = l3out.tenant_name, l3out_name = l3out.name, l3out_key = l3out_key })
    }
  ]...)
  l3out_nodes = merge([
    for profile_key, profile in local.l3out_node_profiles : {
      for n in lookup(profile, "nodes", []) :
      "${profile_key}/${n.node_id}" => merge(n, { profile_key = profile_key, tenant_name = profile.tenant_name, l3out_name = profile.l3out_name, l3out_key = profile.l3out_key })
    }
  ]...)
  l3out_interface_profiles = merge([
    for profile_key, profile in local.l3out_node_profiles : {
      for p in lookup(profile, "interface_profiles", []) :
      "${profile_key}/${p.name}" => merge(p, { node_profile_key = profile_key, tenant_name = profile.tenant_name, l3out_name = profile.l3out_name, l3out_key = profile.l3out_key })
    }
  ]...)
  l3out_interfaces = merge([
    for ip_key, profile in local.l3out_interface_profiles : {
      for i in lookup(profile, "interfaces", []) :
      "${ip_key}/${i.node_id}/${i.module}/${i.port}" => merge(i, { interface_profile_key = ip_key, node_profile_key = profile.node_profile_key, l3out_key = profile.l3out_key, tenant_name = profile.tenant_name })
    }
  ]...)
  bgp_peers = merge([
    for interface_key, i in local.l3out_interfaces : {
      for p in lookup(i, "bgp_peers", []) :
      "${interface_key}/${p.ip}" => merge(p, { interface_key = interface_key, l3out_key = i.l3out_key, node_profile_key = i.node_profile_key })
    }
  ]...)
  ospf_interfaces = merge([
    for interface_key, i in local.l3out_interfaces : {
      for o in lookup(i, "ospf", []) :
      "${interface_key}/${o.name}" => merge(o, { interface_key = i.interface_profile_key, l3out_key = i.l3out_key, tenant_name = i.tenant_name })
    }
  ]...)

  # VMware VMM Domains (logical ACI-side objects). vCenter username/password
  # are runtime Terraform variables, never generated into YAML.
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

  relation_vz_rs_subj_graph_att = (
    lookup(each.value, "service_graph", null) != null
    ? aci_l4_l7_service_graph_template.this["${each.value.tenant_name}/${each.value.service_graph}"].id
    : null
  )
}

# ---------------------------------------------------------------------------
# L4-L7 Devices, Service Graphs, and Policy-Based Redirect
# ---------------------------------------------------------------------------
resource "aci_l4_l7_device" "this" {
  for_each = local.l4l7_devices

  tenant_dn     = aci_tenant.this[each.value.tenant_name].id
  name          = each.value.device_name
  service_type  = lookup(each.value, "service_type", null)
  device_type   = upper(lookup(each.value, "device_type", "VIRTUAL"))
  function_type = lookup(each.value, "function_type", null)
  managed       = try(each.value.managed ? "yes" : "no", null)
  context_aware = lookup(each.value, "context_aware", null)
  trunking      = try(each.value.trunking ? "yes" : "no", null)
  promiscuous_mode = try(
    each.value.promiscuous_mode ? "yes" : "no",
    null,
  )
  description = lookup(each.value, "description", null)

  dynamic "relation_vns_rs_al_dev_to_dom_p" {
    for_each = lookup(each.value, "vmm_domain", null) != null ? [each.value.vmm_domain] : []

    content {
      domain_dn = aci_vmm_domain.this[relation_vns_rs_al_dev_to_dom_p.value].id
    }
  }
}

resource "aci_l4_l7_logical_interface" "this" {
  for_each = local.l4l7_logical_interfaces

  l4_l7_device_dn = aci_l4_l7_device.this["${each.value.tenant_name}/${each.value.device_name}"].id
  name            = each.value.name
  description     = lookup(each.value, "description", null)
}

resource "aci_l4_l7_service_graph_template" "this" {
  for_each = local.service_graphs

  tenant_dn                         = aci_tenant.this[each.value.tenant_name].id
  name                              = each.value.graph_name
  l4_l7_service_graph_template_type = lookup(each.value, "graph_type", "legacy")
  ui_template_type = lookup(
    {
      FW_ROUTED = "ONE_NODE_FW_ROUTED"
      FW_TRANS  = "ONE_NODE_FW_TRANS"
    },
    upper(lookup(each.value, "template_type", "UNSPECIFIED")),
    upper(lookup(each.value, "template_type", "UNSPECIFIED")),
  )
  term_cons_name = lookup(each.value, "consumer_terminal_name", "consumer")
  term_prov_name = lookup(each.value, "provider_terminal_name", "provider")
  description    = lookup(each.value, "description", null)
}

resource "aci_logical_device_context" "this" {
  for_each = local.service_graphs

  tenant_dn                          = aci_tenant.this[each.value.tenant_name].id
  ctrct_name_or_lbl                  = each.value.contract
  graph_name_or_lbl                  = each.value.graph_name
  node_name_or_lbl                   = lookup(each.value, "node_name", "node-1")
  relation_vns_rs_l_dev_ctx_to_l_dev = aci_l4_l7_device.this["${each.value.tenant_name}/${each.value.device}"].id
  depends_on = [
    aci_contract.this,
    aci_l4_l7_service_graph_template.this,
  ]
}

resource "aci_logical_interface_context" "this" {
  for_each = local.service_graph_interface_contexts

  logical_device_context_dn = aci_logical_device_context.this["${each.value.tenant_name}/${each.value.graph_name}"].id
  conn_name_or_lbl          = each.value.side
  relation_vns_rs_l_if_ctx_to_l_if = aci_l4_l7_logical_interface.this[
    "${each.value.tenant_name}/${each.value.device_name}/${each.value.logical_interface}"
  ].id
  relation_vns_rs_l_if_ctx_to_svc_redirect_pol = aci_service_redirect_policy.this[
    "${each.value.tenant_name}/${each.value.redirect_policy}"
  ].id
  l3_dest = try(each.value.l3_destination ? "yes" : "no", null)
}

resource "aci_service_redirect_policy" "this" {
  for_each = local.redirect_policies

  tenant_dn              = aci_tenant.this[each.value.tenant_name].id
  name                   = each.value.policy_name
  dest_type              = lookup(each.value, "destination_type", "L3")
  anycast_enabled        = try(each.value.anycast ? "yes" : "no", null)
  program_local_pod_only = try(each.value.pod_aware ? "yes" : "no", null)
  resilient_hash_enabled = try(each.value.resilient_hashing ? "yes" : "no", null)
  description            = lookup(each.value, "description", null)
}

resource "aci_destination_of_redirected_traffic" "this" {
  for_each = local.redirect_destinations

  service_redirect_policy_dn = aci_service_redirect_policy.this["${each.value.tenant_name}/${each.value.policy_name}"].id
  ip                         = each.value.ip
  mac                        = lookup(each.value, "mac", null)
  description                = lookup(each.value, "description", null)
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

resource "aci_logical_node_profile" "this" {
  for_each      = local.l3out_node_profiles
  l3_outside_dn = aci_l3_outside.this["${each.value.tenant_name}/${each.value.l3out_name}"].id
  name          = each.value.name
  description   = lookup(each.value, "description", null)
}

resource "aci_logical_node_to_fabric_node" "this" {
  for_each                = local.l3out_nodes
  logical_node_profile_dn = aci_logical_node_profile.this[each.value.profile_key].id
  tdn                     = "topology/pod-${each.value.pod_id}/node-${each.value.node_id}"
  rtr_id                  = lookup(each.value, "router_id", null)
  rtr_id_loop_back        = try(each.value.router_id_as_loopback ? "yes" : "no", null)
}

resource "aci_logical_interface_profile" "this" {
  for_each                = local.l3out_interface_profiles
  logical_node_profile_dn = aci_logical_node_profile.this[each.value.node_profile_key].id
  name                    = each.value.name
  description             = lookup(each.value, "description", null)
}

resource "aci_l3out_path_attachment" "this" {
  for_each                     = { for k, i in local.l3out_interfaces : k => i if !try(i.svi, false) }
  logical_interface_profile_dn = aci_logical_interface_profile.this[each.value.interface_profile_key].id
  if_inst_t                    = "l3-port"
  target_dn                    = "topology/pod-${each.value.pod_id}/paths-${each.value.node_id}/pathep-[eth${each.value.module}/${each.value.port}]"
  addr                         = lookup(each.value, "ip", null)
  encap                        = lookup(each.value, "vlan", null) != null ? "vlan-${each.value.vlan}" : null
  mode                         = lookup(each.value, "mode", null)
  mtu                          = lookup(each.value, "mtu", null)
}

resource "aci_l3out_floating_svi" "this" {
  for_each                     = { for k, i in local.l3out_interfaces : k => i if try(i.svi, false) }
  logical_interface_profile_dn = aci_logical_interface_profile.this[each.value.interface_profile_key].id
  node_dn                      = "topology/pod-${each.value.pod_id}/node-${each.value.node_id}"
  encap                        = "vlan-${each.value.vlan}"
  addr                         = lookup(each.value, "ip", null)
  mode                         = lookup(each.value, "mode", null)
  mtu                          = lookup(each.value, "mtu", null)
}

resource "aci_l3out_bgp_protocol_profile" "this" {
  for_each                = local.l3out_bgp_policies
  logical_node_profile_dn = one([for k, p in local.l3out_node_profiles : aci_logical_node_profile.this[k].id if startswith(k, "${each.key}/")])
}

resource "aci_bgp_peer_connectivity_profile" "this" {
  for_each                = local.bgp_peers
  parent_dn               = aci_l3out_bgp_protocol_profile.this[each.value.l3out_key].id
  logical_node_profile_dn = aci_logical_node_profile.this[each.value.node_profile_key].id
  addr                    = each.value.ip
  as_number               = tostring(each.value.remote_as)
  local_asn               = tostring(each.value.local_as)
  admin_state             = try(each.value.admin_state ? "enabled" : "disabled", null)
  ttl                     = tostring(lookup(each.value, "ttl", 1))
  weight                  = tostring(lookup(each.value, "weight", 0))
  allowed_self_as_cnt     = tostring(lookup(each.value, "allowed_self_as_count", 0))
}

resource "aci_l3out_ospf_interface_profile" "this" {
  for_each                     = local.ospf_interfaces
  logical_interface_profile_dn = aci_logical_interface_profile.this[each.value.interface_key].id
  relation_ospf_rs_if_pol      = lookup(each.value, "policy", null) != null ? aci_ospf_interface_policy.this["${each.value.tenant_name}/${each.value.policy}"].id : null
  auth_type                    = lookup(each.value, "authentication_type", null)
  auth_key_id                  = lookup(each.value, "authentication_key_id", null)
}

resource "aci_ospf_interface_policy" "this" {
  for_each = local.ospf_interface_policies

  tenant_dn = aci_tenant.this[each.value.tenant_name].id
  name      = each.value.name
  nw_t = lookup({
    "point-to-point" = "p2p"
    "broadcast"      = "bcast"
  }, lower(lookup(each.value, "network_type", "unspecified")), lower(lookup(each.value, "network_type", "unspecified")))
  hello_intvl = lookup(each.value, "hello_interval", null)
  dead_intvl  = lookup(each.value, "dead_interval", null)
  cost        = lookup(each.value, "cost", null)
  prio        = lookup(each.value, "priority", null)
  ctrl = compact([
    try(each.value.passive ? "passive" : null, null),
  ])
  description = lookup(each.value, "description", null)
}

# ---------------------------------------------------------------------------
# VRF Route Leaking
# ---------------------------------------------------------------------------
resource "aci_vrf_leak_epg_bd_subnet" "this" {
  for_each = local.vrf_route_leaks

  vrf_dn = aci_vrf.this["${each.value.tenant_name}/${each.value.destination_vrf}"].id
  ip     = each.value.subnet

  allow_l3out_advertisement = try(
    each.value.allow_l3out_advertisement ? "true" : "false",
    null,
  )
  description = lookup(each.value, "description", null)
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
  relation_infra_rs_cdp_if_pol           = lookup(local.ipg_cdp_policies, each.key, null) != null ? aci_cdp_interface_policy.this[each.key].id : null
  relation_infra_rs_lldp_if_pol          = lookup(local.ipg_lldp_policies, each.key, null) != null ? aci_lldp_interface_policy.this[each.key].id : null
  relation_infra_rs_l2_if_pol            = lookup(local.ipg_link_policies, each.key, null) != null ? aci_link_level_interface_policy.this[each.key].id : null
  relation_infra_rs_stp_if_pol           = lookup(local.ipg_stp_policies, each.key, null) != null ? aci_spanning_tree_interface_policy.this[each.key].id : null
  relation_infra_rs_l2_port_security_pol = lookup(local.ipg_port_security_policies, each.key, null) != null ? aci_port_security_interface_policy.this[each.key].id : null
}

resource "aci_cdp_interface_policy" "this" {
  for_each    = local.ipg_cdp_policies
  name        = "${each.key}-cdp"
  admin_state = try(each.value.enabled ? "enabled" : "disabled", null)
}

resource "aci_lldp_interface_policy" "this" {
  for_each    = local.ipg_lldp_policies
  name        = "${each.key}-lldp"
  admin_rx_st = try(each.value.receive ? "enabled" : "disabled", null)
  admin_tx_st = try(each.value.transmit ? "enabled" : "disabled", null)
}

resource "aci_link_level_interface_policy" "this" {
  for_each = local.ipg_link_policies
  name     = "${each.key}-link"
  auto_negotiation = lookup({
    auto = "on"
    full = "on-enforce"
  }, lower(lookup(each.value, "duplex", "auto")), "on")
  speed = lookup(each.value, "speed", null)
}

resource "aci_spanning_tree_interface_policy" "this" {
  for_each           = local.ipg_stp_policies
  name               = "${each.key}-stp"
  interface_controls = [each.value.spanning_tree]
}

resource "aci_port_security_interface_policy" "this" {
  for_each         = local.ipg_port_security_policies
  name             = "${each.key}-port-security"
  violation_action = each.value.port_security ? "protect" : "shutdown"
}

resource "aci_leaf_interface_profile" "this" {
  for_each    = local.leaf_interface_profiles
  name        = each.value.name
  description = lookup(each.value, "description", null)
}

resource "aci_access_port_selector" "this" {
  for_each                                  = local.interface_selectors
  leaf_interface_profile_dn                 = aci_leaf_interface_profile.this[each.value.leaf_interface_profile].id
  name                                      = each.value.name
  port_selector_type                        = lookup(each.value, "port_selector_type", "range")
  relation_to_leaf_access_port_policy_group = { target_dn = aci_leaf_access_port_policy_group.this[each.value.policy_group].id }
}

resource "aci_epg_to_domain" "this" {
  for_each           = local.epg_domain_bindings
  application_epg_dn = aci_application_epg.this["${each.value.epg.tenant_name}/${each.value.epg.ap_name}/${each.value.epg.name}"].id
  tdn                = each.value.kind == "physical" ? aci_physical_domain.this[each.value.domain].id : aci_vmm_domain.this[each.value.domain].id
  encap              = each.value.kind == "vmm" ? lookup(each.value.details, "encap", null) : null
  encap_mode         = each.value.kind == "vmm" ? lookup(each.value.details, "mode", null) : null
}

resource "aci_epg_to_static_path" "this" {
  for_each           = local.static_path_bindings
  application_epg_dn = aci_application_epg.this["${each.value.tenant_name}/${each.value.ap_name}/${each.value.epg_name}"].id
  tdn                = "topology/pod-${each.value.pod_id}/paths-${each.value.node_id}/pathep-[eth${each.value.module}/${each.value.port}]"
  encap              = each.value.encap
  mode               = lookup(each.value, "mode", "regular")
}

# ---------------------------------------------------------------------------
# VMware VMM Domains
# ---------------------------------------------------------------------------
resource "aci_vmm_domain" "this" {
  for_each = local.vmm_domains

  parent_dn = "uni/vmmp-${lookup(each.value, "vendor", "VMware")}"
  name      = each.value.name

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

  relation_vmm_rs_acc = (
    lookup(local.vmm_domains[each.value.vmm_domain_name], "credential", null) != null
    ? local.vmm_domains[each.value.vmm_domain_name].credential.name
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

