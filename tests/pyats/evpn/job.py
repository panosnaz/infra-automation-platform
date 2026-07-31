"""pyATS job — runs the EVPN validation test scripts against the testbed.

Usage:
    export VAULT_ADDR=http://localhost:8200
    export VAULT_TOKEN=<token>
    source tests/pyats/evpn/scripts/load-vault-env.sh
    pyats run job tests/pyats/evpn/job.py --testbed-file tests/pyats/evpn/testbed.yml
"""

from pathlib import Path

_HERE = Path(__file__).resolve().parent


def main(runtime):
    runtime.tasks.run(testscript=str(_HERE / "test_evpn_features.py"))
