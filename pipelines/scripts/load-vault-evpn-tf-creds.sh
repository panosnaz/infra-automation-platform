#!/usr/bin/env bash
# load-vault-evpn-tf-creds.sh — export TF_VAR_nxos_* for cml-terraform-run.sh
# / terraform_plan / terraform_apply, sourced from secret/lab/evpn (the same
# Vault secret tests/pyats/evpn/scripts/load-vault-env.sh already reads).
#
# The generator-driven Terraform module manages one device per provider
# block (ADR-021, variables.tf's own bgp_asn comment), so a target device
# must be chosen -- EVPN_TARGET_DEVICE selects which of the 4 real nodes
# (default dc1_leaf, matching every other live-verification pass in this
# ADR series).
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   export EVPN_TARGET_DEVICE=dc1_leaf   # optional, default shown
#   source pipelines/scripts/load-vault-evpn-tf-creds.sh
#
# Known gap, not solved by this script: TF_VAR_bgp_asn has no source in
# Vault or Nautobot today -- no EVPN Device objects with a populated
# evpn_bgp_asn Custom Field were found in this lab's Nautobot instance
# (confirmed via a direct API query, not assumed). Defaults to a clearly
# placeholder ASN (65000) unless EVPN_BGP_ASN is set -- do not treat this
# default as real fabric data.
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
EVPN_TARGET_DEVICE="${EVPN_TARGET_DEVICE:-dc1_leaf}"

if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set. Export it before sourcing this script." >&2
  return 1 2>/dev/null || exit 1
fi

_secret_json="$(curl -sSf --header "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR%/}/v1/secret/data/lab/evpn")" || {
  echo "ERROR: failed to read secret/lab/evpn from Vault at ${VAULT_ADDR}" >&2
  return 1 2>/dev/null || exit 1
}

_exports="$(echo "${_secret_json}" | python3 -c "
import json, sys

data = json.load(sys.stdin)['data']['data']
device = '${EVPN_TARGET_DEVICE}'
url_key = f'{device}_url'
if url_key not in data:
    print(f'ERROR: no {url_key} in secret/lab/evpn (known devices: dc1_leaf, dc1_bgw, dc2_leaf, dc2_bgw)', file=sys.stderr)
    sys.exit(1)
print(f'export TF_VAR_nxos_url={json.dumps(data[url_key])}')
print(f'export TF_VAR_nxos_username={json.dumps(data[\"username\"])}')
print(f'export TF_VAR_nxos_password={json.dumps(data[\"password\"])}')
")"

eval "${_exports}"
export TF_VAR_nxos_insecure="true"
export TF_VAR_bgp_asn="${EVPN_BGP_ASN:-65000}"
unset _secret_json _exports

echo "[vault] Exported TF_VAR_nxos_* for ${EVPN_TARGET_DEVICE} from Vault (${VAULT_ADDR}); TF_VAR_bgp_asn=${TF_VAR_bgp_asn} (placeholder unless EVPN_BGP_ASN was set)"
