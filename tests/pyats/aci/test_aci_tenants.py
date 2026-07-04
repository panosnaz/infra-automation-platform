"""pyATS validation: ACI tenants match the generated NetAsCode YAML.

Independent of Terraform and Ansible — connects directly to the APIC REST API
via pyATS' generic rest.connector (there is no dedicated ACI connector class
in this pyATS distribution beyond rest.connector.libs.apic; see
docs/01-Vision/01-Current-State.md Open Question Q3, resolved 2026-07-04).

Run via:
    export VAULT_ADDR=http://localhost:8200
    export VAULT_TOKEN=<token>
    source tests/pyats/aci/scripts/load-vault-env.sh
    pyats run job tests/pyats/aci/job.py --testbed-file tests/pyats/aci/testbed.yml
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pyats import aetest

log = logging.getLogger(__name__)

# platform/netascode/aci/tenants.yaml — the same generator output Terraform
# and Ansible consume.
_NETASCODE_YAML = Path(__file__).resolve().parents[3] / "platform" / "netascode" / "aci" / "tenants.yaml"


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
        expected = [t["name"] for t in data["apic"]["tenants"]]
        log.info("Expected tenants from NetAsCode YAML: %s", expected)
        self.parent.parameters["expected_tenants"] = expected


class VerifyTenants(aetest.Testcase):
    """Assert every tenant in the NetAsCode YAML exists in ACI. Read-only —
    only issues GET requests, never creates/modifies/deletes anything."""

    @aetest.test
    def query_aci_tenants(self, apic):
        response = apic.rest.get("api/class/fvTenant.json")
        self.parent.parameters["actual_tenants"] = [
            item["fvTenant"]["attributes"]["name"] for item in response.get("imdata", [])
        ]
        log.info("Tenants found in ACI: %s", self.parent.parameters["actual_tenants"])

    @aetest.test
    def assert_tenants_present(self, expected_tenants, actual_tenants):
        missing = [t for t in expected_tenants if t not in actual_tenants]
        if missing:
            self.failed(f"Tenant(s) not found in ACI: {missing}")
        self.passed(f"All {len(expected_tenants)} expected tenant(s) verified present: {expected_tenants}")


class CommonCleanup(aetest.CommonCleanup):
    @aetest.subsection
    def disconnect(self, apic):
        if apic.is_connected(alias="rest"):
            apic.disconnect(alias="rest")


if __name__ == "__main__":
    aetest.main()
