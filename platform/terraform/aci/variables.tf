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

variable "netascode_yaml_file" {
  description = "Path to the NetAsCode tenants YAML file produced by the generator."
  type        = string
  default     = "../../netascode/aci/tenants.yaml"
}
