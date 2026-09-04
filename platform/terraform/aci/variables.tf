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

variable "netascode_yaml_file" {
  description = "Path to the NetAsCode tenants YAML file produced by the generator."
  type        = string
  default     = "../../netascode/aci/tenants.yaml"
}
