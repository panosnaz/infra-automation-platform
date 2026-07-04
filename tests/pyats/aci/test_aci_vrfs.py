"""pyATS validation: ACI VRFs match the generated NetAsCode YAML.

Same pattern as test_aci_tenants.py — read-only, connects via
rest.connector.libs.apic, independent of Terraform and Ansible.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from pyats import aetest

log = logging.getLogger(__name__)

_NETASCODE_YAML = Path(__file__).resolve().parents[3] / "platform" / "netascode" / "aci" / "tenants.yaml"

# ACI VRF (fvCtx) distinguished names look like "uni/tn-<tenant>/ctx-<vrf>".
_VRF_DN_RE = re.compile(r"^uni/tn-(?P<tenant>[^/]+)/ctx-(?P<vrf>.+)$")


class CommonSetup(aetest.CommonSetup):
    @aetest.subsection
    def connect(self, testbed):
        device = testbed.devices["apic"]
        # Set the parameter before connecting so CommonCleanup can still
        # attempt a disconnect even if connect() raises.
        self.parent.parameters["apic"] = device
        device.connect(via="rest", alias="rest")

    @aetest.subsection
    def load_netascode_yaml(self):
        with open(_NETASCODE_YAML, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        expected = [
            (tenant["name"], vrf["name"])
            for tenant in data["apic"]["tenants"]
            for vrf in tenant.get("vrfs", [])
        ]
        log.info("Expected tenant/VRF pairs from NetAsCode YAML: %s", expected)
        self.parent.parameters["expected_vrfs"] = expected


class VerifyVrfs(aetest.Testcase):
    """Assert every (tenant, VRF) pair in the NetAsCode YAML exists in ACI.
    Read-only — only issues GET requests, never creates/modifies/deletes
    anything."""

    @aetest.test
    def query_aci_vrfs(self, apic):
        response = apic.rest.get("api/class/fvCtx.json")
        actual = []
        for item in response.get("imdata", []):
            dn = item["fvCtx"]["attributes"]["dn"]
            match = _VRF_DN_RE.match(dn)
            if match:
                actual.append((match.group("tenant"), match.group("vrf")))
        self.parent.parameters["actual_vrfs"] = actual
        log.info("Tenant/VRF pairs found in ACI: %s", actual)

    @aetest.test
    def assert_vrfs_present(self, expected_vrfs, actual_vrfs):
        missing = [pair for pair in expected_vrfs if pair not in actual_vrfs]
        if missing:
            self.failed(f"Tenant/VRF pair(s) not found in ACI: {missing}")
        self.passed(f"All {len(expected_vrfs)} expected VRF(s) verified present: {expected_vrfs}")


class CommonCleanup(aetest.CommonCleanup):
    @aetest.subsection
    def disconnect(self, apic):
        if apic.is_connected(alias="rest"):
            apic.disconnect(alias="rest")


if __name__ == "__main__":
    aetest.main()
