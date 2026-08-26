#!/usr/bin/env bash
# cml-verify-fabric-run.sh — relay the plain-Python EVPN fabric feature
# check (tests/pyats/evpn/verify_fabric_features.py, ADR-021 §19 -- the
# pyATS-free replacement for pyats_verify) onto the jump host and run it
# against all 4 real devices.
#
# Single-file, no relative-path dependencies, so this uses the same
# upload/fetch two-hop dropfolder mechanism as cml-jump-fetch-file.sh
# directly, rather than cml-terraform-run.sh/cml-ansible-run.sh's
# directory-staging approach (unnecessary for one file).
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   pipelines/scripts/cml-verify-fabric-run.sh <lab_name> <node_label> \
#       <local_script_path>
#
# Requires EVPN_USERNAME/EVPN_PASSWORD/DC1_LEAF_URL/DC1_BGW_URL/
# DC2_LEAF_URL/DC2_BGW_URL already exported (e.g. via
# tests/pyats/evpn/scripts/load-vault-env.sh, which already exports exactly
# these names).
#
# Exit code: the script's own exit code (0 = all devices healthy, 1 = at
# least one real failure -- see verify_fabric_features.py), or 124 on a
# relay-level connection/timeout failure.
set -euo pipefail

LAB_NAME="${1:?Usage: cml-verify-fabric-run.sh <lab_name> <node_label> <local_script_path>}"
NODE_LABEL="${2:?node_label required}"
LOCAL_SCRIPT="${3:?local_script_path required}"

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_DIR="/home/cisco/ci-run-verify"
SCRIPT_NAME="$(basename "${LOCAL_SCRIPT}")"

for v in EVPN_USERNAME EVPN_PASSWORD DC1_LEAF_URL DC1_BGW_URL DC2_LEAF_URL DC2_BGW_URL; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: ${v} must be exported before calling this script (e.g. source tests/pyats/evpn/scripts/load-vault-env.sh)." >&2
    exit 1
  fi
done

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set." >&2
  exit 1
fi
_secret_json="$(curl -sSf --header "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR%/}/v1/secret/data/lab/cml")" || {
  echo "ERROR: failed to read secret/lab/cml from Vault at ${VAULT_ADDR}" >&2
  exit 1
}
CML_HOST="$(echo "${_secret_json}" | python3 -c '
import json, sys
from urllib.parse import urlsplit
print(urlsplit(json.load(sys.stdin)["data"]["data"]["url"]).hostname)
')"
CML_USER="$(echo "${_secret_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["data"]["username"])')"
CML_PASS="$(echo "${_secret_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["data"]["password"])')"
unset _secret_json

echo "[cml-verify-fabric-run] uploading ${SCRIPT_NAME} to CML dropfolder..." >&2
curl -sSk -T "${LOCAL_SCRIPT}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/${SCRIPT_NAME}"

echo "[cml-verify-fabric-run] pulling onto jump host..." >&2
"${_HERE}/cml-jump-fetch-file.sh" "${LAB_NAME}" "${NODE_LABEL}" "${SCRIPT_NAME}" "${REMOTE_DIR}/${SCRIPT_NAME}" 60

echo "[cml-verify-fabric-run] cleaning up dropfolder copy..." >&2
curl -sSk -Q "rm ${SCRIPT_NAME}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/" || true

echo "[cml-verify-fabric-run] running..." >&2
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "cd ${REMOTE_DIR} && DC1_LEAF_URL='${DC1_LEAF_URL}' DC1_BGW_URL='${DC1_BGW_URL}' DC2_LEAF_URL='${DC2_LEAF_URL}' DC2_BGW_URL='${DC2_BGW_URL}' EVPN_USERNAME='${EVPN_USERNAME}' EVPN_PASSWORD='${EVPN_PASSWORD}' /home/cisco/py-env/venv/bin/python3 ${SCRIPT_NAME}" \
  90
