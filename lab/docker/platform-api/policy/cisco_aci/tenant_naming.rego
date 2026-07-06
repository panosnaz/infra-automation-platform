package platform.cisco_aci

# ADR-014 Appendix A: every domain package exposes exactly one entry point,
# `decision`, returning a single {"allow": bool, "reasons": [...]}"} object.
# The Python integration layer (technical_policy.py) never knows this rule's
# internal structure — only that this package exists at this path.

default decision := {"allow": false, "reasons": ["no tenants found in domain_intent"]}

decision := {"allow": true, "reasons": []} if {
	count(invalid_tenant_names) == 0
	count(input.domain_intent.apic.tenants) > 0
}

decision := {"allow": false, "reasons": invalid_tenant_names} if {
	count(invalid_tenant_names) > 0
}

# Naming convention: tenant names must be lowercase alphanumeric with
# hyphens only (matches the existing web-tenant vertical slice example).
invalid_tenant_names contains msg if {
	some tenant in input.domain_intent.apic.tenants
	not regex.match("^[a-z0-9-]+$", tenant.name)
	msg := sprintf("tenant name '%s' does not match required pattern ^[a-z0-9-]+$", [tenant.name])
}
