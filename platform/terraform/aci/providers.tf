terraform {
  required_version = ">= 1.6"
  required_providers {
    aci = {
      source  = "CiscoDevNet/aci"
      version = "~> 2.0"
    }
  }
}

provider "aci" {
  username = var.aci_username
  password = var.aci_password
  url      = var.aci_url
  insecure = var.aci_insecure
}
