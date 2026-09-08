#!/usr/bin/env bash
# load-vault-creds.sh — Fetch ACI credentials from HashiCorp Vault and export
# them as TF_VAR_* environment variables so Terraform never reads secrets
# from a static tfvars file.
#
# This closes the Terraform -> Vault gap: previously, aci_username/aci_password
# had to be copied by hand into a local terraform.tfvars file. That file still
# worked (and was gitignored), but it meant Terraform owned a static copy of a
# secret instead of retrieving it at runtime, violating ADR-012 (Centralized
# Secrets Management — "No platform component permanently stores or owns
# sensitive credentials").
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<root-or-scoped-token>
#   source platform/terraform/aci/scripts/load-vault-creds.sh
#   terraform -chdir=platform/terraform/aci plan
#
# Requires: curl, python3 (both already used elsewhere in this repo)
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"

if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set. Export it before sourcing this script." >&2
  return 1 2>/dev/null || exit 1
fi

_secret_json="$(curl -sSf --header "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR%/}/v1/secret/data/lab/platform")" || {
  echo "ERROR: failed to read secret/lab/platform from Vault at ${VAULT_ADDR}" >&2
  return 1 2>/dev/null || exit 1
}

_vault_value() {
  printf '%s' "${_secret_json}" | python3 -c '
import json
import sys
data = json.load(sys.stdin)["data"]["data"]
print(data.get(sys.argv[1], ""))
' "$1"
}

export TF_VAR_aci_url="$(_vault_value aci_url)"
export TF_VAR_aci_username="$(_vault_value aci_username)"
export TF_VAR_aci_password="$(_vault_value aci_password)"
_vmm_vcenter_username="$(_vault_value vmm_vcenter_username)"
_vmm_vcenter_password="$(_vault_value vmm_vcenter_password)"
if [[ -n "${_vmm_vcenter_username}" ]]; then
  export TF_VAR_vmm_vcenter_username="${_vmm_vcenter_username}"
fi
if [[ -n "${_vmm_vcenter_password}" ]]; then
  export TF_VAR_vmm_vcenter_password="${_vmm_vcenter_password}"
fi
# Present since 2026-07-04; fall back to "true" for older secrets written
# before this field existed (this Vault only ever stores the lab ACI
# simulator, which always uses a self-signed certificate).
export TF_VAR_aci_insecure="$(_vault_value aci_insecure)"
if [[ -z "${TF_VAR_aci_insecure}" ]]; then
  export TF_VAR_aci_insecure="true"
fi
unset _secret_json _vmm_vcenter_username _vmm_vcenter_password

echo "[vault] Exported password-based ACI Terraform variables from Vault (${VAULT_ADDR})"
