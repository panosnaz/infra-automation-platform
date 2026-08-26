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
# ADR-021 §22: state IS now persisted across runs (fixing §21's finding).
# terraform.tfstate lives at a stable, non-wiped jump-host location
# (/home/cisco/tf-state/<slug>, matching the same persistence already used
# for tf-mirror/py-env, not the ephemeral per-run ci-run/tfwork directory)
# and is copied into each fresh working directory before terraform runs,
# then copied back out after `apply`. `plan` fetches its saved `tfplan`
# back to the caller (via cml-fetch-from-jumphost.sh) so it can become a
# real GitLab artifact; `apply` expects that same file already staged
# locally and pushes it back up, so it executes the *exact* plan `plan`
# computed instead of silently recomputing one.
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
# For "apply", a `tfplan` file must already exist at
# <local_dir_to_bundle>/<repo_relative_terraform_dir>/tfplan (the artifact
# downloaded from the corresponding "plan" run's GitLab job via `needs:`).
#
# Requires TF_VAR_nxos_url / TF_VAR_nxos_username / TF_VAR_nxos_password /
# TF_VAR_device_name to already be exported by the caller (TF_VAR_nxos_insecure
# and TF_VAR_bgp_asn are optional overrides -- see main.tf's local.resolved_asn,
# ADR-021 §23) -- this script doesn't source device credentials itself
# (unlike CML's own admin credentials, which it reads from Vault the same way
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
# Keyed by device_name too, not just TF_SUBDIR -- this module manages one
# device per apply (ADR-021 §23's var.device_name), so two devices sharing
# the same TF_SUBDIR (e.g. DC1-Leaf and DC1-BGW both under
# platform/terraform/evpn) must not collide on the same persisted state.
STATE_SLUG="$(echo "${TF_SUBDIR}_${TF_VAR_device_name:-nodevice}" | tr '/' '_')"
PERSIST_DIR="/home/cisco/tf-state/${STATE_SLUG}"

if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set." >&2
  exit 1
fi
for v in TF_VAR_nxos_url TF_VAR_nxos_username TF_VAR_nxos_password TF_VAR_device_name; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: ${v} must be exported before calling this script." >&2
    exit 1
  fi
done
if [[ "${TF_ACTION}" == "apply" && ! -f "${LOCAL_BUNDLE_DIR}/${TF_SUBDIR}/tfplan" ]]; then
  echo "ERROR: apply requires ${LOCAL_BUNDLE_DIR}/${TF_SUBDIR}/tfplan (the plan job's artifact) to already exist locally." >&2
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

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

NETASCODE_SUBDIR="$(dirname "$(dirname "${TF_SUBDIR}")")/netascode/$(basename "${TF_SUBDIR}")"

# Stage a copy rather than tar'ing the real working tree directly, so the
# generated terraform.tfvars (real device credentials) never touches the
# actual repo checkout, even transiently.
STAGE="${WORK}/stage"
mkdir -p "${STAGE}/$(dirname "${TF_SUBDIR}")" "${STAGE}/$(dirname "${NETASCODE_SUBDIR}")"
cp -r "${LOCAL_BUNDLE_DIR}/${TF_SUBDIR}" "${STAGE}/${TF_SUBDIR}"
rm -rf "${STAGE}/${TF_SUBDIR}/.terraform" "${STAGE}/${TF_SUBDIR}/.terraform.lock.hcl"
if [[ "${TF_ACTION}" == "plan" ]]; then
  # A stale local tfplan from a previous run must not be bundled up for a
  # fresh plan -- only "apply" ever wants an existing tfplan carried along.
  rm -f "${STAGE}/${TF_SUBDIR}/tfplan"
fi
cp -r "${LOCAL_BUNDLE_DIR}/${NETASCODE_SUBDIR}" "${STAGE}/${NETASCODE_SUBDIR}"

cat > "${STAGE}/${TF_SUBDIR}/terraform.tfvars" <<EOF
nxos_url      = "${TF_VAR_nxos_url}"
nxos_username = "${TF_VAR_nxos_username}"
nxos_password = "${TF_VAR_nxos_password}"
nxos_insecure = ${TF_VAR_nxos_insecure:-true}
device_name   = "${TF_VAR_device_name}"
EOF
# bgp_asn is an explicit override only -- normally left unset so the ASN
# resolves from fabric.yaml/Nautobot's Device.evpn_bgp_asn (ADR-021 §23).
if [[ -n "${TF_VAR_bgp_asn:-}" ]]; then
  echo "bgp_asn = \"${TF_VAR_bgp_asn}\"" >> "${STAGE}/${TF_SUBDIR}/terraform.tfvars"
fi

echo "[cml-terraform-run] bundling ${TF_SUBDIR} (+ ${NETASCODE_SUBDIR})..." >&2
tar czf "${WORK}/${BUNDLE_NAME}" -C "${STAGE}" "${TF_SUBDIR}" "${NETASCODE_SUBDIR}"

echo "[cml-terraform-run] uploading bundle to CML dropfolder..." >&2
curl -sSk -T "${WORK}/${BUNDLE_NAME}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/${BUNDLE_NAME}"

echo "[cml-terraform-run] pulling bundle onto jump host..." >&2
"${_HERE}/cml-jump-fetch-file.sh" "${LAB_NAME}" "${NODE_LABEL}" "${BUNDLE_NAME}" "${REMOTE_WORKDIR}/${BUNDLE_NAME}" 120

echo "[cml-terraform-run] cleaning up dropfolder copy..." >&2
curl -sSk -Q "RM /${BUNDLE_NAME}" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/" || true

echo "[cml-terraform-run] extracting on jump host and restoring persisted state (if any)..." >&2
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "rm -rf ${REMOTE_WORKDIR}/tfwork && mkdir -p ${REMOTE_WORKDIR}/tfwork && tar xzf ${REMOTE_WORKDIR}/${BUNDLE_NAME} -C ${REMOTE_WORKDIR}/tfwork && rm -f ${REMOTE_WORKDIR}/${BUNDLE_NAME} && mkdir -p ${PERSIST_DIR} && cp ${PERSIST_DIR}/terraform.tfstate ${REMOTE_WORKDIR}/tfwork/${TF_SUBDIR}/terraform.tfstate 2>/dev/null; true" \
  60

if [[ "${TF_ACTION}" == "plan" ]]; then
  TF_CMD="terraform init -input=false && terraform plan -input=false -out=tfplan"
else
  # Executes the exact plan already computed by the "plan" job -- no
  # -auto-approve needed (or accepted) when applying a saved plan file.
  TF_CMD="terraform init -input=false && terraform apply -input=false tfplan"
fi

echo "[cml-terraform-run] running terraform ${TF_ACTION}..." >&2
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "cd ${REMOTE_WORKDIR}/tfwork/${TF_SUBDIR} && ${TF_CMD}" \
  180

if [[ "${TF_ACTION}" == "plan" ]]; then
  echo "[cml-terraform-run] fetching saved tfplan back as a local artifact..." >&2
  "${_HERE}/cml-fetch-from-jumphost.sh" "${LAB_NAME}" "${NODE_LABEL}" \
    "${REMOTE_WORKDIR}/tfwork/${TF_SUBDIR}/tfplan" "${LOCAL_BUNDLE_DIR}/${TF_SUBDIR}/tfplan"
else
  echo "[cml-terraform-run] persisting updated terraform.tfstate on the jump host..." >&2
  "${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
    "cp ${REMOTE_WORKDIR}/tfwork/${TF_SUBDIR}/terraform.tfstate ${PERSIST_DIR}/terraform.tfstate" \
    60
fi

