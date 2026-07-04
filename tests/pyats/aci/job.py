"""pyATS job — runs the ACI validation test scripts against the testbed.

Usage:
    export VAULT_ADDR=http://localhost:8200
    export VAULT_TOKEN=<token>
    source tests/pyats/aci/scripts/load-vault-env.sh
    pyats run job tests/pyats/aci/job.py --testbed-file tests/pyats/aci/testbed.yml
"""

from pathlib import Path

_HERE = Path(__file__).resolve().parent


def main(runtime):
    runtime.tasks.run(testscript=str(_HERE / "test_aci_tenants.py"))
    runtime.tasks.run(testscript=str(_HERE / "test_aci_vrfs.py"))
