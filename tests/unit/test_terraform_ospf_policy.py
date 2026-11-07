"""An OSPF interface that names no OSPF Interface Policy must plan.

`policy` on an L3Out's `ospf_interfaces` entry is optional: leaving it out means
the APIC's default OSPF interface policy applies. The MCP tool
`create_ospf_interface` stores it as `"policy": null` when not given, and the
generator passes it through to the YAML. Hand-written YAML may omit the key.

Until 2026-11-07 the module's `inferred_ospf_policies` local read `o.policy`
on the right of `&&`. Terraform 1.9.8 -- the version the pipeline runs -- does
not short-circuit `&&`, so either form failed the whole plan (a missing
attribute, or a null in a string template), blocking every change to the
fabric. Found by the Day-2 ownership evaluation (tenant `evalansible`, stage 4).

The behavioural tests extract the real block from main.tf and evaluate it with
the Terraform on PATH, or the one named by TERRAFORM_BIN. They are skipped
without one. Only Terraform 1.9.x reproduces the original failure: newer
versions short-circuit, so the static test below also pins the shape of the fix.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_MAIN_TF = Path(__file__).resolve().parents[2] / "platform" / "terraform" / "aci" / "main.tf"
_TERRAFORM = os.environ.get("TERRAFORM_BIN") or shutil.which("terraform")


def _block() -> str:
    text = _MAIN_TF.read_text(encoding="utf-8")
    match = re.search(r"^  inferred_ospf_policies = merge\(\[\n.*?^  \]\.\.\.\)\n", text, re.S | re.M)
    assert match, "inferred_ospf_policies not found in main.tf"
    return match.group(0)


def _evaluate(tmp_path: Path, ospf_interfaces: list, defined_policies: dict | None = None) -> dict:
    (tmp_path / "main.tf").write_text(
        'variable "l3outs" { type = any }\n'
        'variable "ospf_interface_policies" { type = any }\n'
        "locals {\n"
        "  l3outs                  = var.l3outs\n"
        "  ospf_interface_policies = var.ospf_interface_policies\n"
        f"{_block()}"
        "}\n"
        'output "inferred" { value = local.inferred_ospf_policies }\n',
        encoding="utf-8",
    )
    (tmp_path / "terraform.tfvars.json").write_text(json.dumps({
        "l3outs": {"t/out": {"tenant_name": "t", "ospf_interfaces": ospf_interfaces}},
        "ospf_interface_policies": defined_policies or {},
    }), encoding="utf-8")
    env = {**os.environ, "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1"}
    run = lambda *a: subprocess.run([_TERRAFORM, *a], cwd=tmp_path, env=env,  # noqa: E731
                                    capture_output=True, text=True, timeout=120)
    res = run("apply", "-auto-approve", "-input=false", "-no-color")
    assert res.returncode == 0, f"plan/apply failed:\n{res.stdout}\n{res.stderr}"
    out = run("output", "-json", "inferred")
    return json.loads(out.stdout)


needs_terraform = pytest.mark.skipif(not _TERRAFORM, reason="no terraform binary (set TERRAFORM_BIN)")
IFACE = {"name": "ospf", "area": "0.0.0.0", "area_type": "regular", "interface_key": "np/ip"}


@needs_terraform
def test_an_interface_without_the_policy_key_plans_and_infers_nothing(tmp_path):
    assert _evaluate(tmp_path, [IFACE]) == {}


@needs_terraform
def test_an_interface_with_a_null_policy_plans_and_infers_nothing(tmp_path):
    """The form the MCP tool writes when no policy is given."""
    assert _evaluate(tmp_path, [{**IFACE, "policy": None}]) == {}


@needs_terraform
def test_a_named_but_undefined_policy_is_still_inferred_as_broadcast(tmp_path):
    assert _evaluate(tmp_path, [{**IFACE, "policy": "p1"}]) == {
        "t/p1": {"tenant_name": "t", "name": "p1", "network_type": "broadcast"}}


@needs_terraform
def test_a_named_and_defined_policy_is_not_inferred_again(tmp_path):
    assert _evaluate(tmp_path, [{**IFACE, "policy": "p1"}], {"t/p1": {"name": "p1"}}) == {}


@needs_terraform
def test_named_and_unnamed_interfaces_together(tmp_path):
    ifaces = [{**IFACE, "policy": "p1"}, {**IFACE, "interface_key": "np/ip2"},
              {**IFACE, "interface_key": "np/ip3", "policy": None}]
    assert list(_evaluate(tmp_path, ifaces)) == ["t/p1"]


def test_the_policy_is_filtered_before_it_is_dereferenced():
    """Guards the fix on Terraform versions that short-circuit `&&` (the
    behavioural tests cannot fail there): interfaces without a policy are
    dropped by an inner `for ... if try(x.policy, null) != null` before
    anything reads `.policy` directly."""
    block = "\n".join(line.split("#", 1)[0] for line in _block().splitlines())
    assert re.search(r"for\s+x\s+in\s+lookup\(l3out,\s*\"ospf_interfaces\",\s*\[\]\)\s*:\s*x\s+if\s+"
                     r"try\(x\.policy,\s*null\)\s*!=\s*null", block), block
    assert "&&" not in block, "a policy check joined with && does not short-circuit on Terraform 1.9.8"
