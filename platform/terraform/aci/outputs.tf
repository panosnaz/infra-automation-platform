output "tenant_ids" {
  description = "Map of managed tenant names to their ACI distinguished names."
  value       = { for k, v in aci_tenant.this : k => v.id }
}

output "vrf_ids" {
  description = "Map of VRF keys (tenant/vrf) to their ACI distinguished names."
  value       = { for k, v in aci_vrf.this : k => v.id }
}

output "bridge_domain_ids" {
  description = "Map of Bridge Domain keys (tenant/bd) to their ACI distinguished names."
  value       = { for k, v in aci_bridge_domain.this : k => v.id }
}
