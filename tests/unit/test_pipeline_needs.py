"""Every pipeline job after generate_nac must plan, apply and verify the YAML
generate_nac produced in THIS pipeline -- not the copy in the git checkout.

GitLab CI `needs:` is not transitive: a job downloads artifacts only from
the jobs listed in its own `needs:`, and otherwise reads the file from the
checkout. generate_nac commits its output with [skip ci], so the checkout
holds whatever the PREVIOUS pipeline generated. Found live 2026-10-18:
pipeline 67's validate_nac and policy_check checked a YAML containing a new
VRF, while terraform_plan (needs: policy_check, which publishes no artifact)
planned the stale checkout and reported "No changes".

The rule is default-on: a new job inherits it unless it is exempted here by
name, with the reason it does not read the YAML.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_COMMON = _REPO / "pipelines" / "includes" / "common.gitlab-ci.yml"
_PIPELINES = {
    "aci": (_REPO / "pipelines" / "aci.gitlab-ci.yml", "generate_nac"),
    "evpn": (_REPO / "pipelines" / "evpn.gitlab-ci.yml", "evpn_generate_nac"),
}
EXEMPT = {
    # reachability probe through the jump host; reads no intent
    "evpn_lab_connectivity_check",
}


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!reference", lambda loader, node: loader.construct_sequence(node))


def _load(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)


def _jobs(pipeline: Path) -> dict[str, dict]:
    """Concrete jobs with `extends` resolved against the shared templates."""
    templates = {k: v for k, v in _load(_COMMON).items() if k.startswith(".")}
    jobs = {}
    for name, body in _load(pipeline).items():
        if name.startswith(".") or name in ("include", "variables", "stages") or not isinstance(body, dict):
            continue
        merged = dict(templates.get(body.get("extends", ""), {}))
        merged.update(body)
        jobs[name] = merged
    return jobs


def _publishes_yaml(job: dict) -> bool:
    return "${NETASCODE_YAML}" in ((job.get("artifacts") or {}).get("paths") or [])


def _downloads_from(job: dict) -> set[str]:
    out = set()
    for need in job.get("needs") or []:
        if isinstance(need, str):
            out.add(need)
        elif need.get("artifacts", True):
            out.add(need["job"])
    return out


@pytest.mark.parametrize("domain", sorted(_PIPELINES))
def test_every_job_after_generate_reads_this_pipelines_yaml(domain):
    path, generate = _PIPELINES[domain]
    jobs = _jobs(path)
    assert _publishes_yaml(jobs[generate])
    producers = {name for name, job in jobs.items() if _publishes_yaml(job)}
    stale = sorted(name for name, job in jobs.items()
                   if name != generate and name not in EXEMPT and not _downloads_from(job) & producers)
    assert stale == [], f"{domain}: these jobs would read the stale git copy of NETASCODE_YAML: {stale}"


def test_exemptions_name_real_jobs():
    every = set().union(*(_jobs(p) for p, _ in _PIPELINES.values()))
    assert EXEMPT <= every
