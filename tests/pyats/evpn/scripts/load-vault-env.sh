#!/usr/bin/env bash
# load-vault-env.sh — Fetch EVPN device credentials from HashiCorp Vault and
# export them as plain env vars for pyATS testbed.yml's %ENV{} substitution.
#
# Mirrors tests/pyats/aci/scripts/load-vault-env.sh's exact pattern -- same
# principle: no hardcoded credentials. Reads secret/lab/evpn (added ADR-021
# §12), which holds the 4 real Nexus 9000v nodes' shared admin/cisco
# credentials and their mgmt0 URLs (172.30.46.220-223, confirmed live this
# session -- ADR-021 §6/§10/§11).
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   source tests/pyats/evpn/scripts/load-vault-env.sh
#   pyats run job tests/pyats/evpn/job.py --testbed-file tests/pyats/evpn/testbed.yml
#
# Requires: curl, python3
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"

if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set. Export it before sourcing this script." >&2
  return 1 2>/dev/null || exit 1
fi

_secret_json="$(curl -sSf --header "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR%/}/v1/secret/data/lab/evpn")" || {
  echo "ERROR: failed to read secret/lab/evpn from Vault at ${VAULT_ADDR}" >&2
  return 1 2>/dev/null || exit 1
}

_exports="$(echo "${_secret_json}" | python3 -c '
import json, sys

data = json.load(sys.stdin)["data"]["data"]
username = data["username"]
password = data["password"]
print(f"export EVPN_USERNAME={json.dumps(username)}")
print(f"export EVPN_PASSWORD={json.dumps(password)}")
for key, env_name in (
    ("dc1_leaf_url", "DC1_LEAF_URL"),
    ("dc1_bgw_url", "DC1_BGW_URL"),
    ("dc2_leaf_url", "DC2_LEAF_URL"),
    ("dc2_bgw_url", "DC2_BGW_URL"),
):
    # Vault stores the bare mgmt0 URL (e.g. https://172.30.46.220) --
    # append /ins, the real NX-API JSON-RPC endpoint path.
    print(f"export {env_name}={json.dumps(data[key].rstrip(\"/\") + \"/ins\")}")
')"

eval "${_exports}"
unset _secret_json _exports

echo "[vault] Exported EVPN_USERNAME, EVPN_PASSWORD, DC1_LEAF_URL, DC1_BGW_URL, DC2_LEAF_URL, DC2_BGW_URL from Vault (${VAULT_ADDR})"
