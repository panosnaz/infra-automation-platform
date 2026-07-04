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

_exports="$(echo "${_secret_json}" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]["data"]
aci_url = data["aci_url"]
aci_username = data["aci_username"]
aci_password = data["aci_password"]
# Present since 2026-07-04; fall back to "true" for older secrets written
# before this field existed (this Vault only ever stores the lab ACI
# simulator, which always uses a self-signed certificate).
aci_insecure = data.get("aci_insecure", "true")
print(f"export TF_VAR_aci_url={json.dumps(aci_url)}")
print(f"export TF_VAR_aci_username={json.dumps(aci_username)}")
print(f"export TF_VAR_aci_password={json.dumps(aci_password)}")
print(f"export TF_VAR_aci_insecure={json.dumps(aci_insecure)}")
')"

eval "${_exports}"
unset _secret_json _exports

echo "[vault] Exported TF_VAR_aci_url, TF_VAR_aci_username, TF_VAR_aci_password, TF_VAR_aci_insecure from Vault (${VAULT_ADDR})"
