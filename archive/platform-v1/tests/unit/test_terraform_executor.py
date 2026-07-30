"""Unit tests for the Terraform executor — Milestone 6A.

No Docker, no real Terraform binary, no real Nautobot/Vault required:
`subprocess.run`, `NautobotClient`, and the Vault HTTP read are all mocked,
exactly the same "mock the I/O boundary" discipline used throughout M1-M5
(httpx.MockTransport for HTTP, tmp_path SQLite for the Execution Store).
"""

from __future__ import annotations

import subprocess
import uuid
from unittest.mock import patch

import pytest

import app.terraform_executor as te_module
from app.execution_store import ExecutionStore
from app.terraform_executor import execute_deployment
from canonical_intent import ApprovalState, DeploymentContext, Environment, ExecutionState, LifecycleState


def _new_deployment(store: ExecutionStore) -> uuid.UUID:
    context = DeploymentContext(
        intent_id=uuid.uuid4(),
        engineering_version=1,
        requester="tester",
        entry_point="cli",
        environment=Environment.LAB,
        approval_state=ApprovalState.NONE_REQUIRED,
    )
    state = ExecutionState(deployment_id=context.deployment_id, lifecycle_state=LifecycleState.ACCEPTED, desired_version=1)
    store.create(context, state)
    return context.deployment_id


@pytest.fixture(autouse=True)
def _configure_module(tmp_path, monkeypatch):
    monkeypatch.setattr(te_module, "NAUTOBOT_TOKEN", "test-nautobot-token")
    monkeypatch.setattr(te_module, "VAULT_TOKEN", "test-vault-token")
    monkeypatch.setattr(te_module, "NETASCODE_OUTPUT_DIR", tmp_path / "netascode")
    monkeypatch.setattr(te_module, "TERRAFORM_DIR", tmp_path / "terraform")


def _mock_generator(monkeypatch) -> None:
    monkeypatch.setattr(
        te_module.NautobotClient,
        "get_tenants",
        lambda self: [{"name": "ACI:web-tenant", "description": "", "vrfs": [{"name": "web-vrf", "description": ""}]}],
    )
    monkeypatch.setattr(te_module.NautobotClient, "get_prefixes", lambda self: [])


def _mock_vault(monkeypatch, ok: bool = True) -> None:
    class _FakeResponse:
        def raise_for_status(self) -> None:
            if not ok:
                raise RuntimeError("vault unreachable")

        def json(self) -> dict:
            return {"data": {"data": {"aci_url": "https://apic", "aci_username": "admin", "aci_password": "secret"}}}

    monkeypatch.setattr(te_module.httpx, "get", lambda *a, **k: _FakeResponse())


def test_execute_deployment_success_transitions_to_deploying_only(tmp_path, monkeypatch) -> None:
    """On success, execute_deployment() owns ACCEPTED->DEPLOYING only -- it never touches VALIDATING/STABLE itself."""
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    _mock_generator(monkeypatch)
    _mock_vault(monkeypatch)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        execute_deployment(store, deployment_id)

    state = store.get_state(deployment_id)
    assert state.lifecycle_state == LifecycleState.DEPLOYING


def test_execute_deployment_runs_init_plan_apply_in_order(tmp_path, monkeypatch) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    _mock_generator(monkeypatch)
    _mock_vault(monkeypatch)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        execute_deployment(store, deployment_id)

    subcommands = [call.args[0][1] for call in mock_run.call_args_list]
    assert subcommands == ["init", "plan", "apply"]


def test_execute_deployment_writes_netascode_yaml_before_terraform_runs(tmp_path, monkeypatch) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    _mock_generator(monkeypatch)
    _mock_vault(monkeypatch)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        execute_deployment(store, deployment_id)

    var_file = tmp_path / "netascode" / "tenants.yaml"
    assert var_file.exists()
    assert "web-tenant" in var_file.read_text(encoding="utf-8")


def test_execute_deployment_transitions_to_failed_on_nonzero_exit(tmp_path, monkeypatch) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    _mock_generator(monkeypatch)
    _mock_vault(monkeypatch)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="apply failed")
        execute_deployment(store, deployment_id)

    state = store.get_state(deployment_id)
    assert state.lifecycle_state == LifecycleState.FAILED


def test_execute_deployment_transitions_to_failed_on_timeout(tmp_path, monkeypatch) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    _mock_generator(monkeypatch)
    _mock_vault(monkeypatch)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="terraform", timeout=120)):
        execute_deployment(store, deployment_id)

    state = store.get_state(deployment_id)
    assert state.lifecycle_state == LifecycleState.FAILED


def test_execute_deployment_transitions_to_failed_when_nautobot_token_missing(tmp_path, monkeypatch) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    monkeypatch.setattr(te_module, "NAUTOBOT_TOKEN", None)

    execute_deployment(store, deployment_id)

    assert store.get_state(deployment_id).lifecycle_state == LifecycleState.FAILED


def test_execute_deployment_transitions_to_failed_when_vault_token_missing(tmp_path, monkeypatch) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    _mock_generator(monkeypatch)
    monkeypatch.setattr(te_module, "VAULT_TOKEN", None)

    execute_deployment(store, deployment_id)

    assert store.get_state(deployment_id).lifecycle_state == LifecycleState.FAILED


def test_execute_deployment_transitions_to_failed_when_vault_unreachable(tmp_path, monkeypatch) -> None:
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    _mock_generator(monkeypatch)
    _mock_vault(monkeypatch, ok=False)

    execute_deployment(store, deployment_id)

    assert store.get_state(deployment_id).lifecycle_state == LifecycleState.FAILED


def test_execute_deployment_never_raises_to_caller(tmp_path, monkeypatch) -> None:
    """No Terraform-specific exception handling should ever be needed in main.py (ADR-004)."""
    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id = _new_deployment(store)
    monkeypatch.setattr(te_module, "NAUTOBOT_TOKEN", None)

    execute_deployment(store, deployment_id)  # must not raise


def test_concurrent_deployments_never_run_terraform_simultaneously(tmp_path, monkeypatch) -> None:
    """Two concurrent execute_deployment() calls must serialize their terraform

    init/plan/apply calls (_TERRAFORM_EXECUTION_LOCK) -- platform/terraform/aci/
    is one shared module with one shared local state file for the whole domain.
    """
    import threading
    import time as time_module

    store = ExecutionStore(path=tmp_path / "db.sqlite")
    deployment_id_1 = _new_deployment(store)
    deployment_id_2 = _new_deployment(store)
    _mock_generator(monkeypatch)
    _mock_vault(monkeypatch)

    active = 0
    max_concurrent = 0
    lock = threading.Lock()

    def _fake_run(*args, **kwargs):
        nonlocal active, max_concurrent
        with lock:
            active += 1
            max_concurrent = max(max_concurrent, active)
        time_module.sleep(0.05)  # long enough for a real overlap to be observed if unsynchronized
        with lock:
            active -= 1
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=_fake_run):
        t1 = threading.Thread(target=execute_deployment, args=(store, deployment_id_1))
        t2 = threading.Thread(target=execute_deployment, args=(store, deployment_id_2))
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

    assert max_concurrent == 1, "terraform commands from two deployments ran concurrently -- the lock did not serialize them"
    assert store.get_state(deployment_id_1).lifecycle_state == LifecycleState.DEPLOYING
    assert store.get_state(deployment_id_2).lifecycle_state == LifecycleState.DEPLOYING
