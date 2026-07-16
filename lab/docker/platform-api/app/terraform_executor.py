"""Terraform executor — Vertical Slice v0.1, Milestone 6A (Real Terraform Integration).

Execution Plane implementation (Contract #3 §5, ADR-002): replaces
terraform_stub.py's simulated success with the already-proven Phase 3
Terraform module (platform/terraform/aci/), invoked exactly as it was run
by hand during Phase 3 — terraform init -> plan -> apply against a freshly
regenerated NetAsCode YAML.

Per Contract #3 §2's explicit ownership table, the Execution Plane — not
the Workflow Engine — owns ACCEPTED -> DEPLOYING (this function's own entry
transition, moved here from workflow_stub.py during this milestone) and
DEPLOYING -> FAILED (on any execution error). It never touches
VALIDATING/STABLE — that boundary belongs to validation_stub.py, which
gained its own DEPLOYING -> VALIDATING entry transition in the same change.

Only one domain (cisco_aci) exists, so this module calls
platform/python/generate_aci.py's generator functions directly — no
provider abstraction or registry is introduced for a single domain, the
same discipline already applied to app/aci_materializer.py and main.py's
_aci_tenant_name() (Milestone 1 Architecture Validation Review).

On any failure (NetAsCode YAML regeneration, Vault credential read, or
terraform init/plan/apply, including a timeout), this function transitions
DEPLOYING -> FAILED itself and returns normally — it never raises to its
caller. main.py's _run_deployment_pipeline only needs to check the
resulting lifecycle_state; no Terraform-specific exception handling
belongs in the Platform API (ADR-004).

terraform init/plan/apply are serialized within this process via
_TERRAFORM_EXECUTION_LOCK (a plain threading.Lock — FastAPI's
BackgroundTasks for sync routes run in a thread pool, not separate
processes): platform/terraform/aci/ is one shared module with one shared
local state file for the whole domain, and concurrent deployments would
otherwise contend for the same terraform.tfstate. -lock-timeout remains as
a defensive fallback for any external/manual concurrent `terraform`
invocation outside this process.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import httpx
import yaml

from canonical_intent import LifecycleState

from .execution_store import ExecutionStore

NAUTOBOT_URL = os.environ.get("NAUTOBOT_URL", "http://host.docker.internal:8080")
NAUTOBOT_TOKEN = os.environ.get("NAUTOBOT_TOKEN")

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://host.docker.internal:8200")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN")

TERRAFORM_DIR = Path(os.environ.get("TERRAFORM_DIR", "/app/terraform/aci"))
NETASCODE_OUTPUT_DIR = Path(os.environ.get("NETASCODE_OUTPUT_DIR", "/app/netascode/aci"))
_GENERATOR_SRC_DIR = os.environ.get("GENERATOR_SRC_DIR", "/app/generator_src")
_TERRAFORM_TIMEOUT = float(os.environ.get("TERRAFORM_TIMEOUT_SECONDS", "180"))
_TERRAFORM_LOCK_TIMEOUT = os.environ.get("TERRAFORM_LOCK_TIMEOUT", "60s")

# Serializes terraform init/plan/apply within this process -- platform/terraform/aci/
# is one shared module with one shared local state file for the whole domain, and
# concurrent BackgroundTasks (one per in-flight deployment) would otherwise contend
# for the same terraform.tfstate. -lock-timeout above is a defensive fallback for any
# external/manual concurrent `terraform` invocation outside this process; this lock is
# the primary mechanism for concurrency this process itself creates.
_TERRAFORM_EXECUTION_LOCK = threading.Lock()

if _GENERATOR_SRC_DIR not in sys.path:
    sys.path.insert(0, _GENERATOR_SRC_DIR)

from generator.client import NautobotClient  # noqa: E402 - path must be set first
from generator.transformer import build_netascode_yaml  # noqa: E402


class TerraformExecutionError(Exception):
    """Raised internally when Terraform execution fails — always caught within execute_deployment()."""


def execute_deployment(store: ExecutionStore, deployment_id: uuid.UUID) -> None:
    """Execute a real Terraform deployment for `deployment_id`.

    Owns ACCEPTED -> DEPLOYING (start) and DEPLOYING -> FAILED (on error).
    Never touches VALIDATING/STABLE.
    """
    store.transition(deployment_id, LifecycleState.DEPLOYING)

    try:
        var_file = _regenerate_netascode_yaml()
        aci_env = _read_aci_credentials()
        _run_terraform(var_file, aci_env)
    except TerraformExecutionError as exc:
        print(f"WARNING: Terraform execution failed for deployment {deployment_id}: {exc}")
        store.transition(deployment_id, LifecycleState.FAILED)


def _regenerate_netascode_yaml() -> Path:
    """Query Nautobot fresh and write the NetAsCode YAML Terraform will consume.

    Reuses platform/python/generate_aci.py's own library functions
    (NautobotClient, build_netascode_yaml) rather than reimplementing them —
    the generator is not modified by this milestone.
    """
    if not NAUTOBOT_TOKEN:
        raise TerraformExecutionError("NAUTOBOT_TOKEN is not configured on the Platform API.")

    try:
        client = NautobotClient(url=NAUTOBOT_URL, token=NAUTOBOT_TOKEN)
        tenants = client.get_tenants()
        prefixes = client.get_prefixes()
    except Exception as exc:  # noqa: BLE001 - any Nautobot read failure is a deployment failure
        raise TerraformExecutionError(f"Failed to query Nautobot for NetAsCode generation: {exc}") from exc

    data = build_netascode_yaml(tenants=tenants, prefixes=prefixes, include_system_tenants=False)

    NETASCODE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    var_file = NETASCODE_OUTPUT_DIR / "tenants.yaml"
    with var_file.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return var_file


def _read_aci_credentials() -> dict[str, str]:
    """Read ACI credentials from Vault (secret/lab/platform), the same secret

    platform/terraform/aci/scripts/load-vault-creds.sh already reads by hand.
    """
    if not VAULT_TOKEN:
        raise TerraformExecutionError("VAULT_TOKEN is not configured on the Platform API.")

    try:
        response = httpx.get(
            f"{VAULT_ADDR.rstrip('/')}/v1/secret/data/lab/platform",
            headers={"X-Vault-Token": VAULT_TOKEN},
            timeout=5.0,
        )
        response.raise_for_status()
        secret = response.json()["data"]["data"]
    except Exception as exc:  # noqa: BLE001 - any Vault read failure is a deployment failure
        raise TerraformExecutionError(f"Failed to read ACI credentials from Vault: {exc}") from exc

    try:
        return {
            "TF_VAR_aci_url": secret["aci_url"],
            "TF_VAR_aci_username": secret["aci_username"],
            "TF_VAR_aci_password": secret["aci_password"],
            "TF_VAR_aci_insecure": str(secret.get("aci_insecure", "true")).lower(),
        }
    except KeyError as exc:
        raise TerraformExecutionError(f"Vault secret secret/lab/platform is missing required field {exc}") from exc


def _run_terraform(var_file: Path, aci_env: dict[str, str]) -> None:
    env = {**os.environ, **aci_env, "TF_VAR_netascode_yaml_file": str(var_file)}
    lock_timeout = f"-lock-timeout={_TERRAFORM_LOCK_TIMEOUT}"
    with _TERRAFORM_EXECUTION_LOCK:
        for args in (
            ["init", "-input=false", lock_timeout],
            ["plan", "-input=false", lock_timeout],
            ["apply", "-auto-approve", "-input=false", lock_timeout],
        ):
            _run_terraform_command(args, env)


def _run_terraform_command(args: list[str], env: dict[str, str]) -> None:
    try:
        result = subprocess.run(
            ["terraform", *args],
            cwd=TERRAFORM_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=_TERRAFORM_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TerraformExecutionError(f"terraform {' '.join(args)} timed out after {_TERRAFORM_TIMEOUT}s") from exc

    if result.returncode != 0:
        raise TerraformExecutionError(f"terraform {' '.join(args)} failed (exit {result.returncode}): {result.stderr[-2000:]}")
