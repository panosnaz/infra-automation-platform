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
  description = "Override for this device's BGP ASN. Normally left unset -- sourced automatically from local.devices[var.device_name].bgp_asn (fabric.yaml/Nautobot Device.evpn_bgp_asn), see ADR-021 §23."
  type        = string
  default     = null
}

variable "device_name" {
  description = "Name of the fabric device (matching fabric.yaml's fabric.devices[].name / Nautobot Device.name) that this Terraform workspace/provider block targets -- used to look up this device's own BGP ASN and BGP peers. Must be set (ADR-021 §23)."
  type        = string
}
