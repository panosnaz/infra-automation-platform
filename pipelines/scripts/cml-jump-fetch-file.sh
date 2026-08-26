#!/usr/bin/env bash
# cml-jump-fetch-file.sh — retry wrapper around cml-jump-fetch-file.exp,
# same retry-on-exit-124 convention as cml-jump-relay.sh.
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   pipelines/scripts/cml-jump-fetch-file.sh <lab_name> <node_label> \
#       <remote_filename> <local_dest_path> [timeout_seconds]
#
# Precondition: <remote_filename> must already be uploaded to CML's SFTP
# dropfolder over the external address before calling this (e.g. via
# `curl -T <file> sftp://<user>:<pass>@<cml_host>/<remote_filename>`).
set -euo pipefail

LAB_NAME="${1:?Usage: cml-jump-fetch-file.sh <lab_name> <node_label> <remote_filename> <local_dest_path> [timeout_seconds]}"
NODE_LABEL="${2:?node_label required}"
REMOTE_FILE="${3:?remote_filename required}"
LOCAL_DEST="${4:?local_dest_path required}"
TIMEOUT_SECONDS="${5:-90}"
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
  echo "[cml-jump-fetch-file] attempt ${attempt}/${MAX_ATTEMPTS}: ${LAB_NAME}/${NODE_LABEL}: ${REMOTE_FILE} -> ${LOCAL_DEST}" >&2
  set +e
  output="$(expect "${_HERE}/cml-jump-fetch-file.exp" "${CML_HOST}" "${CML_USER}" "${CML_PASS}" "${LAB_NAME}" "${NODE_LABEL}" "${REMOTE_FILE}" "${LOCAL_DEST}" "${TIMEOUT_SECONDS}")"
  exit_code=$?
  set -e
  if [[ "${exit_code}" -eq 0 ]]; then
    echo "${output}"
    exit 0
  fi
  echo "[cml-jump-fetch-file] attempt ${attempt} failed (exit ${exit_code}): ${output}" >&2
  attempt=$(( attempt + 1 ))
done

echo "ERROR: all ${MAX_ATTEMPTS} fetch attempts failed" >&2
exit 124
