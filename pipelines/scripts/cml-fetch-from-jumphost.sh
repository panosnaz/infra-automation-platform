#!/usr/bin/env bash
# cml-fetch-from-jumphost.sh — pull a file FROM the jump host back to this
# host (the CI runner or dev host), the reverse of cml-terraform-run.sh's
# push direction. Needed so terraform_plan's saved `tfplan` can become a
# real GitLab artifact that terraform_apply executes exactly, instead of
# terraform_apply silently recomputing its own plan (ADR-021 §21).
#
# Two legs, same dropfolder mechanism used throughout this ADR, just
# reversed: (1) cml-jump-push-file.sh drives the jump host to `put` the
# file to CML's INTERNAL dropfolder address; (2) a plain `curl` GET pulls
# it from the EXTERNAL dropfolder address, the same way any other machine
# with real internet access reaches CML.
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   pipelines/scripts/cml-fetch-from-jumphost.sh <lab_name> <node_label> \
#       <remote_path_on_jump_host> <local_dest_path>
set -euo pipefail

LAB_NAME="${1:?Usage: cml-fetch-from-jumphost.sh <lab_name> <node_label> <remote_path_on_jump_host> <local_dest_path>}"
NODE_LABEL="${2:?node_label required}"
REMOTE_PATH="${3:?remote_path_on_jump_host required}"
LOCAL_DEST="${4:?local_dest_path required}"

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DROPFOLDER_NAME="fetchback-$$-$(basename "${REMOTE_PATH}")"

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

echo "[cml-fetch-from-jumphost] pushing ${REMOTE_PATH} onto CML dropfolder as ${DROPFOLDER_NAME}..." >&2
"${_HERE}/cml-jump-push-file.sh" "${LAB_NAME}" "${NODE_LABEL}" "${REMOTE_PATH}" "${DROPFOLDER_NAME}" 90

echo "[cml-fetch-from-jumphost] downloading from CML dropfolder..." >&2
mkdir -p "$(dirname "${LOCAL_DEST}")"
curl -sSfk -o "${LOCAL_DEST}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/${DROPFOLDER_NAME}"

echo "[cml-fetch-from-jumphost] cleaning up dropfolder copy..." >&2
curl -sSk -Q "rm ${DROPFOLDER_NAME}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/" || true

echo "[cml-fetch-from-jumphost] done: $(wc -c < "${LOCAL_DEST}") bytes at ${LOCAL_DEST}" >&2
