#!/usr/bin/env bash
# cml-terraform-run.sh — package a local Terraform working directory, relay
# it onto the CML lab's jump host (via CML's own SFTP dropfolder, both
# legs), and run terraform there against the real lab devices.
#
# This is the piece ADR-021 §14 concluded was blocked ("no sshpass/expect
# on the jump host, apk install blocked, chrooted SFTP, base64 doesn't
# scale"). It isn't: nothing needs installing on the jump host at all --
# cml-jump-fetch-file.sh drives the whole two-hop transfer (upload to CML's
# EXTERNAL dropfolder from wherever this script runs, which has real
# internet access; pull from the INTERNAL dropfolder address from outside
# the jump host, the same way cml-jump-relay.sh already answers the jump
# host's own OS login prompt without anything installed there either).
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   pipelines/scripts/cml-terraform-run.sh <lab_name> <node_label> \
#       <local_dir_to_bundle> <repo_relative_terraform_dir> <plan|apply>
#
# <local_dir_to_bundle> is tarred as-is (paths preserved) and extracted on
# the jump host under a fixed working directory -- pass the repo root (or
# any ancestor of <repo_relative_terraform_dir>) so relative paths inside
# the Terraform config (e.g. netascode_yaml_file's "../../netascode/...")
# keep resolving the same way after extraction.
#
# Requires TF_VAR_nxos_url / TF_VAR_nxos_username / TF_VAR_nxos_password /
# TF_VAR_nxos_insecure / TF_VAR_bgp_asn to already be exported by the
# caller -- this script doesn't source device credentials itself (unlike
# CML's own admin credentials, which it reads from Vault the same way
# cml-jump-relay.sh does).
set -euo pipefail

LAB_NAME="${1:?Usage: cml-terraform-run.sh <lab_name> <node_label> <local_dir_to_bundle> <repo_relative_terraform_dir> <plan|apply>}"
NODE_LABEL="${2:?node_label required}"
LOCAL_BUNDLE_DIR="${3:?local_dir_to_bundle required}"
TF_SUBDIR="${4:?repo_relative_terraform_dir required, e.g. platform/terraform/evpn}"
TF_ACTION="${5:?action required: plan or apply}"

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_WORKDIR="/home/cisco/ci-run"
BUNDLE_NAME="tfbundle-$$.tar.gz"

if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set." >&2
  exit 1
fi
for v in TF_VAR_nxos_url TF_VAR_nxos_username TF_VAR_nxos_password TF_VAR_bgp_asn; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: ${v} must be exported before calling this script." >&2
    exit 1
  fi
done

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

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

NETASCODE_SUBDIR="$(dirname "$(dirname "${TF_SUBDIR}")")/netascode/$(basename "${TF_SUBDIR}")"

# Stage a copy rather than tar'ing the real working tree directly, so the
# generated terraform.tfvars (real device credentials) never touches the
# actual repo checkout, even transiently.
STAGE="${WORK}/stage"
mkdir -p "${STAGE}/$(dirname "${TF_SUBDIR}")" "${STAGE}/$(dirname "${NETASCODE_SUBDIR}")"
cp -r "${LOCAL_BUNDLE_DIR}/${TF_SUBDIR}" "${STAGE}/${TF_SUBDIR}"
rm -rf "${STAGE}/${TF_SUBDIR}/.terraform" "${STAGE}/${TF_SUBDIR}/.terraform.lock.hcl" "${STAGE}/${TF_SUBDIR}/tfplan"
cp -r "${LOCAL_BUNDLE_DIR}/${NETASCODE_SUBDIR}" "${STAGE}/${NETASCODE_SUBDIR}"

cat > "${STAGE}/${TF_SUBDIR}/terraform.tfvars" <<EOF
nxos_url      = "${TF_VAR_nxos_url}"
nxos_username = "${TF_VAR_nxos_username}"
nxos_password = "${TF_VAR_nxos_password}"
nxos_insecure = ${TF_VAR_nxos_insecure:-true}
bgp_asn       = "${TF_VAR_bgp_asn}"
EOF

echo "[cml-terraform-run] bundling ${TF_SUBDIR} (+ ${NETASCODE_SUBDIR})..." >&2
tar czf "${WORK}/${BUNDLE_NAME}" -C "${STAGE}" "${TF_SUBDIR}" "${NETASCODE_SUBDIR}"

echo "[cml-terraform-run] uploading bundle to CML dropfolder..." >&2
curl -sSk -T "${WORK}/${BUNDLE_NAME}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/${BUNDLE_NAME}"

echo "[cml-terraform-run] pulling bundle onto jump host..." >&2
"${_HERE}/cml-jump-fetch-file.sh" "${LAB_NAME}" "${NODE_LABEL}" "${BUNDLE_NAME}" "${REMOTE_WORKDIR}/${BUNDLE_NAME}" 120

echo "[cml-terraform-run] cleaning up dropfolder copy..." >&2
curl -sSk -Q "RM /${BUNDLE_NAME}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/" || true

echo "[cml-terraform-run] extracting and running terraform ${TF_ACTION}..." >&2
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "rm -rf ${REMOTE_WORKDIR}/tfwork && mkdir -p ${REMOTE_WORKDIR}/tfwork && tar xzf ${REMOTE_WORKDIR}/${BUNDLE_NAME} -C ${REMOTE_WORKDIR}/tfwork && rm -f ${REMOTE_WORKDIR}/${BUNDLE_NAME}" \
  60

TF_CMD="terraform init -input=false && terraform ${TF_ACTION} -input=false"
if [[ "${TF_ACTION}" == "apply" ]]; then
  TF_CMD="${TF_CMD} -auto-approve"
fi

"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "cd ${REMOTE_WORKDIR}/tfwork/${TF_SUBDIR} && ${TF_CMD}" \
  180
