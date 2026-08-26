#!/usr/bin/env bash
# cml-provision-py-env.sh — one-time (idempotent), reusable version of the
# manual steps that got a working Python + Ansible + pyATS-adjacent
# environment onto the CML jump host (ADR-021 §18), so ansible_configure
# and any future Python-based relay tooling don't need a package manager on
# the jump host at all (apk install is blocked by this lab's NAT egress,
# confirmed live, §14).
#
# Bundles, in one shot:
#   - A portable, musl-linked CPython build (python-build-standalone,
#     "install_only_stripped" variant -- confirmed live: runs correctly on
#     real Alpine/musl, ~28 MB).
#   - musllinux wheels for ansible-core + its network-connection deps
#     (cryptography/paramiko/ncclient/pynacl) -- all resolved cleanly via
#     `pip download --platform musllinux_1_2_x86_64`, no compilation needed.
#   - The cisco.nxos / community.hashi_vault Ansible collections (+ their
#     own ansible.netcommon/ansible.utils dependencies), fetched via
#     `ansible-galaxy collection download`.
#
# Does NOT provision pyATS -- confirmed live (§18) that pyats.clean,
# rest.connector, and unicon's plugin discovery all unconditionally import
# `genie`, and no `genie` release on PyPI has both a working dependency
# tree and a musllinux wheel simultaneously (26.7 has the wheel but a
# broken `genie.metaparser` dependency; 25.x and earlier are glibc-only
# manylinux wheels). This is a real, upstream packaging gap, not something
# fixable by different bundling here -- see Platform-Status-and-Pending-
# Items.md §2 for the current state of pyats_verify.
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=<token>
#   pipelines/scripts/cml-provision-py-env.sh <lab_name> <node_label>
#
# Idempotent: skips the whole rebuild-and-transfer cycle if
# /home/cisco/py-env/venv/bin/ansible already exists on the jump host.
set -euo pipefail

LAB_NAME="${1:?Usage: cml-provision-py-env.sh <lab_name> <node_label>}"
NODE_LABEL="${2:?node_label required}"

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_RELEASE_TAG="20260825"
PYTHON_BUILD="cpython-3.12.14+${PYTHON_RELEASE_TAG}-x86_64_v2-unknown-linux-musl-install_only_stripped.tar.gz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_RELEASE_TAG}/${PYTHON_BUILD}"

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set." >&2
  exit 1
fi

echo "[provision] checking whether the jump host is already provisioned..." >&2
set +e
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "test -x /home/cisco/py-env/venv/bin/ansible" 30
already_provisioned=$?
set -e
if [[ "${already_provisioned}" -eq 0 ]]; then
  echo "[provision] /home/cisco/py-env/venv/bin/ansible already present -- skipping." >&2
  exit 0
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

echo "[provision] downloading portable musl Python..." >&2
curl -sSL -o "${WORK}/python.tar.gz" "${PYTHON_URL}"
mkdir -p "${WORK}/combined"
tar xzf "${WORK}/python.tar.gz" -C "${WORK}/combined"

echo "[provision] downloading ansible-core + network-connection deps as musllinux wheels..." >&2
mkdir -p "${WORK}/combined/wheels"
pip download --platform musllinux_1_2_x86_64 --python-version 3.12 --implementation cp --abi cp312 \
  --only-binary=:all: -d "${WORK}/combined/wheels" \
  ansible-core cryptography paramiko ncclient pynacl

echo "[provision] downloading Ansible collections..." >&2
SCRATCH_VENV="$(mktemp -d)"
python3 -m venv "${SCRATCH_VENV}"
"${SCRATCH_VENV}/bin/pip" install --quiet ansible-core
mkdir -p "${WORK}/combined/collections"
"${SCRATCH_VENV}/bin/ansible-galaxy" collection download cisco.nxos community.hashi_vault \
  -p "${WORK}/combined/collections"
rm -rf "${SCRATCH_VENV}"

echo "[provision] bundling and uploading..." >&2
tar czf "${WORK}/py-env-bundle.tar.gz" -C "${WORK}/combined" python wheels collections
curl -sSk -T "${WORK}/py-env-bundle.tar.gz" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/py-env-bundle.tar.gz"

echo "[provision] pulling bundle onto jump host..." >&2
"${_HERE}/cml-jump-fetch-file.sh" "${LAB_NAME}" "${NODE_LABEL}" "py-env-bundle.tar.gz" "/home/cisco/py-env-bundle.tar.gz" 300
curl -sSk -Q "rm py-env-bundle.tar.gz" "sftp://${CML_USER}:${CML_PASS}@${CML_HOST}/" || true

echo "[provision] extracting and building the venv on the jump host..." >&2
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "mkdir -p /home/cisco/py-env && tar xzf /home/cisco/py-env-bundle.tar.gz -C /home/cisco/py-env && rm -f /home/cisco/py-env-bundle.tar.gz" \
  120

"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "/home/cisco/py-env/python/bin/python3.12 -m venv /home/cisco/py-env/venv && /home/cisco/py-env/venv/bin/pip install --no-index --find-links /home/cisco/py-env/wheels ansible-core cryptography paramiko ncclient pynacl" \
  180

"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "/home/cisco/py-env/venv/bin/ansible-galaxy collection install /home/cisco/py-env/collections/*.tar.gz -p /home/cisco/py-env/venv/ansible_collections" \
  90

echo "[provision] done -- verifying..." >&2
"${_HERE}/cml-jump-relay.sh" "${LAB_NAME}" "${NODE_LABEL}" \
  "/home/cisco/py-env/venv/bin/ansible --version | head -1" \
  30
