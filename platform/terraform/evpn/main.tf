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

  # This workspace's own device entry (ADR-021 §23) -- looked up by
  # var.device_name, the same fabric.yaml/Nautobot Device this provider
  # block's nxos_url actually points at. Empty map if the device hasn't
  # been onboarded into fabric.yaml yet (e.g. a fresh device with no
  # evpn_bgp_asn/evpn_role Custom Fields set), so every reference below
  # degrades gracefully rather than erroring on `try(...)`/`lookup(...)`.
  this_device = lookup(local.devices, var.device_name, {})

  # var.bgp_asn is an explicit override for local testing; the real,
  # end-to-end path is Nautobot's Device.evpn_bgp_asn -> generator ->
  # fabric.yaml -> here, closing the gap Platform-Status-and-Pending-Items.md
  # used to track ("no real Nautobot-sourced ASN exists").
  resolved_asn = coalesce(var.bgp_asn, try(tostring(local.this_device.bgp_asn), null))

  # This device's real, directly-connected eBGP neighbors (peer IP + remote
  # ASN), sourced from Nautobot's evpn_bgp_peers Custom Field via the
  # generator -- ADR-021 §23. Keyed by peer_ip per nxos_bgp's own schema
  # (vrfs.<name>.peers.<peer_ip>, confirmed via `terraform providers schema
  # -json` against the real CiscoDevNet/nxos provider).
  bgp_peers = {
    for peer in try(local.this_device.bgp_peers, []) :
    peer.peer_ip => {
      remote_asn = tostring(peer.remote_asn)
      description = try(peer.description, null)
    }
  }

  # Bridge Domains with a gateway IP configured -- these already have an SVI
  # via nxos_svi_interface.fabric below; this subset also gets an address
  # assignment via nxos_ipv4.fabric.
  bds_with_gateway = {
    for key, bd in local.bridge_domains :
    key => bd
    if try(bd.gateway_ip, null) != null
  }

  # nxos_ipv4's own grouping level is VRF name (matching nxos_vrf.fabric's
  # plain on_device_name, not nxos_svi_interface's "sys/inst-<name>" DN
  # format) -- defaults to "default" the same way nxos_svi_interface.fabric's
  # vrf_dn lookup does.
  ipv4_vrf_names = distinct([
    for key, bd in local.bds_with_gateway : coalesce(bd.on_device_vrf_name, "default")
  ])
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
}

# ---------------------------------------------------------------------------
# ADR-021 §7/§15: `terraform destroy` on nxos_feature.fabric used to report
# success without actually disabling anything on the device (confirmed live
# against DC1-Leaf, 2026-07-30) -- the CiscoDevNet/nxos v0.13.1 schema has no
# content_on_destroy-equivalent attribute to fix this at the attribute level
# (every attribute is a plain enabled/disabled string). A destroy-time
# provisioner can only reference `self`/`count.index`/`each.key` (confirmed
# via `terraform validate`, not assumed) -- it cannot read `var.*` directly,
# so credentials are threaded through this null_resource's own `triggers`
# instead, the standard workaround for this exact limitation. This does mean
# these values are stored in Terraform state via `triggers`, same as they
# already are via the `nxos` provider block itself -- not a new exposure.
#
# Issues the same real NX-API cli_conf commands used to manually revert
# DC1-Leaf in §6. `evpn`/`vn_segment` are deliberately NOT included -- §10
# found neither appears as a distinct row in this platform's `show feature`
# output, so a `no feature evpn`/`no feature vn-segment-vlan-based` command
# would very likely fail with an invalid-feature-name error and abort the
# whole destroy for no benefit.
#
# Live-verified end-to-end against real DC1-Leaf hardware (2026-08-26, §16):
# apply -> plan (0 diff) -> destroy -> independent NX-API `show feature`
# query confirmed bgp/interface-vlan/nve genuinely disabled post-destroy.
# ---------------------------------------------------------------------------
resource "null_resource" "revert_nxos_feature_on_destroy" {
  depends_on = [nxos_feature.fabric]

  triggers = {
    nxos_url      = var.nxos_url
    nxos_username = var.nxos_username
    nxos_password = var.nxos_password
    nxos_insecure = tostring(var.nxos_insecure)
  }

  provisioner "local-exec" {
    when = destroy

    # Credentials come from `self.triggers`, not interpolated into
    # `command`, so they aren't captured in Terraform's own logs (matches
    # Terraform's documented guidance for passing secrets to local-exec).
    environment = {
      NXOS_URL      = self.triggers.nxos_url
      NXOS_USERNAME = self.triggers.nxos_username
      NXOS_PASSWORD = self.triggers.nxos_password
      NXOS_WGET_TLS = self.triggers.nxos_insecure == "true" ? "--no-check-certificate" : ""
    }

    # Uses wget, not curl -- confirmed live (2026-08-26) that `terraform
    # destroy` can run from a host with no curl at all (this ADR's own
    # jump host, knowledge/runbooks/CML-EVPN-Lab-Jump-Host.md, ships only
    # busybox wget). wget's `-u`/`--user` flags don't exist on busybox
    # either (same runbook, SS5), so the Basic auth header is built by hand,
    # and the request body goes through `--post-file` (a temp file, not
    # `--post-data`) since busybox wget's argument parsing mishandles the
    # embedded quotes/semicolons in the cli_conf payload otherwise.
    command = <<-EOT
      set -euo pipefail
      AUTH=$(printf '%s:%s' "$NXOS_USERNAME" "$NXOS_PASSWORD" | base64 | tr -d '\n')
      REQ_FILE=$(mktemp)
      trap 'rm -f "$REQ_FILE"' EXIT
      printf '{"ins_api":{"version":"1.0","type":"cli_conf","chunk":"0","sid":"1","input":"no feature bgp ; no feature interface-vlan ; no feature nv overlay","output_format":"json"}}' > "$REQ_FILE"
      response=$(wget $NXOS_WGET_TLS -q -O- \
        --header="Content-Type: application/json" \
        --header="Authorization: Basic $AUTH" \
        --post-file="$REQ_FILE" \
        "$NXOS_URL/ins")
      echo "$response"
      if echo "$response" | grep -Eqi '"code":[[:space:]]*"[45][0-9]{2}"'; then
        echo "nxos_feature destroy-time revert failed against $NXOS_URL: $response" >&2
        exit 1
      fi
    EOT
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
# BGP neighbor/peer configuration (ADR-021 §23, closing the honest scope
# limit this resource used to document): `vrfs.default.peers`, keyed by
# peer IP, each activating the l2vpn-evpn address-family -- confirmed via
# `terraform providers schema -json` against the real provider, not
# guessed. ASN and peer IPs are real, sourced from Nautobot's
# evpn_bgp_asn/evpn_bgp_peers Custom Fields (verified live against all 4
# real devices), not invented -- but the *design* itself (which ASN each
# device gets, iBGP vs eBGP per peer) was corrected mid-implementation
# after discovering this lab already had a partial day-0 BGP reference
# design (site-shared ASN, loopback-based iBGP within a site + eBGP
# between sites' BGWs) that revealed a real constraint: the loopback-based
# iBGP sessions sit permanently Idle (no underlay IGP exists to route
# loopback-to-loopback traffic), while the directly-connected BGW-to-BGW
# eBGP session was ALREADY established and exchanging real EVPN routes.
# This module's peers therefore all use directly-connected interface IPs
# (never loopbacks) for both iBGP (site-local) and eBGP (multi-site)
# sessions -- proven reachable without any underlay IGP, unlike the
# loopback design. Adding a real underlay IGP for loopback reachability
# is a distinct, larger scope item deliberately not invented here.
# ---------------------------------------------------------------------------
resource "nxos_bgp" "fabric" {
  depends_on = [nxos_evpn.fabric]

  admin_state          = "enabled"
  instance_admin_state = "enabled"
  asn                  = local.resolved_asn

  lifecycle {
    precondition {
      condition     = local.resolved_asn != null
      error_message = "No BGP ASN resolved for device '${var.device_name}' -- set var.bgp_asn explicitly, or onboard this device into fabric.yaml (Nautobot Device.evpn_bgp_asn Custom Field)."
    }
  }

  vrfs = merge(
    {
      "default" = {
        address_families = {
          "l2vpn-evpn" = {}
        }
        peers = {
          for peer_ip, peer in local.bgp_peers :
          peer_ip => {
            remote_asn  = peer.remote_asn
            description = peer.description
            peer_address_families = {
              "l2vpn-evpn" = {
                send_community_extended = "enabled"
                # Rewrites the EVPN route-target's embedded ASN on routes
                # exchanged with a different-AS peer (needed for RT
                # matching across a multi-site eBGP link) -- confirmed
                # against this lab's own already-established DC1-BGW <->
                # DC2-BGW session, which uses this exact setting.
                rewrite_rt_asn = peer.remote_asn != local.resolved_asn ? "enabled" : null
              }
            }
          }
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
# The SVI's gateway IP address itself is assigned separately by
# nxos_ipv4.fabric below (nxos_svi_interface's own schema has no
# IP-address attribute -- that's the distinct nxos_ipv4 resource).
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

# ---------------------------------------------------------------------------
# IPv4 addressing — assigns each SVI's gateway IP, grouped by VRF per the
# resource's own schema (vrfs.<name>.interfaces.<interface_id>.addresses.
# <address>, confirmed via the real provider schema -- terraform providers
# schema -json against the CiscoDevNet/nxos v0.13.1 binary, no live device
# needed for this structural confirmation). `interface_id` must match
# nxos_svi_interface's own naming ("vlan<id>"). `addresses`' map key is the
# address itself; bd.gateway_ip's existing "a.b.c.d/nn" format is used
# as-is (schema only says "Address", format not live-verified this pass).
# Confirmed schema: registry.terraform.io/providers/CiscoDevNet/nxos/latest/docs/resources/ipv4
# ---------------------------------------------------------------------------
resource "nxos_ipv4" "fabric" {
  depends_on = [nxos_svi_interface.fabric]

  vrfs = {
    for vrf_name in local.ipv4_vrf_names :
    vrf_name => {
      interfaces = {
        for key, bd in local.bds_with_gateway :
        "vlan${bd.vlan_id}" => {
          addresses = {
            (bd.gateway_ip) = {}
          }
        }
        if coalesce(bd.on_device_vrf_name, "default") == vrf_name
      }
    }
  }
}

