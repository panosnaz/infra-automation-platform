#!/usr/bin/env bash
# Execution Framework -- Stage 2 (Validation), determinism half, Milestone 2.
#
# Confirms the Nautobot -> NetAsCode generator produces byte-identical
# output across two consecutive runs against the same Nautobot state.
# Milestone 2's gate requires this be proven empirically, not assumed --
# the generator writes with sort_keys=False, so determinism depends on
# Nautobot returning objects in stable order, not on the generator sorting
# them itself.
#
# Usage: check_determinism.sh <run1-copy-path> <netascode-yaml-path>
set -euo pipefail

RUN1_COPY="$1"
CURRENT="$2"

if ! diff "${RUN1_COPY}" "${CURRENT}"; then
  echo "FAIL: generator output is not deterministic across two consecutive runs against the same Nautobot state" >&2
  exit 1
fi

echo "OK -- generator output is byte-identical across two consecutive runs"
