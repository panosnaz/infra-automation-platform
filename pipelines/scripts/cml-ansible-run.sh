#!/usr/bin/env bash
# cml-ansible-run.sh — package the EVPN Ansible directory + its referenced
# NetAsCode YAML, relay it onto the CML jump host (same two-hop dropfolder
# mechanism as cml-terraform-run.sh), and run ansible-playbook there against
# the real lab devices via NX-API (httpapi), since the runner has no network
# path to them at all (ADR-021 §5/§12).
#
# Unlike Terraform, this does NOT need anything installed on the jump host
# beyond what cml-provision-py-env.sh already sets up once (Ansible has no
# genie-style musl blocker -- confirmed live, ADR-021 §18) -- this script
# assumes that provisioning has already run.
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   pipelines/scripts/cml-ansible-run.sh <lab_name> <node_label> \
#       <local_dir_to_bundle> <repo_relative_ansible_dir> <playbook_name>
#
# Requires TF_VAR_nxos_url/_username/_password already exported (same
# convention as cml-terraform-run.sh, e.g. via load-vault-evpn-tf-creds.sh)
# -- reused here as nxos_host/nxos_username/nxos_password extra-vars.
set -euo pipefail

LAB_NAME="${1:?Usage: cml-ansible-run.sh <lab_name> <node_label> <local_dir_to_bundle> <repo_relative_ansible_dir> <playbook_name>}"
NODE_LABEL="${2:?node_label required}"
LOCAL_BUNDLE_DIR="${3:?local_dir_to_bundle required}"
ANSIBLE_SUBDIR="${4:?repo_relative_ansible_dir required, e.g. platform/ansible/evpn}"
PLAYBOOK_NAME="${5:?playbook_name required, e.g. verify-fabric.yml}"

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_WORKDIR="/home/cisco/ci-run-ansible"
BUNDLE_NAME="ansiblebundle-$$.tar.gz"
VENV="/home/cisco/py-env/venv/bin"

if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set." >&2
  exit 1
fi
for v in TF_VAR_nxos_url TF_VAR_nxos_username TF_VAR_nxos_password; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: ${v} must be exported before calling this script (e.g. source load-vault-evpn-tf-creds.sh)." >&2
    exit 1
  fi
done
NXOS_HOST="$(python3 -c "from urllib.parse import urlsplit; print(urlsplit('${TF_VAR_nxos_url}').hostname)")"

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
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

# Preserve the real repo-relative path structure (platform/ansible/<domain>,
# platform/netascode/<domain>) so verify-fabric.yml's own relative
# "../../../netascode/<domain>/fabric.yaml" reference keeps resolving the
# same way after extraction -- same reasoning as cml-terraform-run.sh.
DOMAIN="$(basename "${ANSIBLE_SUBDIR}")"
NETASCODE_SUBDIR="$(dirname "$(dirname "${ANSIBLE_SUBDIR}")")/netascode/${DOMAIN}"
STAGE="${WORK}/stage"
mkdir -p "${STAGE}/$(dirname "${ANSIBLE_SUBDIR}")" "${STAGE}/$(dirname "${NETASCODE_SUBDIR}")"
cp -r "${LOCAL_BUNDLE_DIR}/${ANSIBLE_SUBDIR}" "${STAGE}/${ANSIBLE_SUBDIR}"
cp -r "${LOCAL_BUNDLE_DIR}/${NETASCODE_SUBDIR}" "${STAGE}/${NETASCODE_SUBDIR}"

echo "[cml-ansible-run] bundling ${ANSIBLE_SUBDIR} (+ ${NETASCODE_SUBDIR})..." >&2
tar czf "${WORK}/${BUNDLE_NAME}" -C "${STAGE}" "${ANSIBLE_SUBDIR}" "${NETASCODE_SUBDIR}"

echo "[cml-ansible-run] uploading bundle to CML dropfolder..." >&2
curl -sSk -T "${WORK}/${BUNDLE_NAME}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/${BUNDLE_NAME}"

echo "[cml-ansible-run] pulling bundle onto jump host..." >&2
"${_HERE}/cml-jump-fetch-file.sh" "${LAB_NAME}" "${NODE_LABEL}" "${BUNDLE_NAME}" "${REMOTE_WORKDIR}/${BUNDLE_NAME}" 120

echo "[cml-ansible-run] cleaning up dropfolder copy..." >&2
curl -sSk -Q "rm ${BUNDLE_NAME}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/" || true

echo "[cml-ansible-run] extracting on jump host..." >&2
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "rm -rf ${REMOTE_WORKDIR}/work && mkdir -p ${REMOTE_WORKDIR}/work && tar xzf ${REMOTE_WORKDIR}/${BUNDLE_NAME} -C ${REMOTE_WORKDIR}/work && rm -f ${REMOTE_WORKDIR}/${BUNDLE_NAME}" \
  60

echo "[cml-ansible-run] running ansible-playbook..." >&2
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "cd ${REMOTE_WORKDIR}/work/${ANSIBLE_SUBDIR} && ANSIBLE_COLLECTIONS_PATH=/home/cisco/py-env/venv/ansible_collections ${VENV}/ansible-playbook -i inventory/hosts.yml playbooks/${PLAYBOOK_NAME} -e nxos_host=${NXOS_HOST} -e nxos_username=${TF_VAR_nxos_username} -e nxos_password=${TF_VAR_nxos_password}" \
  180
