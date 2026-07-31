# ---------------------------------------------------------------------------
# Locals — parse the EVPN fabric YAML and build flat maps for for_each
# ---------------------------------------------------------------------------
locals {
  nac = yamldecode(file(var.netascode_yaml_file))

  tenants = {
    for t in local.nac.fabric.tenants :
    t.name => t
  }

  # Flat map of all VRFs: "tenant_vrf" => { ...vrf attrs, tenant_name, vrf_name }
  # NX-OS VRF names are global on the device (unlike ACI's tenant-scoped
  # model), so the flattened key doubles as the actual on-device VRF name --
  # prefixed with the tenant to avoid collisions across tenants.
  vrfs = merge([
    for tn, t in local.tenants : {
      for vrf in lookup(t, "vrfs", []) :
      "${tn}_${vrf.name}" => merge(vrf, {
        tenant_name    = tn
        on_device_name = "${tn}_${vrf.name}"
      })
    }
  ]...)

  # Flat map of all Bridge Domains: "tenant_bd" => { ...bd attrs, tenant_name, on_device_vrf_name }
  bridge_domains = merge([
    for tn, t in local.tenants : {
      for bd in lookup(t, "bridge_domains", []) :
      "${tn}_${bd.name}" => merge(bd, {
        tenant_name        = tn
        on_device_vrf_name = try("${tn}_${bd.vrf}", null)
      })
    }
  ]...)

  devices = {
    for d in lookup(local.nac.fabric, "devices", []) :
    d.name => d
  }
}

# ---------------------------------------------------------------------------
# Features — must be enabled before any VRF/VXLAN/EVPN/BGP config is possible.
# Confirmed schema: registry.terraform.io/providers/CiscoDevNet/nxos/latest/docs/resources/feature
# ---------------------------------------------------------------------------
resource "nxos_feature" "fabric" {
  bgp            = "enabled"
  evpn           = "enabled"
  nv_overlay     = "enabled"
  vn_segment     = "enabled"
  interface_vlan = "enabled"

  # Confirmed live (2026-07-30) and via the real provider schema (every
  # attribute here is a plain enabled/disabled string -- no content_on_
  # destroy-equivalent exists, unlike aci_rest_managed): `terraform destroy`
  # reports success but does not actually disable these features on the
  # device. prevent_destroy stops this module from silently no-op'ing a
  # destroy on shared, foundational fabric state -- see
  # Platform-Status-and-Pending-Items.md §2 for the manual NX-API revert
  # procedure if these genuinely need disabling.
  lifecycle {
    prevent_destroy = true
  }
}

# ---------------------------------------------------------------------------
# VRFs — one resource, one map entry per tenant VRF. L3 VNI is expressed via
# the `encap = "vxlan-<vni>"` attribute (confirmed schema: nxos_vrf's example
# usage shows exactly this format).
# ---------------------------------------------------------------------------
resource "nxos_vrf" "fabric" {
  depends_on = [nxos_feature.fabric]

  vrfs = {
    for key, vrf in local.vrfs :
    vrf.on_device_name => {
      description = try(vrf.description, null)
      admin_state = "admin-up"
      encap       = try("vxlan-${vrf.l3_vni}", "unknown")
      l3vni       = try(vrf.l3_vni, null) != null
    }
  }
}

# ---------------------------------------------------------------------------
# Bridge Domains — one resource, one map entry per tenant Bridge Domain
# (VLAN). Keyed by `fabric_encap` per the confirmed schema
# (vlan-XX for a plain VLAN, vxlan-XX once an L2 VNI is mapped).
# ---------------------------------------------------------------------------
resource "nxos_bridge_domain" "fabric" {
  depends_on = [nxos_vrf.fabric]

  bridge_domains = {
    for key, bd in local.bridge_domains :
    (try(bd.l2_vni, null) != null ? "vxlan-${bd.l2_vni}" : "vlan-${bd.vlan_id}") => {
      name                = bd.name
      admin_state         = "active"
      bridge_domain_state = "active"
      vrf_name            = try(bd.on_device_vrf_name, "default")
    }
  }
}

# ---------------------------------------------------------------------------
# NVO / NVE — the actual VXLAN overlay: one NVE interface (id "1"), with one
# VNI entry per L2 Bridge Domain and per L3 VRF. Confirmed schema:
# registry.terraform.io/providers/CiscoDevNet/nxos/latest/docs/resources/nvo
# ---------------------------------------------------------------------------
resource "nxos_nvo" "fabric" {
  depends_on = [nxos_bridge_domain.fabric]

  nve_interfaces = {
    "1" = {
      admin_state                = "enabled"
      host_reachability_protocol = "bgp"
      source_interface           = "lo0"
      vnis = merge(
        {
          for key, bd in local.bridge_domains :
          tostring(bd.l2_vni) => {
            associate_vrf                = false
            ingress_replication_protocol = "bgp"
          }
          if try(bd.l2_vni, null) != null
        },
        {
          for key, vrf in local.vrfs :
          tostring(vrf.l3_vni) => {
            associate_vrf                = true
            ingress_replication_protocol = "bgp"
          }
          if try(vrf.l3_vni, null) != null
        }
      )
    }
  }
}

# ---------------------------------------------------------------------------
# EVPN — route-target/route-distinguisher config per VNI. Confirmed schema:
# registry.terraform.io/providers/CiscoDevNet/nxos/latest/docs/resources/evpn
# Route targets/RD are left at NX-OS's "auto" convention (empty route_targets
# map = device default) until a real fabric's RT/RD numbering scheme exists
# to encode here -- deliberately not invented (ADR-021 §Consequences).
# ---------------------------------------------------------------------------
resource "nxos_evpn" "fabric" {
  depends_on = [nxos_nvo.fabric]

  admin_state = "enabled"

  vnis = merge(
    {
      for key, bd in local.bridge_domains :
      "vxlan-${bd.l2_vni}" => {}
      if try(bd.l2_vni, null) != null
    },
    {
      for key, vrf in local.vrfs :
      "vxlan-${vrf.l3_vni}" => {}
      if try(vrf.l3_vni, null) != null
    }
  )
}

# ---------------------------------------------------------------------------
# BGP — the actual EVPN control plane: the default VRF's L2VPN EVPN
# address-family (distributes MAC/IP routes fabric-wide) plus each tenant
# VRF's ipv4-ucast address-family with `advertise_l2vpn_evpn` (redistributes
# that VRF's local routes into EVPN). Confirmed schema:
# registry.terraform.io/providers/CiscoDevNet/nxos/latest/docs/resources/bgp
#
# Deliberately NOT included (ADR-021, honest scope limit): actual BGP
# neighbor/peer configuration (`vrfs.default.peers`/`interface_peers`).
# Nautobot has no Interface/Cable data model wired up for this domain yet
# (mirrors ADR-020 Phase B's same limitation for ACI Access Policies) --
# peer IPs/interfaces would have to be invented, not sourced from real data.
# ---------------------------------------------------------------------------
resource "nxos_bgp" "fabric" {
  depends_on = [nxos_evpn.fabric]

  admin_state          = "enabled"
  instance_admin_state = "enabled"
  asn                  = var.bgp_asn

  vrfs = merge(
    {
      "default" = {
        address_families = {
          "l2vpn-evpn" = {}
        }
      }
    },
    {
      for key, vrf in local.vrfs :
      vrf.on_device_name => {
        address_families = {
          "ipv4-ucast" = {
            advertise_l2vpn_evpn = "enabled"
          }
        }
      }
      if try(vrf.l3_vni, null) != null
    }
  )
}

# ---------------------------------------------------------------------------
# SVI interfaces — one per Bridge Domain with a gateway IP, bound to its
# VRF. Confirmed schema:
# registry.terraform.io/providers/CiscoDevNet/nxos/latest/docs/resources/svi_interface
#
# Deliberately NOT included (ADR-021, honest scope limit): the SVI's actual
# gateway IP address assignment. `nxos_svi_interface`'s own schema has no
# IP-address attribute -- that's a separate `nxos_ipv4` resource, whose
# schema was not researched in this pass. The SVI exists and is bound to
# the correct VRF/VLAN; its IP address is not yet configured.
# ---------------------------------------------------------------------------
resource "nxos_svi_interface" "fabric" {
  depends_on = [nxos_bgp.fabric]

  svi_interfaces = {
    for key, bd in local.bridge_domains :
    "vlan${bd.vlan_id}" => {
      admin_state = "up"
      description = try(bd.description, bd.name)
      vrf_dn      = try("sys/inst-${bd.on_device_vrf_name}", null)
    }
    if try(bd.gateway_ip, null) != null
  }
}

