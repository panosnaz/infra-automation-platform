"""pyATS validation: EVPN fabric features are enabled on the real Nexus 9000v
devices, matching the generated NetAsCode YAML's expectations.

Independent of Terraform and Ansible -- connects directly to each device's
real NX-API JSON-RPC endpoint (POST /ins with an ins_api envelope) via plain
`requests`, not pyATS' rest.connector (confirmed via its source that the
`nxos` plugin targets a different, ACI-style DN-based REST API -- see
testbed.yml's own comment). Read-only: only issues `show` (cli_show) queries,
never `configure terminal` (cli_conf).

All 4 real Nexus 9000v nodes (DC1-Leaf, DC1-BGW, DC2-Leaf, DC2-BGW) were
confirmed live via this exact query shape this session (ADR-021 SS6/SS10/SS11).
These hosts are only reachable from inside the CML lab network (via the
alpine jump host) -- NOT from wherever this pyATS job actually runs (see
testbed.yml's own comment and knowledge/runbooks/CML-EVPN-Lab-Jump-Host.md).

Run via (from inside the jump host, once Python/pyATS are available there,
or from any host with a route to the lab's OOB network):
    export VAULT_ADDR=http://localhost:8200
    export VAULT_TOKEN=<token>
    source tests/pyats/evpn/scripts/load-vault-env.sh
    pyats run job tests/pyats/evpn/job.py --testbed-file tests/pyats/evpn/testbed.yml
"""

from __future__ import annotations

import logging

import requests
import urllib3
from pyats import aetest

log = logging.getLogger(__name__)

# nxos_feature.fabric (platform/terraform/evpn/main.tf) enables these 5
# features on every fabric device. Only 3 show up as distinct rows in this
# NX-OS version's `show feature` table (confirmed live this session,
# ADR-021 SS10/SS11) -- `evpn`/`vn_segment` don't appear as separate feature
# entries at all here, so they are deliberately not asserted on individually.
_EXPECTED_ENABLED_FEATURES = ["bgp", "interface-vlan", "nve"]

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


class CommonSetup(aetest.CommonSetup):
    @aetest.subsection
    def load_devices(self, testbed):
        self.parent.parameters["device_names"] = list(testbed.devices.keys())
        self.parent.parameters["testbed"] = testbed


class VerifyFabricFeatures(aetest.Testcase):
    """Assert bgp/interface-vlan/nve are enabled on every real EVPN fabric
    device, via a direct NX-API query -- not Terraform's own state."""

    @aetest.test
    def query_and_verify_each_device(self, testbed, device_names):
        failures: dict[str, str] = {}
        for name in device_names:
            device = testbed.devices[name]
            nxapi_url = device.custom["nxapi_url"]
            username = device.custom["username"]
            password = device.custom["password"]
            try:
                body = _query_show_feature(nxapi_url, username, password)
                enabled = _enabled_feature_names(body)
            except Exception as exc:  # noqa: BLE001 - report per-device, don't abort the whole run
                failures[name] = f"query failed: {exc}"
                continue
            log.info("%s: enabled features relevant to EVPN: %s", name, enabled & set(_EXPECTED_ENABLED_FEATURES))
            missing = [f for f in _EXPECTED_ENABLED_FEATURES if f not in enabled]
            if missing:
                failures[name] = f"feature(s) not enabled: {missing}"

        if failures:
            self.failed(f"EVPN fabric feature verification failed: {failures}")
        self.passed(f"All {len(device_names)} device(s) have bgp/interface-vlan/nve enabled: {device_names}")


class CommonCleanup(aetest.CommonCleanup):
    @aetest.subsection
    def no_op(self):
        """No persistent connections were opened (plain `requests` per call),
        so there is nothing to disconnect."""


if __name__ == "__main__":
    aetest.main()
