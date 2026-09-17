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

  epg_subnets = merge([
    for epg_key, epg in local.endpoint_groups : {
      for subnet in lookup(epg, "subnets", []) :
      "${epg_key}/${subnet.ip}" => merge(subnet, {
        tenant_name = epg.tenant_name
        ap_name     = epg.ap_name
        epg_name    = epg.name
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

  # Concrete devices (2026-09-15). A logical L4-L7 device with no concrete
  # device is INVALID, not merely incomplete -- measured: it raises
  # "No device found in cluster", "LIf has no relation to CIf" and
  # "invalid abstract graph config", and the service graph never renders.
  # Concrete devices are what make the whole L4-L7 chain valid.
  l4l7_concrete_devices = merge([
    for device_key, device in local.l4l7_devices : {
      for cdev in lookup(device, "concrete_devices", []) :
      "${device_key}/${cdev.name}" => merge(cdev, {
        tenant_name = device.tenant_name
        device_key  = device_key
      })
    }
  ]...)

  l4l7_concrete_interfaces = merge([
    for cdev_key, cdev in local.l4l7_concrete_devices : {
      for cif in lookup(cdev, "interfaces", []) :
      "${cdev_key}/${cif.name}" => merge(cif, {
        tenant_name = cdev.tenant_name
        cdev_key    = cdev_key
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

  # PBR resilience objects (2026-09-15). Tenant-scoped named objects
  # declared alongside devices/graphs/redirect_policies in the
  # aci_l4l7_services Custom Field.
  redirect_health_groups = merge([
    for tn, t in local.tenants : {
      for g in lookup(lookup(t, "services", {}), "health_groups", []) :
      "${tn}/${g.name}" => merge(g, { tenant_name = tn })
    }
  ]...)

  ip_sla_policies = merge([
    for tn, t in local.tenants : {
      for p in lookup(lookup(t, "services", {}), "ip_sla_policies", []) :
      "${tn}/${p.name}" => merge(p, { tenant_name = tn })
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

  # Route control (2026-09-16). A route map in ACI is four objects, not one:
  #
  #   rtctrlSubjP        a named match rule, TENANT scoped
  #   rtctrlMatchRtDest  one prefix inside that match rule
  #   rtctrlProfile      the route map itself, scoped UNDER an L3Out
  #   rtctrlCtxP         one ordered permit/deny entry in the map, pointing
  #                      at a match rule by name
  #
  # Match rules are tenant-scoped on purpose (the provider requires
  # tenant_dn) so one rule can be reused by several route maps.
  match_rules = merge([
    for tn, t in local.tenants : {
      for rule in lookup(t, "match_rules", []) :
      "${tn}/${rule.name}" => merge(rule, { tenant_name = tn })
    }
  ]...)

  match_rule_destinations = merge([
    for rule_key, rule in local.match_rules : {
      for prefix in lookup(rule, "prefixes", []) :
      "${rule_key}/${prefix.ip}" => merge(prefix, { rule_key = rule_key, tenant_name = rule.tenant_name })
    }
  ]...)

  route_control_profiles = merge([
    for l3out_key, l3out in local.l3outs : {
      for profile in lookup(l3out, "route_control_profiles", []) :
      "${l3out_key}/${profile.name}" => merge(profile, {
        l3out_key   = l3out_key
        tenant_name = l3out.tenant_name
        l3out_name  = l3out.l3out_name
      })
    }
  ]...)

  route_control_contexts = merge([
    for profile_key, profile in local.route_control_profiles : {
      for ctx in lookup(profile, "contexts", []) :
      "${profile_key}/${ctx.name}" => merge(ctx, {
        profile_key = profile_key
        tenant_name = profile.tenant_name
      })
    }
  ]...)

  # Optional: bind a named route map to an external EPG for one direction.
  # A profile named `default-export` applies to the whole L3Out on its own; a
  # custom-named one does NOT take effect until something references it, and
  # this is the reference.
  external_epg_route_profiles = merge([
    for epg_key, epg in local.external_epgs : {
      for rp in lookup(epg, "route_control_profiles", []) :
      "${epg_key}/${rp.direction}/${rp.name}" => merge(rp, { epg_key = epg_key })
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

  # External Routed Domains referenced by L3Out `domain:`. Fabric-wide
  # objects (uni/l3dom-*), so deduped across every tenant's L3Outs.
  l3out_domains = toset(compact([for k, l in local.l3outs : lookup(l, "domain", null)]))

  # Explicitly declared L3 domains, which unlike the inferred ones above can
  # carry a VLAN pool. An L3Out's encap VLAN must come from the pool bound to
  # its L3 domain; without this the fabric had NO pool covering vlan-51 even
  # though BGP_L3Out uses it (found 2026-09-16).
  declared_l3_domains = {
    for d in lookup(lookup(local.nac.apic, "access_policies", {}), "l3_domains", []) :
    d.name => d
  }

  # L3Out Logical Interface Profile sub-policies (2026-09-16). Each is a
  # tenant-scoped policy object that an interface profile then REFERENCES.
  # Modelled as five separate flat maps rather than one, because the provider
  # splits them across five resources with two different parent arguments
  # (parent_dn for ND/DPP/custom-QoS, tenant_dn for PIM/IGMP).
  #
  # Why this exists: APIC auto-creates every one of these relations on a new
  # l3extLIfP pointing at uni/tn-common/<kind>-default, so an interface
  # profile has NEVER been unconfigured here -- it has silently run on fabric
  # defaults, with no way to change them. Measured on the live lab 2026-09-16.
  nd_interface_policies = merge([
    for tn, t in local.tenants : {
      for p in lookup(t, "nd_interface_policies", []) :
      "${tn}/${p.name}" => merge(p, { tenant_name = tn })
    }
  ]...)

  dpp_policies = merge([
    for tn, t in local.tenants : {
      for p in lookup(t, "dpp_policies", []) :
      "${tn}/${p.name}" => merge(p, { tenant_name = tn })
    }
  ]...)

  pim_interface_policies = merge([
    for tn, t in local.tenants : {
      for p in lookup(t, "pim_interface_policies", []) :
      "${tn}/${p.name}" => merge(p, { tenant_name = tn })
    }
  ]...)

  igmp_interface_policies = merge([
    for tn, t in local.tenants : {
      for p in lookup(t, "igmp_interface_policies", []) :
      "${tn}/${p.name}" => merge(p, { tenant_name = tn })
    }
  ]...)

  custom_qos_policies = merge([
    for tn, t in local.tenants : {
      for p in lookup(t, "custom_qos_policies", []) :
      "${tn}/${p.name}" => merge(p, { tenant_name = tn })
    }
  ]...)

  ospf_interface_policies = merge([
    for tn, t in local.tenants : {
      for p in lookup(t, "ospf_interface_policies", []) :
      "${tn}/${p.name}" => merge(p, { tenant_name = tn })
    }
  ]...)

  # Inferred OSPF policies for any L3Out referencing an interface policy
  inferred_ospf_policies = merge([
    for l3out_key, l3out in local.l3outs : {
      for o in lookup(l3out, "ospf_interfaces", []) :
      "${l3out.tenant_name}/${o.policy}" => {
        tenant_name  = l3out.tenant_name
        name         = o.policy
        network_type = "broadcast"
      }
      if lookup(o, "policy", null) != null && !contains(keys(local.ospf_interface_policies), "${l3out.tenant_name}/${o.policy}")
    }
  ]...)

  all_ospf_interface_policies = merge(local.ospf_interface_policies, local.inferred_ospf_policies)

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

  # Fabric inventory (2026-09-14) -- the leaf/spine roster sourced from
  # Nautobot DCIM Devices by the generator. Only nodes carrying a serial can
  # be registered: APIC fabric membership is keyed by serial number, which is
  # how a switch that later boots is matched to its intended node ID.
  # Gated on var.register_fabric_membership (default false) -- see that
  # variable's comment for why registering nodes on a switch-less fabric is
  # visibility without value, and costs 3 extra minor faults.
  fabric_inventory_nodes = {
    for n in lookup(lookup(local.nac.apic, "fabric_inventory", {}), "nodes", []) :
    n.serial => n
    if var.register_fabric_membership && lookup(n, "serial", "") != ""
  }

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
      "${pool_name}/${r.from}" => merge(r, {
        vlan_pool_name  = pool_name
        pool_alloc_mode = pool.alloc_mode
      })
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

  # Ported from copilot/aci-platform-comparison (2026-09-08) -- IPG-level
  # CDP/LLDP/link-level/spanning-tree/port-security policies, leaf interface
  # profiles/selectors, EPG-to-domain/static-path bindings, and physical/
  # protocol L3Out node/interface/BGP/OSPF intent.
  #
  # CORRECTED 2026-09-14: this comment used to say "expect `apply` to fail"
  # for the L3Out/BGP/OSPF portion because this simulator has no real
  # `pathep-[...]` interface data. That was an assumption, never tested, and
  # it is wrong. ACI relations are late-binding: the APIC accepts a path
  # attachment naming a switch/port that does not exist, stores it, and
  # leaves it at `state: unformed` / `stateQual: none`. A direct-API probe
  # confirmed this for routed interfaces, sub-interfaces, SVIs, static
  # routes, BGP peers, OSPF, EIGRP and access-port blocks alike; two such
  # path attachments already exist in the live `sales` tenant.
  #
  # So `apply` is expected to SUCCEED here. What never happens is
  # deployment: nothing reaches a switch, so relations stay unformed and no
  # adjacency/route/endpoint is ever observable. Treat a successful apply as
  # "the APIC stored it", never as "the fabric is running it". This scope is
  # still plan-validated only because no apply has been ATTEMPTED -- see
  # Platform-Status-and-Pending-Items.md and ADR-020's 2026-09-14
  # correction.
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

  # XML-equivalent access hierarchy: infraAccPortP/infraHPortS/infraPortBlk.
  access_port_profiles = {
    for p in lookup(lookup(local.nac.apic, "access_policies", {}), "access_port_profiles", []) :
    p.name => p
  }
  access_port_selectors = merge([
    for profile_name, profile in local.access_port_profiles : {
      for s in lookup(profile, "selectors", []) :
      "${profile_name}/${s.name}" => merge(s, { profile_name = profile_name })
    }
  ]...)
  access_port_blocks = merge([
    for selector_key, selector in local.access_port_selectors : {
      for b in lookup(selector, "blocks", []) :
      "${selector_key}/${b.name}" => merge(b, { selector_key = selector_key })
    }
  ]...)
  leaf_profiles = {
    for p in lookup(lookup(local.nac.apic, "access_policies", {}), "leaf_profiles", []) :
    p.name => p
  }
  leaf_selectors = merge([
    for profile_name, profile in local.leaf_profiles : {
      for s in lookup(profile, "selectors", []) :
      "${profile_name}/${s.name}" => merge(s, { profile_name = profile_name })
    }
  ]...)
  leaf_node_blocks = merge([
    for selector_key, selector in local.leaf_selectors : {
      for b in lookup(selector, "node_blocks", []) :
      "${selector_key}/${b.name}" => merge(b, { selector_key = selector_key })
    }
  ]...)

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
      "${profile_key}/${p.name}" => merge(p, { node_profile_key = profile_key, node_profile_name = profile.name, tenant_name = profile.tenant_name, l3out_name = profile.l3out_name, l3out_key = profile.l3out_key })
    }
  ]...)
  l3out_interfaces = merge([
    for ip_key, profile in local.l3out_interface_profiles : {
      for i in lookup(profile, "interfaces", []) :
      "${ip_key}/${i.node_id}/${i.module}/${i.port}" => merge(i, { interface_profile_key = ip_key, interface_profile_name = profile.name, node_profile_key = profile.node_profile_key, node_profile_name = profile.node_profile_name, l3out_key = profile.l3out_key, l3out_name = profile.l3out_name, tenant_name = profile.tenant_name })
    }
  ]...)
  bgp_peers = merge([
    for interface_key, i in local.l3out_interfaces : {
      for p in lookup(i, "bgp_peers", []) :
      "${interface_key}/${p.ip}" => merge(p, {
        interface_key          = interface_key
        interface_profile_key  = i.interface_profile_key
        interface_profile_name = i.interface_profile_name
        l3out_key              = i.l3out_key
        l3out_name             = i.l3out_name
        node_profile_key       = i.node_profile_key
        node_profile_name      = i.node_profile_name
        tenant_name            = i.tenant_name
      })
    }
  ]...)
  ospf_interfaces = merge([
    for l3out_key, l3out in local.l3outs : {
      for o in lookup(l3out, "ospf_interfaces", []) :
      "${l3out_key}/${lookup(o, "interface_key", o.name)}" => merge(o, {
        interface_key = "${l3out_key}/${lookup(o, "interface_key", o.name)}"
        l3out_key     = l3out_key
        tenant_name   = l3out.tenant_name
      })
    }
  ]...)

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

  # ADR-020 Phase G -- Fault Lifecycle Policy / Syslog System Message Policy
  # / Syslog Rate Limit Policy are mandatory fabric-wide singletons under
  # uni/fabric/moncommon (the fabric's Common Monitoring Policy, distinct
  # from monfab-default above), same semantics as ntp/dns/snmp/coop/isis.
  fault_lifecycle_policy = lookup(local.fabric_pod_policies, "fault_lifecycle", {})
  syslog_system_msg      = lookup(local.fabric_pod_policies, "syslog_system_msg", {})
  syslog_rate_limit      = lookup(local.fabric_pod_policies, "syslog_rate_limit", {})

  # ADR-020 Phase F -- RBAC/Security Domains/Local Users. A separate top-
  # level apic.aaa_policies key, not nested under fabric_policies -- see
  # transformer.py's _build_aaa_policies() for why. Both objects are purely
  # additive named objects (no default/mandatory instance), same for_each-
  # flat-map convention as vlan_pools/aeps/pod_policy_groups above.
  aaa_policies     = lookup(local.nac.apic, "aaa_policies", {})
  security_domains = { for d in lookup(local.aaa_policies, "security_domains", []) : d.name => d }
  local_users      = { for u in lookup(local.aaa_policies, "local_users", []) : u.name => u }

  # Flat map of every (user, security domain) binding: "user/domain" => {...}
  user_security_domains = merge([
    for u in lookup(local.aaa_policies, "local_users", []) : {
      for d in lookup(u, "security_domains", []) :
      "${u.name}/${d.name}" => { user_name = u.name, domain_name = d.name }
    }
  ]...)

  # Flat map of every (user, security domain, role) binding:
  # "user/domain/role" => {...}
  user_security_domain_roles = merge([
    for u in lookup(local.aaa_policies, "local_users", []) : merge([
      for d in lookup(u, "security_domains", []) : {
        for r in lookup(d, "roles", []) :
        "${u.name}/${d.name}/${r.name}" => merge(r, { user_name = u.name, domain_name = d.name })
      }
    ]...)
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

  # fvRsBDToOut -- which L3Out(s) this bridge domain's subnets may be
  # advertised through (2026-09-16). Without it a BD subnet marked public is
  # still never advertised: ACI needs both the public scope AND an L3Out
  # association, and neither alone does anything. Taken by NAME; the
  # generator validates each against the L3Outs declared in the same tenant.
  # DN, not name -- the provider rejects a bare name with "planned set element
  # does not correlate with any element in actual" at APPLY time (2026-09-16).
  # Same trap as the L3Out interface-profile policy relations. Resolved through
  # the L3Out resource's own id; the generator validates the name first.
  relation_fv_rs_bd_to_out = lookup(each.value, "l3outs", null) == null ? null : [
    for name in each.value.l3outs : aci_l3_outside.this["${each.value.tenant_name}/${name}"].id
  ]

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

resource "aci_subnet" "epg" {
  for_each = local.epg_subnets

  parent_dn = aci_application_epg.this["${each.value.tenant_name}/${each.value.ap_name}/${each.value.epg_name}"].id
  ip        = each.value.ip
  scope     = lookup(each.value, "scope", ["private"])
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

  filter_dn   = aci_filter.this["${each.value.tenant_name}/${each.value.filter_name}"].id
  name        = each.value.name
  description = lookup(each.value, "description", null)

  # String-valued, null-when-unset attributes -- same lookup(...,null)
  # pattern as VRF/BD attribute depth (item 1). Valid value strings (e.g.
  # ether_t: "ip"/"arp"/...; prot: "tcp"/"udp"/"icmp"/...) are left for
  # Terraform/ACI to validate at plan/apply time, not re-validated here.
  ether_t     = lookup(each.value, "ether_type", null)
  prot        = lookup(each.value, "ip_protocol", null)
  d_from_port = lookup(each.value, "dest_from_port", null)
  d_to_port   = lookup(each.value, "dest_to_port", null)
  s_from_port = lookup(each.value, "source_from_port", null)
  s_to_port   = lookup(each.value, "source_to_port", null)
  arp_opc     = lookup(each.value, "arp_opcode", null)
  icmpv4_t    = lookup(each.value, "icmpv4_type", null)
  icmpv6_t    = lookup(each.value, "icmpv6_type", null)
  match_dscp  = lookup(each.value, "match_dscp", null)
  tcp_rules   = lookup(each.value, "tcp_rules", null)

  # APIC represents these as "yes"/"no", not booleans.
  stateful      = try(each.value.stateful ? "yes" : "no", null)
  apply_to_frag = try(each.value.apply_to_fragments ? "yes" : "no", null)
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
  description = lookup(each.value, "description", null)
  prio        = lookup(each.value, "priority", null)
  target_dscp = lookup(each.value, "target_dscp", null)

  # APIC represents these as "yes"/"no", not booleans. rev_flt_ports only
  # applies when the subject is bidirectional.
  apply_both_directions = try(each.value.apply_both_directions ? "yes" : "no", null)
  rev_flt_ports         = try(each.value.reverse_filter_ports ? "yes" : "no", null)

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

  # A VIRTUAL device binds to a VMM Domain; a PHYSICAL device binds to a
  # Physical Domain through a DIFFERENT attribute entirely, and the provider
  # makes it mandatory -- `terraform plan` fails outright with
  # "relation_vns_rs_al_dev_to_phys_dom_p is required when device_type is
  # PHYSICAL". Until 2026-09-15 only the VMM relation existed here, so a
  # physical service device could not be created at all.
  dynamic "relation_vns_rs_al_dev_to_dom_p" {
    for_each = lookup(each.value, "vmm_domain", null) != null ? [each.value.vmm_domain] : []

    content {
      domain_dn = aci_vmm_domain.this[relation_vns_rs_al_dev_to_dom_p.value].id
    }
  }

  # Built as a literal DN rather than referencing aci_physical_domain.this[
  # ...].id, because the provider validates this attribute at PLAN time and
  # a reference to a not-yet-created resource is unknown then -- the provider
  # reads unknown as unset and fails with "is required when device_type is
  # PHYSICAL" even though it IS configured. physDomP DNs are deterministic
  # (`uni/phys-<name>`, confirmed against this APIC), so the literal is safe;
  # depends_on restores the ordering the lost reference would have given.
  relation_vns_rs_al_dev_to_phys_dom_p = (
    lookup(each.value, "physical_domain", null) != null
    ? "uni/phys-${each.value.physical_domain}"
    : null
  )

  depends_on = [aci_physical_domain.this, aci_vmm_domain.this]
}

resource "aci_l4_l7_logical_interface" "this" {
  for_each = local.l4l7_logical_interfaces

  l4_l7_device_dn = aci_l4_l7_device.this["${each.value.tenant_name}/${each.value.device_name}"].id
  name            = each.value.name
  description     = lookup(each.value, "description", null)

  # Binding the logical interface to its concrete interface(s) is what
  # clears "LIf has no relation to CIf" / "LIf has an invalid CIf". Without
  # it the device is invalid however complete the rest of the graph looks.
  # Referenced by "<concrete_device>/<interface>" so one logical interface
  # can front several concrete ones (an HA pair).
  relation_vns_rs_c_if_att_n = [
    for ref in lookup(each.value, "concrete_interfaces", []) :
    aci_concrete_interface.this["${each.value.tenant_name}/${each.value.device_name}/${ref}"].id
  ]

  # Left unset by default. For an UNMANAGED device APIC allocates the encap
  # from the domain's VLAN pool; pinning one that is not in the pool raises
  # "Configuration is invalid due to invalid encapsulation on LIf".
  encap = lookup(each.value, "encap", null)
}

# vnsCDev -- the actual appliance behind the logical device.
resource "aci_concrete_device" "this" {
  for_each = local.l4l7_concrete_devices

  l4_l7_device_dn = aci_l4_l7_device.this[each.value.device_key].id
  name            = each.value.name
  description     = lookup(each.value, "description", null)

  # vm_name/vmm_controller_dn apply to a VIRTUAL device discovered from
  # vCenter; a PHYSICAL concrete device is identified by its interfaces'
  # paths instead, so both stay null here.
  vm_name           = lookup(each.value, "vm_name", null)
  vmm_controller_dn = lookup(each.value, "vmm_controller_dn", null)
}

# vnsCIf -- a physical port on the appliance, attached to a leaf port.
#
# The path attachment resolves to `pathep-[...]` and therefore stays
# `state: unformed` on a fabric with no switches -- measured 2026-09-15.
# Critically it raises NO fault of its own, so modelling concrete devices
# is still worth doing here: it clears every structural L4-L7 fault even
# though the port itself can never come up on this simulator.
# EVIDENCE: live-verified apply + destroy, but the PHYSICAL path bottoms
# out at 6 APIC faults on this fabric and cannot reach zero -- a concrete
# device is an appliance plugged into a leaf port, and there are no
# switches. Measured both with the path attachment present (unformed) and
# omitted entirely; both give 6. Read any count ABOVE 6 as a regression.
# The virtual (VMM) path has no such floor -- see l4l7-vmm-virtual.yaml.
resource "aci_concrete_interface" "this" {
  for_each = local.l4l7_concrete_interfaces

  concrete_device_dn = aci_concrete_device.this[each.value.cdev_key].id
  name               = each.value.name
  vnic_name          = lookup(each.value, "vnic_name", null)
  encap              = lookup(each.value, "encap", null)

  # NOTE: relation_vns_rs_c_if_path_att is deliberately NOT set here -- see
  # aci_rest_managed.concrete_interface_path below.
}

# vnsRsCIfPathAtt -- the concrete interface's attachment to a leaf port.
#
# Set through aci_rest_managed rather than aci_concrete_interface's own
# `relation_vns_rs_c_if_path_att` attribute because the typed resource
# PRE-VALIDATES that the target DN resolves and fails the apply outright
# with "Relation target dn topology/pod-1/paths-101/pathep-[eth1/30] not
# found" on a fabric with no switches.
#
# That is a PROVIDER check, not an APIC rule -- verified 2026-09-15 by
# POSTing the identical object over raw REST, which the APIC accepted and
# stored with `state: unformed`, exactly like every other pathep- relation
# in this module. aci_rest_managed issues the same raw POST, so it behaves
# the way the rest of this file already does: configuration is stored,
# the relation forms if and when real hardware appears.
#
# Ordinary destroy behaviour is correct -- this is an additive relation on
# an object this module owns, not a mandatory system singleton, so no
# content_on_destroy is needed (contrast the Phase C/G resources).
resource "aci_rest_managed" "concrete_interface_path" {
  for_each = { for k, i in local.l4l7_concrete_interfaces : k => i if lookup(i, "node_id", null) != null }

  dn         = "${aci_concrete_interface.this[each.key].id}/rsCIfPathAtt"
  class_name = "vnsRsCIfPathAtt"
  content = {
    tDn = "topology/pod-${lookup(each.value, "pod_id", 1)}/paths-${each.value.node_id}/pathep-[eth${each.value.module}/${each.value.port}]"
  }
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

# vnsAbsNode -- the service FUNCTION node inside the graph.
#
# aci_l4_l7_service_graph_template creates ONLY the graph shell and its two
# terminal connectors (confirmed via `terraform providers schema -json`: that
# resource has no nested blocks and no node attributes). Without this
# resource the graph contains terminals and nothing in between, so a Contract
# attaching to it has no service node to redirect through and the graph
# cannot render -- APIC accepts the incomplete graph silently, which is why
# this went unnoticed.
#
# `name` MUST equal aci_logical_device_context.node_name_or_lbl below, or the
# device context binds to a node that does not exist.
#
# routing_mode = "Redirect" is what makes this a PBR node rather than a plain
# go-to firewall insertion; it is set whenever either arm of the graph carries
# a redirect policy.
resource "aci_function_node" "this" {
  for_each = local.service_graphs

  l4_l7_service_graph_template_dn = aci_l4_l7_service_graph_template.this[each.key].id
  name                            = lookup(each.value, "node_name", "node-1")

  # Bind the node to the logical device that actually performs the function.
  relation_vns_rs_node_to_l_dev = aci_l4_l7_device.this["${each.value.tenant_name}/${each.value.device}"].id

  func_type = lookup(each.value, "function_type", "GoTo")
  managed   = try(each.value.managed ? "yes" : "no", "no")
  routing_mode = anytrue([
    for side in ["consumer", "provider"] :
    lookup(lookup(each.value, side, {}), "redirect_policy", null) != null
  ]) ? "Redirect" : null

  # Connector names must match the device's own logical interface names so
  # the node's consumer/provider connectors resolve to real interfaces.
  l4_l7_device_interface_consumer_name = try(each.value.consumer.logical_interface, null)
  l4_l7_device_interface_provider_name = try(each.value.provider.logical_interface, null)

  description = lookup(each.value, "description", null)
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
    aci_function_node.this,
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

# PBR resilience objects. A redirect policy with a single destination and no
# health tracking fails closed the moment that destination dies -- traffic is
# redirected into a black hole. A health group plus an IP SLA monitoring
# policy is what lets APIC detect the failure and bypass or drop per the
# configured threshold action.
resource "aci_l4_l7_redirect_health_group" "this" {
  for_each = local.redirect_health_groups

  tenant_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  description = lookup(each.value, "description", null)
}

resource "aci_ip_sla_monitoring_policy" "this" {
  for_each = local.ip_sla_policies

  tenant_dn             = aci_tenant.this[each.value.tenant_name].id
  name                  = each.value.name
  sla_type              = lookup(each.value, "sla_type", "icmp")
  sla_frequency         = lookup(each.value, "frequency", null)
  sla_port              = lookup(each.value, "port", null)
  sla_detect_multiplier = lookup(each.value, "detect_multiplier", null)
  timeout               = lookup(each.value, "timeout", null)
  threshold             = lookup(each.value, "threshold", null)
  description           = lookup(each.value, "description", null)
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

  # Threshold/hashing behaviour. Left unmanaged (null) when unset, same
  # lookup(..., null) convention as everywhere else in this file.
  hashing_algorithm     = lookup(each.value, "hashing_algorithm", null)
  threshold_enable      = try(each.value.threshold_enable ? "yes" : "no", null)
  min_threshold_percent = lookup(each.value, "min_threshold_percent", null)
  max_threshold_percent = lookup(each.value, "max_threshold_percent", null)
  threshold_down_action = lookup(each.value, "threshold_down_action", null)

  relation_vns_rs_ipsla_monitoring_pol = (
    lookup(each.value, "ip_sla_policy", null) != null
    ? aci_ip_sla_monitoring_policy.this["${each.value.tenant_name}/${each.value.ip_sla_policy}"].id
    : null
  )
}

resource "aci_destination_of_redirected_traffic" "this" {
  for_each = local.redirect_destinations

  service_redirect_policy_dn = aci_service_redirect_policy.this["${each.value.tenant_name}/${each.value.policy_name}"].id
  ip                         = each.value.ip
  mac                        = lookup(each.value, "mac", null)
  description                = lookup(each.value, "description", null)

  ip2       = lookup(each.value, "second_ip", null)
  dest_name = lookup(each.value, "dest_name", null)
  pod_id    = lookup(each.value, "pod_id", null)

  # Binding a destination to a health group is what actually arms tracking
  # for it -- an IP SLA policy on the redirect policy alone monitors nothing.
  relation_vns_rs_redirect_health_group = (
    lookup(each.value, "health_group", null) != null
    ? aci_l4_l7_redirect_health_group.this["${each.value.tenant_name}/${each.value.health_group}"].id
    : null
  )
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
resource "aci_l3_domain_profile" "this" {
  # Union of domains named by an L3Out and domains declared explicitly, so a
  # domain works whether or not anyone bothered to declare it separately.
  for_each = toset(concat(tolist(local.l3out_domains), keys(local.declared_l3_domains)))
  name     = each.value

  # VLAN pool relation takes a DN, and the pool's allocation mode is part of
  # the pool's own DN, so it cannot be built from the name alone.
  relation_infra_rs_vlan_ns = lookup(local.declared_l3_domains, each.value, null) == null ? null : (
    lookup(local.declared_l3_domains[each.value], "vlan_pool", null) == null ? null :
    aci_vlan_pool.this[local.declared_l3_domains[each.value].vlan_pool].id
  )
}

resource "aci_l3_outside" "this" {
  for_each = local.l3outs

  tenant_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  description = lookup(each.value, "description", null)

  # Required relation to the L3Out's VRF -- referencing the VRF's own .id
  # (rather than the raw YAML string) creates the implicit dependency edge,
  # same pattern as relation_to_vrf/relation_to_bridge_domain above.
  relation_l3ext_rs_ectx = aci_vrf.this["${each.value.tenant_name}/${each.value.vrf}"].id

  relation_l3ext_rs_l3_dom_att = (
    lookup(each.value, "domain", null) != null
    ? aci_l3_domain_profile.this[each.value.domain].id
    : null
  )
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

# ---------------------------------------------------------------------------
# Route control / route maps (2026-09-16).
#
# Built for the transit-routing lab, where the requirement was to stop using
# per-subnet "Export Route Control Subnet" flags and drive export from a route
# map instead: permit one prefix, deny a bridge-domain subnet, and let ACI's
# implicit deny drop everything else.
# ---------------------------------------------------------------------------

resource "aci_match_rule" "this" {
  for_each = local.match_rules

  tenant_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  description = lookup(each.value, "description", null)
}

resource "aci_match_route_destination_rule" "this" {
  for_each = local.match_rule_destinations

  match_rule_dn = aci_match_rule.this[each.value.rule_key].id
  ip            = each.value.ip
  description   = lookup(each.value, "description", null)

  # aggregate is APIC's "Aggregate" checkbox; the two mask bounds are the
  # ge/le of a prefix-list entry. All three default to off/0, matching the
  # APIC UI defaults shown in the lab screenshots.
  # The provider takes "yes"/"no" here, not a bool -- same convention as the
  # bridge-domain flags above. A raw false fails the apply with
  # 'expected aggregate to be one of ["no" "yes"], got false' (2026-09-16),
  # and only at apply time: the plan renders the bool happily.
  aggregate         = try(each.value.aggregate ? "yes" : "no", null)
  greater_than_mask = lookup(each.value, "greater_than_mask", null)
  less_than_mask    = lookup(each.value, "less_than_mask", null)
}

resource "aci_route_control_profile" "this" {
  for_each = local.route_control_profiles

  parent_dn   = aci_l3_outside.this[each.value.l3out_key].id
  name        = each.value.name
  description = lookup(each.value, "description", null)

  # "global"     = Match Routing Policy Only  (the screenshots' setting)
  # "combinable" = Match Prefix AND Routing Policy
  route_control_profile_type = lookup(each.value, "type", "global")
}

resource "aci_route_control_context" "this" {
  for_each = local.route_control_contexts

  route_control_profile_dn = aci_route_control_profile.this[each.value.profile_key].id
  name                     = each.value.name
  action                   = lookup(each.value, "action", "permit")
  order                    = lookup(each.value, "order", null)
  description              = lookup(each.value, "description", null)

  # DN, not name. The schema gives no hint either way and the plan renders a
  # bare name happily; the APPLY then fails with "Relation target dn
  # match-permit-prefix-out not found" (measured 2026-09-16). Match rules are
  # tenant-scoped, so the DN comes from the match rule resource in this
  # context's own tenant.
  relation_rtctrl_rs_ctx_p_to_subj_p = lookup(each.value, "match_rule", null) == null ? null : [
    aci_match_rule.this["${each.value.tenant_name}/${each.value.match_rule}"].id
  ]

  set_rule = lookup(each.value, "set_rule", null)

  depends_on = [aci_match_rule.this]
}

# Binds a named route map to an external EPG for one direction. Only needed
# for a custom-named profile; `default-export` applies on its own.
resource "aci_relation_from_external_epg_to_route_control_profile" "this" {
  for_each = local.external_epg_route_profiles

  parent_dn                  = aci_external_network_instance_profile.this[each.value.epg_key].id
  route_control_profile_name = each.value.name
  direction                  = each.value.direction

  depends_on = [aci_route_control_profile.this]
}

resource "aci_logical_interface_profile" "this" {
  for_each                = local.l3out_interface_profiles
  logical_node_profile_dn = aci_logical_node_profile.this[each.value.node_profile_key].id
  name                    = each.value.name
  description             = lookup(each.value, "description", null)

  # QoS class for traffic on this profile's interfaces (l3extLIfP.prio).
  # Left null -> APIC's own "unspecified", which is what every profile this
  # platform has created to date has carried.
  prio = lookup(each.value, "qos_priority", null)

  # Policy relations. Each takes the policy's NAME, not a DN -- the
  # underlying MOs use tnXxxName attributes.
  #
  # These relations take a full DN, NOT a policy name -- measured 2026-09-16
  # by applying name values and getting "Relation target dn ND_Strict not
  # found" for all seven at once. The provider validates the target resolves
  # at APPLY time (plan renders whatever string you give it, so a plan proves
  # nothing here). The same run disproved a second assumption: the literal
  # `default` is not accepted either. To inherit APIC's built-in default,
  # OMIT the field entirely and let APIC populate the relation itself.
  #
  # Resolved through each policy resource's own `.id` rather than by building
  # "uni/tn-<t>/<prefix>-<name>" strings, because the prefixes are NOT
  # consistent: ndifpol / qosdpppol / pimifpol / qoscustom are lowercase but
  # igmpIfPol is camelCase. Hand-built DNs would work for four of the five
  # and silently fail on IGMP.
  #
  # A value already starting with "uni/" is passed through untouched, so a
  # profile can still point at a policy this module does not manage. Anything
  # else must name a policy declared in the SAME tenant; the generator
  # enforces that ahead of Terraform so a typo fails at generate time with a
  # message naming the tenant, not 20 minutes into an apply.
  relation_l3ext_rs_nd_if_pol = lookup(each.value, "nd_interface_policy", null) == null ? null : (
    startswith(each.value.nd_interface_policy, "uni/") ? each.value.nd_interface_policy :
    aci_neighbor_discovery_interface_policy.this["${each.value.tenant_name}/${each.value.nd_interface_policy}"].id
  )
  relation_l3ext_rs_ingress_qos_dpp_pol = lookup(each.value, "ingress_dpp_policy", null) == null ? null : (
    startswith(each.value.ingress_dpp_policy, "uni/") ? each.value.ingress_dpp_policy :
    aci_data_plane_policing_policy.this["${each.value.tenant_name}/${each.value.ingress_dpp_policy}"].id
  )
  relation_l3ext_rs_egress_qos_dpp_pol = lookup(each.value, "egress_dpp_policy", null) == null ? null : (
    startswith(each.value.egress_dpp_policy, "uni/") ? each.value.egress_dpp_policy :
    aci_data_plane_policing_policy.this["${each.value.tenant_name}/${each.value.egress_dpp_policy}"].id
  )
  relation_l3ext_rs_pim_ip_if_pol = lookup(each.value, "pim_interface_policy", null) == null ? null : (
    startswith(each.value.pim_interface_policy, "uni/") ? each.value.pim_interface_policy :
    aci_pim_interface_policy.this["${each.value.tenant_name}/${each.value.pim_interface_policy}"].id
  )
  relation_l3ext_rs_pim_ipv6_if_pol = lookup(each.value, "pim_v6_interface_policy", null) == null ? null : (
    startswith(each.value.pim_v6_interface_policy, "uni/") ? each.value.pim_v6_interface_policy :
    aci_pim_interface_policy.this["${each.value.tenant_name}/${each.value.pim_v6_interface_policy}"].id
  )
  relation_l3ext_rs_igmp_if_pol = lookup(each.value, "igmp_interface_policy", null) == null ? null : (
    startswith(each.value.igmp_interface_policy, "uni/") ? each.value.igmp_interface_policy :
    aci_igmp_interface_policy.this["${each.value.tenant_name}/${each.value.igmp_interface_policy}"].id
  )
  relation_l3ext_rs_l_if_p_cust_qos_pol = lookup(each.value, "custom_qos_policy", null) == null ? null : (
    startswith(each.value.custom_qos_policy, "uni/") ? each.value.custom_qos_policy :
    aci_custom_qos_policy.this["${each.value.tenant_name}/${each.value.custom_qos_policy}"].id
  )
}

# ---------------------------------------------------------------------------
# L3Out Logical Interface Profile sub-policies (2026-09-16).
#
# ARP is deliberately absent: l3extLIfP carries a relation_l3ext_rs_arp_if_pol
# attribute, but the installed provider has NO resource that can CREATE an
# arpIfPol (confirmed against `terraform providers schema -json`: zero
# resources match /arp/). Supporting the relation without the policy would
# mean accepting a name nothing can validate or produce.
#
# NetFlow is absent for the opposite reason: aci_netflow_monitor_policy DOES
# exist, but aci_logical_interface_profile has no attribute for the
# l3extRsLIfPToNetflowMonitorPol relation, so binding one needs
# aci_rest_managed. Tracked as its own increment.
# ---------------------------------------------------------------------------

resource "aci_neighbor_discovery_interface_policy" "this" {
  for_each = local.nd_interface_policies

  parent_dn                      = aci_tenant.this[each.value.tenant_name].id
  name                           = each.value.name
  description                    = lookup(each.value, "description", null)
  hop_limit                      = lookup(each.value, "hop_limit", null)
  mtu                            = lookup(each.value, "mtu", null)
  retransmit_timer               = lookup(each.value, "retransmit_timer", null)
  reachable_time                 = lookup(each.value, "reachable_time", null)
  neighbor_solicitation_interval = lookup(each.value, "neighbor_solicitation_interval", null)
  neighbor_solicitation_retries  = lookup(each.value, "neighbor_solicitation_retries", null)
  nud_retry_base                 = lookup(each.value, "nud_retry_base", null)
  nud_retry_interval             = lookup(each.value, "nud_retry_interval", null)
  nud_retry_max_attempts         = lookup(each.value, "nud_retry_max_attempts", null)
  router_advertisement_interval  = lookup(each.value, "router_advertisement_interval", null)
  router_advertisement_lifetime  = lookup(each.value, "router_advertisement_lifetime", null)
  controller_state               = lookup(each.value, "controller_state", null)
}

resource "aci_data_plane_policing_policy" "this" {
  for_each = local.dpp_policies

  parent_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  description = lookup(each.value, "description", null)
  admin_state = lookup(each.value, "admin_state", null)
  type        = lookup(each.value, "type", null)
  mode        = lookup(each.value, "mode", null)

  # Rate/burst are the whole point of a policer; the rest is shaping detail.
  # Units are separate attributes in this provider, not value suffixes.
  rate                 = lookup(each.value, "rate", null)
  rate_unit            = lookup(each.value, "rate_unit", null)
  burst                = lookup(each.value, "burst", null)
  burst_unit           = lookup(each.value, "burst_unit", null)
  peak_rate            = lookup(each.value, "peak_rate", null)
  peak_rate_unit       = lookup(each.value, "peak_rate_unit", null)
  excessive_burst      = lookup(each.value, "excessive_burst", null)
  excessive_burst_unit = lookup(each.value, "excessive_burst_unit", null)

  conform_action    = lookup(each.value, "conform_action", null)
  conform_mark_cos  = lookup(each.value, "conform_mark_cos", null)
  conform_mark_dscp = lookup(each.value, "conform_mark_dscp", null)
  exceed_action     = lookup(each.value, "exceed_action", null)
  exceed_mark_cos   = lookup(each.value, "exceed_mark_cos", null)
  exceed_mark_dscp  = lookup(each.value, "exceed_mark_dscp", null)
  violate_action    = lookup(each.value, "violate_action", null)
  violate_mark_cos  = lookup(each.value, "violate_mark_cos", null)
  violate_mark_dscp = lookup(each.value, "violate_mark_dscp", null)
  sharing_mode      = lookup(each.value, "sharing_mode", null)
}

# NOTE: PIM and IGMP take `tenant_dn`, not `parent_dn` like the three others --
# a real inconsistency in the provider, not a transcription slip here.
resource "aci_pim_interface_policy" "this" {
  for_each = local.pim_interface_policies

  tenant_dn                  = aci_tenant.this[each.value.tenant_name].id
  name                       = each.value.name
  description                = lookup(each.value, "description", null)
  control_state              = lookup(each.value, "control_state", null)
  designated_router_delay    = lookup(each.value, "designated_router_delay", null)
  designated_router_priority = lookup(each.value, "designated_router_priority", null)
  hello_interval             = lookup(each.value, "hello_interval", null)
  join_prune_interval        = lookup(each.value, "join_prune_interval", null)

  # auth_key is deliberately NOT sourced from the YAML -- it is a shared
  # secret, and this module's rule is that secrets arrive as sensitive
  # Terraform variables, never through Nautobot or committed YAML (the same
  # rule that keeps OSPF MD5 keys out of create_ospf_interface_policy).
  auth_type = lookup(each.value, "auth_type", null)
}

resource "aci_igmp_interface_policy" "this" {
  for_each = local.igmp_interface_policies

  tenant_dn                 = aci_tenant.this[each.value.tenant_name].id
  name                      = each.value.name
  description               = lookup(each.value, "description", null)
  control                   = lookup(each.value, "control", null)
  group_timeout             = lookup(each.value, "group_timeout", null)
  last_member_count         = lookup(each.value, "last_member_count", null)
  last_member_response_time = lookup(each.value, "last_member_response_time", null)
  querier_timeout           = lookup(each.value, "querier_timeout", null)
  query_interval            = lookup(each.value, "query_interval", null)
  response_interval         = lookup(each.value, "response_interval", null)
  robustness_variable       = lookup(each.value, "robustness_variable", null)
  startup_query_count       = lookup(each.value, "startup_query_count", null)
  startup_query_interval    = lookup(each.value, "startup_query_interval", null)
  version                   = lookup(each.value, "version", null)
}

resource "aci_custom_qos_policy" "this" {
  for_each = local.custom_qos_policies

  parent_dn   = aci_tenant.this[each.value.tenant_name].id
  name        = each.value.name
  description = lookup(each.value, "description", null)

  # Both are lists of objects passed straight through -- dot1p_classifiers
  # entries carry from/to/priority/target/target_cos, dscp_to_priority_maps
  # the same shape over DSCP ranges.
  dot1p_classifiers     = lookup(each.value, "dot1p_classifiers", null)
  dscp_to_priority_maps = lookup(each.value, "dscp_to_priority_maps", null)
}

# EVIDENCE: live-verified 2026-09-15 (apply, no destroy). The expectation
# recorded here previously -- that the APIC accepts a pathep- DN naming a
# switch that does not exist -- is now measured rather than reasoned: the
# 93-resource `sales` apply created 2 x l3extRsPathL3OutAtt, both sitting at
# state: unformed, and check_apic_faults.py reported ZERO new faults for
# them. No destroy has been run for this scope, so it is not apply+destroy
# proven. A session still cannot establish -- that is a dataplane limit.
resource "aci_l3out_path_attachment" "this" {
  for_each                     = local.l3out_interfaces
  logical_interface_profile_dn = aci_logical_interface_profile.this[each.value.interface_profile_key].id
  if_inst_t                    = try(each.value.svi, false) ? "ext-svi" : (lookup(each.value, "vlan", null) != null ? "sub-interface" : "l3-port")
  target_dn                    = "topology/pod-${each.value.pod_id}/paths-${each.value.node_id}/pathep-[eth${each.value.module}/${each.value.port}]"
  addr                         = lookup(each.value, "ip", null)
  encap                        = lookup(each.value, "vlan", null) != null ? "vlan-${each.value.vlan}" : null
  mode                         = lookup(each.value, "mode", null)
  mtu                          = lookup(each.value, "mtu", null)
}

resource "aci_l3out_floating_svi" "this" {
  for_each                     = { for k, i in local.l3out_interfaces : k => i if try(i.floating, false) }
  logical_interface_profile_dn = aci_logical_interface_profile.this[each.value.interface_profile_key].id
  if_inst_t                    = "ext-svi"
  node_dn                      = "topology/pod-${each.value.pod_id}/node-${each.value.node_id}"
  encap                        = "vlan-${each.value.vlan}"
  addr                         = lookup(each.value, "ip", null)
  mode                         = lookup(each.value, "mode", null)
  mtu                          = lookup(each.value, "mtu", null)
}

# bgpExtP -- enables the BGP address family on the L3Out itself. Without it
# APIC ignores every bgpPeerP underneath, so peers stay administratively
# present but never form a session.
resource "aci_l3out_bgp_external_policy" "this" {
  for_each      = local.l3out_bgp_policies
  l3_outside_dn = aci_l3_outside.this[each.key].id
}

resource "aci_l3out_bgp_protocol_profile" "this" {
  for_each                = local.l3out_bgp_policies
  logical_node_profile_dn = one([for k, p in local.l3out_node_profiles : aci_logical_node_profile.this[k].id if startswith(k, "${each.key}/")])
}

# EVIDENCE: plan-verified only -- see aci_l3out_path_attachment above. No
# BGP session can ever establish on this fabric (no switches), so only the
# configuration half is verifiable here.
resource "aci_bgp_peer_connectivity_profile" "this" {
  for_each            = local.bgp_peers
  parent_dn           = aci_l3out_path_attachment.this[each.value.interface_key].id
  addr                = each.value.ip
  as_number           = tostring(each.value.remote_as)
  local_asn           = tostring(each.value.local_as)
  admin_state         = try(each.value.admin_state ? "enabled" : "disabled", "enabled")
  ttl                 = tostring(lookup(each.value, "ttl", 1))
  weight              = tostring(lookup(each.value, "weight", 0))
  allowed_self_as_cnt = tostring(lookup(each.value, "allowed_self_as_count", 0))
}

resource "aci_l3out_ospf_external_policy" "this" {
  for_each      = local.l3out_ospf_policies
  l3_outside_dn = aci_l3_outside.this[each.key].id
  area_id       = try(lookup(lookup(each.value, "ospf_interfaces", [])[0], "area", "0.0.0.0"), "0.0.0.0")
  area_type     = try(lookup(lookup(each.value, "ospf_interfaces", [])[0], "area_type", "regular"), "regular")
}

resource "aci_l3out_ospf_interface_profile" "this" {
  for_each                     = local.ospf_interfaces
  logical_interface_profile_dn = aci_logical_interface_profile.this[each.value.interface_key].id
  relation_ospf_rs_if_pol      = lookup(each.value, "policy", null) != null ? try(aci_ospf_interface_policy.this["${each.value.tenant_name}/${each.value.policy}"].id, null) : null
  auth_type                    = lookup(each.value, "authentication_type", null)
  auth_key_id                  = lookup(each.value, "authentication_key_id", null)
}

resource "aci_ospf_interface_policy" "this" {
  for_each = local.all_ospf_interface_policies

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
# EVIDENCE: plan-verified only -- apply has never been run for VRF route
# leaking in this repo's history. It has no dependency on switch hardware,
# so a clean apply is expected; verify before claiming it.
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
# Fabric Membership -- register each Nautobot-modeled leaf/spine with the APIC
#
# This is what makes the switches visible in the APIC GUI under
# Fabric > Inventory > Fabric Membership, and what populates `fabricNode`.
# Without it, Nautobot's roster and the APIC's roster are simply two
# unrelated lists.
#
# Keyed by SERIAL, not node ID, because that is how ACI itself works: you
# pre-register a serial with its intended node ID/name/role, and when a
# switch with that serial boots and is discovered, the APIC matches it to
# this entry and commissions it as that node. Pre-registering before the
# hardware exists is the normal ACI workflow, not a workaround.
#
# Confirmed live (2026-09-14): posting a fabricNodeIdentP with only a serial
# creates a real `fabricNode` row with no hardware present. What it does NOT
# do is make the node functional -- `l1PhysIf`/`fabricPathEp` stay empty and
# the node sits at `fabricSt: unknown` until a real switch with that serial
# actually checks in. So this delivers an accurate, declarative node roster
# in the APIC; it does not conjure a working fabric.
#
# No `content_on_destroy`: unlike Phase C/G's mandatory system singletons,
# these are purely additive named objects with no default instance, so
# aci_rest_managed's ordinary "delete the DN" destroy behaviour is correct.
# Removing a switch from Nautobot should de-register it from the APIC.
# ---------------------------------------------------------------------------
resource "aci_rest_managed" "fabric_node_identity" {
  for_each = local.fabric_inventory_nodes

  dn         = "uni/controller/nodeidentpol/nodep-${each.value.serial}"
  class_name = "fabricNodeIdentP"
  content = {
    serial = each.value.serial
    nodeId = tostring(each.value.node_id)
    name   = each.value.name
    role   = each.value.role
    podId  = tostring(lookup(each.value, "pod_id", 1))
  }
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
  from         = "vlan-${each.value.from}"
  to           = "vlan-${each.value.to}"
  alloc_mode   = lookup(each.value, "alloc_mode", "inherit")
  role         = lookup(each.value, "role", "external")
  description  = lookup(each.value, "description", null)
}

# ---------------------------------------------------------------------------
# Access Policies: Physical Domains, AEPs, Leaf Interface Policy Groups
# (ADR-020 Phase B, logical-only MVP)
#
# These three resources model the fabric-wide policy OBJECTS themselves
# (VLAN Pool, Physical Domain, AEP, Leaf Interface Policy Group + their
# relations to each other) and stop short of binding any of them to a leaf
# port. That was an MVP scope choice for Phase B; the physical hierarchy is
# implemented further down this file by Phase J's `xml_compatible` resources.
#
# CORRECTED 2026-09-14: the original comment here justified the exclusion by
# saying physical port binding is impossible because "this ACI simulator has
# zero real interface data available at all". The premise is true (`l1PhysIf`
# totalCount 0, `fabricNode` totalCount 1 -- the controller alone) but the
# conclusion is not. ACI relations are late-binding: a probe created a full
# infraAccPortP/infraHPortS/infraPortBlk hierarchy naming ports on a
# non-existent leaf and the APIC accepted it. The live fabric already carries
# two such profiles raising fault F1299 "Node Not Leaf For Infra Policies" --
# stored, never deployed. Configuration works; deployment and operational
# verification do not. See ADR-020's 2026-09-14 correction.
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
  # An AEP can front a physical domain, an L3 domain, or both. Until
  # 2026-09-16 only physical resolved, so an AEP could never be attached to an
  # L3 domain -- which is what an L3Out's interface needs. A plain string stays
  # a physical domain for backwards compatibility; {name, type} selects.
  relation_to_domains = [
    for d in lookup(each.value, "domains", []) :
    {
      target_dn = try(d.type, "physical") == "l3" ? aci_l3_domain_profile.this[try(d.name, d)].id : aci_physical_domain.this[try(d.name, d)].id
    }
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

resource "aci_leaf_interface_profile" "xml_compatible" {
  for_each    = local.access_port_profiles
  name        = each.value.name
  description = lookup(each.value, "description", null)
}

resource "aci_access_port_selector" "xml_compatible" {
  for_each = local.access_port_selectors

  leaf_interface_profile_dn = aci_leaf_interface_profile.xml_compatible[each.value.profile_name].id
  name                      = each.value.name
  port_selector_type        = lookup(each.value, "selector_type", "range")
  relation_to_leaf_access_port_policy_group = {
    target_dn = aci_leaf_access_port_policy_group.this[each.value.policy_group].id
  }
}

resource "aci_access_port_block" "xml_compatible" {
  for_each = local.access_port_blocks

  access_port_selector_dn = aci_access_port_selector.xml_compatible[each.value.selector_key].id
  name                    = each.value.name
  from_card               = tostring(each.value.from_card)
  to_card                 = tostring(lookup(each.value, "to_card", each.value.from_card))
  from_port               = tostring(each.value.from_port)
  to_port                 = tostring(lookup(each.value, "to_port", each.value.from_port))
}

resource "aci_leaf_profile" "xml_compatible" {
  for_each = local.leaf_profiles

  name = each.value.name
  relation_infra_rs_acc_port_p = [
    for p in lookup(each.value, "access_port_profiles", []) :
    aci_leaf_interface_profile.xml_compatible[p].id
  ]
}

resource "aci_leaf_selector" "xml_compatible" {
  for_each = local.leaf_selectors

  leaf_profile_dn         = aci_leaf_profile.xml_compatible[each.value.profile_name].id
  name                    = each.value.name
  switch_association_type = lookup(each.value, "selector_type", "range")
}

resource "aci_node_block" "xml_compatible" {
  for_each = local.leaf_node_blocks

  switch_association_dn = aci_leaf_selector.xml_compatible[each.value.selector_key].id
  name                  = each.value.name
  from_                 = tostring(each.value.from_node)
  to_                   = tostring(lookup(each.value, "to_node", each.value.from_node))
}

resource "aci_access_port_selector" "this" {
  for_each                                  = local.interface_selectors
  leaf_interface_profile_dn                 = aci_leaf_interface_profile.this[each.value.leaf_interface_profile].id
  name                                      = each.value.name
  port_selector_type                        = lookup(each.value, "port_selector_type", "range")
  relation_to_leaf_access_port_policy_group = { target_dn = aci_leaf_access_port_policy_group.this[each.value.policy_group].id }
}

resource "aci_epg_to_static_path" "this" {
  for_each           = local.static_path_bindings
  application_epg_dn = aci_application_epg.this["${each.value.tenant_name}/${each.value.ap_name}/${each.value.epg_name}"].id
  tdn                = "topology/pod-${each.value.pod_id}/paths-${each.value.node_id}/pathep-[eth${each.value.module}/${each.value.port}]"
  encap              = each.value.encap
  mode               = lookup(each.value, "mode", "regular")
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

  # fabricRsPodPGrpBGPRRP is what the GUI shows as "BGP Route Reflector
  # Policy" on the Pod Policy Group. RN and property name confirmed against
  # this APIC, not assumed (a wrong RN is rejected with "wrong rn prefix").
  dynamic "child" {
    for_each = lookup(each.value, "bgp_route_reflector_policy", null) != null ? [each.value.bgp_route_reflector_policy] : []
    content {
      rn         = "rspodPGrpBGPRRP"
      class_name = "fabricRsPodPGrpBGPRRP"
      content = {
        tnBgpInstPolName = child.value
      }
    }
  }
}

# ---------------------------------------------------------------------------
# ADR-020 Phase G -- Fault Lifecycle Policy / Syslog System Message Policy /
# Syslog Rate Limit Policy. All three are mandatory fabric-wide singletons
# under uni/fabric/moncommon, confirmed via direct APIC query (not guessed)
# -- no typed Terraform resource exists for any of them, so aci_rest_managed
# is used, same as Phase C's ntp/dns/snmp. content_on_destroy is set to this
# lab's confirmed original baseline values -- never remove it, same warning
# as Phase C's resources below.
resource "aci_rest_managed" "fault_lifecycle_policy" {
  count = length(local.fault_lifecycle_policy) > 0 ? 1 : 0

  dn         = "uni/fabric/moncommon/flcp-generic"
  class_name = "faultLcP"
  content = {
    soak   = tostring(lookup(local.fault_lifecycle_policy, "soak", 120))
    retain = tostring(lookup(local.fault_lifecycle_policy, "retain", 3600))
    clear  = tostring(lookup(local.fault_lifecycle_policy, "clear", 120))
  }
  # Resets to this lab's confirmed original defaults on destroy/removal --
  # never deletes the mandatory singleton object itself.
  content_on_destroy = {
    soak   = "120"
    retain = "3600"
    clear  = "120"
  }
}

resource "aci_rest_managed" "syslog_system_msg" {
  count = length(local.syslog_system_msg) > 0 ? 1 : 0

  dn         = "uni/fabric/moncommon/sysmsgp"
  class_name = "syslogSystemMsgP"
  content = {
    systemSyslogMsgHdl = lookup(local.syslog_system_msg, "admin_state", "monitor")
  }
  # Resets to this lab's confirmed original default on destroy/removal --
  # never deletes the mandatory singleton object itself.
  content_on_destroy = {
    systemSyslogMsgHdl = "monitor"
  }
}

resource "aci_rest_managed" "syslog_rate_limit" {
  count = length(local.syslog_rate_limit) > 0 ? 1 : 0

  dn         = "uni/fabric/moncommon/ratelimitp"
  class_name = "syslogRateLimitP"
  content = {
    enabled     = lookup(local.syslog_rate_limit, "enabled", true) ? "yes" : "no"
    limitPerSec = tostring(lookup(local.syslog_rate_limit, "limit_per_sec", 500))
  }
  # Resets to this lab's confirmed original defaults on destroy/removal --
  # never deletes the mandatory singleton object itself.
  content_on_destroy = {
    enabled     = "yes"
    limitPerSec = "500"
  }
}

# ---------------------------------------------------------------------------
# ADR-020 Phase F -- RBAC / Security Domains / Local Users. Confirmed real
# DNs via direct APIC query (not guessed): Security Domain at
# uni/userext/domain-<name>, Local User at uni/userext/user-<name>, User-
# Security-Domain binding at uni/userext/user-<name>/userdomain-<domain>,
# and Role binding at .../userdomain-<domain>/role-<role>. All four are
# purely additive named objects -- no default/mandatory instance exists for
# any custom-named object here (the 3 pre-existing Security Domains --
# mgmt/all/common -- and 2 pre-existing Local Users -- admin/automation --
# are all creator=SYSTEM or otherwise untouched by this module; only new,
# explicitly-Nautobot-sourced names are ever managed). Real typed resources
# exist for all four (aci_aaa_domain/aci_local_user/aci_user_security_domain/
# aci_user_security_domain_role) -- no aci_rest_managed needed.
resource "aci_aaa_domain" "this" {
  for_each = local.security_domains

  name        = each.value.name
  description = lookup(each.value, "description", null)
}

resource "aci_local_user" "this" {
  for_each = local.local_users

  name           = each.value.name
  email          = lookup(each.value, "email", null)
  first_name     = lookup(each.value, "first_name", null)
  last_name      = lookup(each.value, "last_name", null)
  phone          = lookup(each.value, "phone", null)
  account_status = lookup(each.value, "account_status", null)

  # Password is never sourced from Nautobot/the generated YAML -- only from
  # the sensitive local_user_passwords Terraform variable, same convention
  # as vmm_vcenter_username/password. lookup(..., null) leaves it unmanaged
  # (ACI itself requires a password only at real account creation time; an
  # omitted value here means "no password change through this resource").
  pwd = lookup(var.local_user_passwords, each.value.name, null)
}

resource "aci_user_security_domain" "this" {
  for_each = local.user_security_domains

  local_user_dn = aci_local_user.this[each.value.user_name].id
  name          = each.value.domain_name
}

resource "aci_user_security_domain_role" "this" {
  for_each = local.user_security_domain_roles

  user_domain_dn = aci_user_security_domain.this["${each.value.user_name}/${each.value.domain_name}"].id
  name           = each.value.name
  priv_type      = lookup(each.value, "priv_type", null)
}

