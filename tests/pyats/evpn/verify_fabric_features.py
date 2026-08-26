"""Plain-Python EVPN fabric feature verification -- no pyATS.

ADR-021 §18/§19: pyATS's CLI/testbed-loading machinery has a hard,
transitive dependency on `genie` (via pyats.clean, rest.connector, and
unicon's plugin discovery), and no `genie` release combines a working
dependency tree with a musllinux wheel -- confirmed via direct tracebacks
in all three code paths, not assumed. A second, glibc-based jump host was
considered and rejected: this lab's CML Personal/Community license caps at
5 concurrent nodes, and the 4 real Nexus 9000v devices + this alpine jump
host already use all 5.

This script is a deliberate, minimal reimplementation of
test_evpn_features.py's actual logic (which never used pyATS's device-
connection framework anyway -- see that file's own docstring) as plain
Python, so it can run on the same already-provisioned jump host
(`/home/cisco/py-env`, no genie/pyATS needed) via the same relay mechanism
used for Terraform and Ansible. test_evpn_features.py itself is left in
place, unchanged, as the reference implementation for if/when the genie
blocker is ever resolved (e.g. a future genie fix, or a licensing change
that allows a second node) -- it is not run by this pipeline today.

Usage:
    export DC1_LEAF_URL=https://172.30.46.220/ins
    export DC1_BGW_URL=https://172.30.46.221/ins
    export DC2_LEAF_URL=https://172.30.46.222/ins
    export DC2_BGW_URL=https://172.30.46.223/ins
    export EVPN_USERNAME=admin
    export EVPN_PASSWORD=cisco
    python3 verify_fabric_features.py

Exit code: 0 if every device has bgp/interface-vlan/nve enabled, 1
otherwise (per-device failures are all reported before exiting, not just
the first one).
"""

from __future__ import annotations

import os
import sys

import requests
import urllib3

# Mirrors test_evpn_features.py exactly -- see that file for the finding
# this list is based on (evpn/vn_segment don't appear as distinct `show
# feature` rows on this NX-OS version, confirmed live, ADR-021 §10/§11).
_EXPECTED_ENABLED_FEATURES = ["bgp", "interface-vlan", "nve"]

_DEVICE_URL_ENV_VARS = {
    "dc1-leaf": "DC1_LEAF_URL",
    "dc1-bgw": "DC1_BGW_URL",
    "dc2-leaf": "DC2_LEAF_URL",
    "dc2-bgw": "DC2_BGW_URL",
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _query_show_feature(nxapi_url: str, username: str, password: str) -> dict:
    """POST a `show feature` cli_show request via NX-API's JSON-RPC envelope
    and return the parsed body. Raises for any transport/auth error."""
    payload = {
        "ins_api": {
            "version": "1.0",
            "type": "cli_show",
            "chunk": "0",
            "sid": "1",
            "input": "show feature",
            "output_format": "json",
        }
    }
    response = requests.post(
        nxapi_url,
        json=payload,
        auth=(username, password),
        verify=False,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _enabled_feature_names(body: dict) -> set[str]:
    rows = body["ins_api"]["outputs"]["output"]["body"]["TABLE_cfcFeatureCtrlTable"]["ROW_cfcFeatureCtrlTable"]
    return {
        row["cfcFeatureCtrlName2"]
        for row in rows
        if row.get("cfcFeatureCtrlOpStatus2") == "enabled"
    }


def main() -> int:
    username = os.environ["EVPN_USERNAME"]
    password = os.environ["EVPN_PASSWORD"]

    failures: dict[str, str] = {}
    for name, url_env_var in _DEVICE_URL_ENV_VARS.items():
        nxapi_url = os.environ[url_env_var]
        try:
            body = _query_show_feature(nxapi_url, username, password)
            enabled = _enabled_feature_names(body)
        except Exception as exc:  # noqa: BLE001 - report per-device, don't abort the whole run
            failures[name] = f"query failed: {exc}"
            continue
        print(f"{name}: enabled features relevant to EVPN: {enabled & set(_EXPECTED_ENABLED_FEATURES)}")
        missing = [f for f in _EXPECTED_ENABLED_FEATURES if f not in enabled]
        if missing:
            failures[name] = f"feature(s) not enabled: {missing}"

    if failures:
        print(f"FAILED: {failures}", file=sys.stderr)
        return 1
    print(f"PASSED: all {len(_DEVICE_URL_ENV_VARS)} device(s) have bgp/interface-vlan/nve enabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
