variable "nxos_url" {
  description = "NX-OS device URL (e.g. https://<nexus-9kv-host>) -- no simulator exists in this lab yet, see ADR-021."
  type        = string
}

variable "nxos_username" {
  description = "NX-OS device username"
  type        = string
  sensitive   = true
}

variable "nxos_password" {
  description = "NX-OS device password"
  type        = string
  sensitive   = true
}

variable "nxos_insecure" {
  description = "Skip TLS certificate verification. Set true for lab/self-signed certs only."
  type        = bool
  default     = false
}

variable "netascode_yaml_file" {
  description = "Path to the EVPN fabric YAML file produced by generate_evpn.py."
  type        = string
  default     = "../../netascode/evpn/fabric.yaml"
}

variable "bgp_asn" {
  description = "BGP ASN of the device this Terraform workspace targets. Must match that device's Nautobot Device.evpn_bgp_asn value -- not looked up automatically since this module manages a single device per provider block (ADR-021)."
  type        = string
}
