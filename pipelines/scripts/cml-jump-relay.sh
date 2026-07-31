#!/usr/bin/env bash
# cml-jump-relay.sh — retry wrapper around cml-jump-relay.exp. Connection
# establishment to CML's console-proxy has observed real intermittent
# flakiness (roughly 1 in 3 attempts in testing, ADR-021 SS12) -- this
# retries a few times on the relay script's own "exit 124" (its dedicated
# code for a connection/timeout failure, never confused with the relayed
# command's own exit code).
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   pipelines/scripts/cml-jump-relay.sh <lab_name> <node_label> <command> [timeout_seconds]
#
# Requires: curl, python3, expect, sshpass (all already used elsewhere in
# this platform's CI images/scripts -- see tests/pyats/*/scripts/load-vault-env.sh
# for the same Vault-read pattern).
set -euo pipefail

LAB_NAME="${1:?Usage: cml-jump-relay.sh <lab_name> <node_label> <command> [timeout_seconds]}"
NODE_LABEL="${2:?node_label required}"
RELAY_COMMAND="${3:?command required}"
TIMEOUT_SECONDS="${4:-60}"
MAX_ATTEMPTS="${CML_RELAY_MAX_ATTEMPTS:-3}"

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

attempt=1
while (( attempt <= MAX_ATTEMPTS )); do
  echo "[cml-jump-relay] attempt ${attempt}/${MAX_ATTEMPTS}: ${LAB_NAME}/${NODE_LABEL}: ${RELAY_COMMAND}" >&2
  set +e
  output="$(expect "${_HERE}/cml-jump-relay.exp" "${CML_HOST}" "${CML_USER}" "${CML_PASS}" "${LAB_NAME}" "${NODE_LABEL}" "${RELAY_COMMAND}" "${TIMEOUT_SECONDS}")"
  exit_code=$?
  set -e
  if [[ "${exit_code}" -ne 124 ]]; then
    echo "${output}"
    exit "${exit_code}"
  fi
  echo "[cml-jump-relay] connection attempt ${attempt} failed (exit 124), retrying..." >&2
  attempt=$(( attempt + 1 ))
done

echo "ERROR: all ${MAX_ATTEMPTS} connection attempts failed" >&2
exit 124
