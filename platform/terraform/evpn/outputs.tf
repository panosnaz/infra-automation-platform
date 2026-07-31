output "vrf_names" {
  description = "Map of VRF keys (tenant_vrf) to their on-device VRF names."
  value       = { for k, v in local.vrfs : k => v.on_device_name }
}

output "bridge_domain_encaps" {
  description = "Map of Bridge Domain keys (tenant_bd) to their fabric_encap key on the device."
  value       = { for k, v in local.bridge_domains : k => (try(v.l2_vni, null) != null ? "vxlan-${v.l2_vni}" : "vlan-${v.vlan_id}") }
}

output "svi_gateway_addresses" {
  description = "Map of Bridge Domain keys (tenant_bd) with a gateway IP to their SVI interface name and address."
  value       = { for k, v in local.bds_with_gateway : k => { interface = "vlan${v.vlan_id}", address = v.gateway_ip } }
}
