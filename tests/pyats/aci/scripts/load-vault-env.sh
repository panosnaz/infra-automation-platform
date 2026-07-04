#!/usr/bin/env bash
# load-vault-env.sh — Fetch ACI credentials from HashiCorp Vault and export
# them as plain env vars for pyATS testbed.yml's %ENV{} substitution.
#
# Mirrors platform/terraform/aci/scripts/load-vault-creds.sh (TF_VAR_*) and
# platform/ansible/aci/inventory/group_vars/aci.yml (community.hashi_vault
# lookup) — same source secret, same principle: no hardcoded credentials.
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   source tests/pyats/aci/scripts/load-vault-env.sh
#   pyats run job tests/pyats/aci/job.py --testbed-file tests/pyats/aci/testbed.yml
#
# Requires: curl, python3
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
from urllib.parse import urlsplit

data = json.load(sys.stdin)["data"]["data"]
host = urlsplit(data["aci_url"]).hostname
username = data["aci_username"]
password = data["aci_password"]
print(f"export ACI_HOST={json.dumps(host)}")
print(f"export ACI_USERNAME={json.dumps(username)}")
print(f"export ACI_PASSWORD={json.dumps(password)}")
')"

eval "${_exports}"
unset _secret_json _exports

echo "[vault] Exported ACI_HOST, ACI_USERNAME, ACI_PASSWORD from Vault (${VAULT_ADDR})"
