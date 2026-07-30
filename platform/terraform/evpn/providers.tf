terraform {
  required_version = ">= 1.6"
  required_providers {
    nxos = {
      source  = "CiscoDevNet/nxos"
      version = "~> 0.13"
    }
  }
}

# ADR-021 §1: CiscoDevNet/nxos communicates via NX-API REST (`feature nxapi`
# required on the target device). No live device exists in this lab yet
# (the simulator gap ADR-021 states explicitly) -- these credentials point
# at wherever a Nexus 9Kv (or equivalent) ends up once one is stood up.
provider "nxos" {
  username = var.nxos_username
  password = var.nxos_password
  url      = var.nxos_url
  insecure = var.nxos_insecure
}
