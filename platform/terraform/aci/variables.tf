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

variable "vmm_vcenter_username" {
  description = "vCenter username for VMware VMM Domain controller association."
  type        = string
  sensitive   = true
  default     = null
}

variable "vmm_vcenter_password" {
  description = "vCenter password for VMware VMM Domain controller association."
  type        = string
  sensitive   = true
  default     = null
}

variable "netascode_yaml_file" {
  description = "Path to the NetAsCode tenants YAML file produced by the generator."
  type        = string
  default     = "../../netascode/aci/tenants.yaml"
}
