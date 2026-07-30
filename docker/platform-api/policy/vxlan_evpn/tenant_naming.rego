package platform.vxlan_evpn

# ADR-014 Appendix A: every domain package exposes exactly one entry point,
# `decision`, returning a single {"allow": bool, "reasons": [...]} object.
# Mirrors cisco_aci/tenant_naming.rego's structure exactly (ADR-021 -- no new
# policy-integration pattern for a new domain, per ADR-018).

default decision := {"allow": false, "reasons": ["no tenants found in domain_intent"]}

decision := {"allow": true, "reasons": []} if {
	count(all_violations) == 0
	count(input.domain_intent.fabric.tenants) > 0
}

decision := {"allow": false, "reasons": all_violations} if {
	count(all_violations) > 0
}

all_violations contains msg if {
	some msg in invalid_tenant_names
}

all_violations contains msg if {
	some msg in invalid_vni_range
}

all_violations contains msg if {
	some msg in duplicate_vnis
}

# Naming convention: tenant names must be lowercase alphanumeric with
# hyphens only (same convention as cisco_aci's tenant_naming.rego).
invalid_tenant_names contains msg if {
	some tenant in input.domain_intent.fabric.tenants
	not regex.match("^[a-z0-9-]+$", tenant.name)
	msg := sprintf("tenant name '%s' does not match required pattern ^[a-z0-9-]+$", [tenant.name])
}

# VNI range: nxos_nvo's confirmed schema range for a VNI key is 1-16777214
# (registry.terraform.io/providers/CiscoDevNet/nxos/latest/docs/resources/nvo)
# -- not an invented limit.
invalid_vni_range contains msg if {
	some tenant in input.domain_intent.fabric.tenants
	some vrf in object.get(tenant, "vrfs", [])
	vni := object.get(vrf, "l3_vni", null)
	vni != null
	not valid_vni(vni)
	msg := sprintf("tenant '%s' VRF '%s' l3_vni %d is outside the valid VNI range 1-16777214", [tenant.name, vrf.name, vni])
}

invalid_vni_range contains msg if {
	some tenant in input.domain_intent.fabric.tenants
	some bd in object.get(tenant, "bridge_domains", [])
	vni := object.get(bd, "l2_vni", null)
	vni != null
	not valid_vni(vni)
	msg := sprintf("tenant '%s' bridge domain '%s' l2_vni %d is outside the valid VNI range 1-16777214", [tenant.name, bd.name, vni])
}

valid_vni(vni) if {
	vni >= 1
	vni <= 16777214
}

# VNI uniqueness: VNIs are globally unique on a single NX-OS device
# (nxos_nvo's `vnis` map and nxos_evpn's `vnis` map are both keyed by VNI,
# not by tenant) -- a collision here would silently overwrite one tenant's
# config with another's at terraform-apply time, exactly the class of bug
# ADR-020's `web-vrf`/`new-app-vrf` duplicate-VRF incident already
# demonstrated for a different resource shape.
#
# Collected as an ARRAY (not a set) deliberately -- a `contains` rule
# producing a set would deduplicate before we ever get a chance to detect
# the duplicate.
all_vni_occurrences := array.concat(
	[vni |
		some tenant in input.domain_intent.fabric.tenants
		some vrf in object.get(tenant, "vrfs", [])
		vni := object.get(vrf, "l3_vni", null)
		vni != null
	],
	[vni |
		some tenant in input.domain_intent.fabric.tenants
		some bd in object.get(tenant, "bridge_domains", [])
		vni := object.get(bd, "l2_vni", null)
		vni != null
	],
)

duplicate_vnis contains msg if {
	some i, vni_i in all_vni_occurrences
	some j, vni_j in all_vni_occurrences
	i < j
	vni_i == vni_j
	msg := sprintf("VNI %d is used more than once across tenants/VRFs/bridge-domains -- VNIs must be globally unique on the device", [vni_i])
}
