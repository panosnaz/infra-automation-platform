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
# ADR-021 §23: TF_VAR_bgp_asn is no longer forced to a placeholder -- the
# real ASN now comes from fabric.yaml/Nautobot's Device.evpn_bgp_asn
# Custom Field (main.tf's local.resolved_asn), looked up via the new
# TF_VAR_device_name this script also exports (the fabric.yaml device name
# matching EVPN_TARGET_DEVICE, e.g. dc1_leaf -> DC1-Leaf). Set EVPN_BGP_ASN
# to override with an explicit ASN instead (e.g. for local testing before
# a device has been onboarded into Nautobot).
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
EVPN_TARGET_DEVICE="${EVPN_TARGET_DEVICE:-dc1_leaf}"

case "${EVPN_TARGET_DEVICE}" in
  dc1_leaf) _device_name="DC1-Leaf" ;;
  dc1_bgw)  _device_name="DC1-BGW" ;;
  dc2_leaf) _device_name="DC2-Leaf" ;;
  dc2_bgw)  _device_name="DC2-BGW" ;;
  *)
    echo "ERROR: unknown EVPN_TARGET_DEVICE '${EVPN_TARGET_DEVICE}' (known: dc1_leaf, dc1_bgw, dc2_leaf, dc2_bgw)" >&2
    return 1 2>/dev/null || exit 1
    ;;
esac

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
export TF_VAR_device_name="${_device_name}"
if [[ -n "${EVPN_BGP_ASN:-}" ]]; then
  export TF_VAR_bgp_asn="${EVPN_BGP_ASN}"
else
  unset TF_VAR_bgp_asn
fi
unset _secret_json _exports

echo "[vault] Exported TF_VAR_nxos_* for ${EVPN_TARGET_DEVICE} (device_name=${TF_VAR_device_name}) from Vault (${VAULT_ADDR}); bgp_asn will resolve from fabric.yaml unless EVPN_BGP_ASN was set${TF_VAR_bgp_asn:+ (override active: ${TF_VAR_bgp_asn})}"
