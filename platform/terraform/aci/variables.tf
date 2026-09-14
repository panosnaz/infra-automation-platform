variable "aci_url" {
  description = "APIC URL (e.g. https://172.30.46.103)"
  type        = string
}

variable "aci_username" {
  description = "APIC username"
  type        = string
  sensitive   = true
}

variable "aci_password" {
  description = "APIC password"
  type        = string
  sensitive   = true
}

variable "aci_insecure" {
  description = "Skip TLS certificate verification. Set true for lab/self-signed certs only."
  type        = bool
  default     = false
}

# VMM Domain integration -- vCenter controller credential, following the exact
# same sensitive-Terraform-variable pattern as aci_username/aci_password
# above (never embedded in the generated NetAsCode YAML or a Nautobot Custom
# Field). Single credential pair for this lab's one real vCenter; supplied via
# TF_VAR_vmm_vcenter_username/TF_VAR_vmm_vcenter_password (GitLab CI masked
# variables in the pipeline, same as the APIC credentials).
variable "vmm_vcenter_username" {
  description = "vCenter username for VMM Domain controller association."
  type        = string
  sensitive   = true
  default     = null
}

variable "vmm_vcenter_password" {
  description = "vCenter password for VMM Domain controller association."
  type        = string
  sensitive   = true
  default     = null
}

# RBAC/Local Users (ADR-020 Phase F) -- Local User passwords, following the
# exact same sensitive-Terraform-variable pattern as vmm_vcenter_username/
# password above. Keyed by username (map, not a single value), since a
# fabric can have multiple named Local Users each with their own password.
# Never embedded in the generated NetAsCode YAML or a Nautobot Custom
# Field -- supplied via TF_VAR_local_user_passwords (a JSON map) at apply
# time.
variable "local_user_passwords" {
  description = "Map of Local User name -> password (ADR-020 Phase F). Never persisted in Nautobot/YAML."
  type        = map(string)
  sensitive   = true
  default     = {}
}

# Fabric membership registration (2026-09-14). OFF by default, deliberately.
#
# Setting this true makes Terraform register every Nautobot-modeled leaf/spine
# with the APIC as a `fabricNodeIdentP`, so the roster in Nautobot and the
# roster in the APIC agree. That works -- it was applied and verified live --
# but on a fabric with no real switches it buys visibility and nothing else:
# the nodes sit at `fabricSt: undiscovered` forever, and the APIC then starts
# trying to deploy existing tenant policy to nodes that will never answer,
# which raised 3 extra minor faults (13 -> 16) on this lab before it was
# rolled back.
#
# Turn it on when the fabric has, or will soon have, real switches with these
# serial numbers -- pre-registering a serial so a switch is commissioned as
# the right node ID when it boots is the normal ACI workflow, and that is the
# case this exists for.
variable "register_fabric_membership" {
  description = "Register Nautobot-modeled leaf/spine switches with the APIC (fabricNodeIdentP). Leave false on fabrics with no real switches -- see variables.tf comment."
  type        = bool
  default     = false
}

variable "netascode_yaml_file" {
  description = "Path to the NetAsCode tenants YAML file produced by the generator."
  type        = string
  default     = "../../netascode/aci/tenants.yaml"
}
