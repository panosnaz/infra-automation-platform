#!/usr/bin/env python3
"""Execution Framework -- Stage 6 (Verification), Write Results half.

Writes the pipeline's validation outcome back to Nautobot as custom fields
on each verified Tenant object -- closing the loop back to the Source of
Truth (Platform-v2-Reference-Architecture.md §6's "Write Results" stage).

This does not re-validate anything; it only records what pyATS (the
"pyats_verify" job in this same pipeline) already found, by querying that
job's actual status via the GitLab API -- GitLab exposes no predefined
variable for a *sibling* job's status inside a script, so this queries it
directly rather than guessing or requiring a manually-plumbed-through value.

Usage:
    python3 write_results.py <path-to-tenants.yaml>

Reads NAUTOBOT_URL, NAUTOBOT_TOKEN, and GitLab's predefined CI/CD variables
(CI_API_V4_URL, CI_PROJECT_ID, CI_PIPELINE_ID, CI_JOB_TOKEN, CI_PIPELINE_ID,
CI_PIPELINE_URL) from the environment.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import yaml

NAUTOBOT_URL = os.environ.get("NAUTOBOT_URL", "http://localhost:8080").rstrip("/")
NAUTOBOT_TOKEN = os.environ.get("NAUTOBOT_TOKEN", "")


def _nautobot_api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{NAUTOBOT_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Token {NAUTOBOT_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _pyats_verify_status() -> str:
    """Query this pipeline's own jobs for pyats_verify's actual status.

    Uses PIPELINE_STATUS_TOKEN (a dedicated, read_api-scoped project access
    token) rather than CI_JOB_TOKEN -- confirmed via a live pipeline run that
    this GitLab instance's Pipeline Jobs API returns 404 for JOB-TOKEN auth,
    while the same request succeeds with a PRIVATE-TOKEN. Same least-privilege
    dedicated-token pattern already used for GIT_PUSH_TOKEN (Milestone 2).
    """
    api_url = os.environ.get("CI_API_V4_URL")
    project_id = os.environ.get("CI_PROJECT_ID")
    pipeline_id = os.environ.get("CI_PIPELINE_ID")
    status_token = os.environ.get("PIPELINE_STATUS_TOKEN")

    if not all([api_url, project_id, pipeline_id, status_token]):
        return "unknown"

    req = urllib.request.Request(
        f"{api_url}/projects/{project_id}/pipelines/{pipeline_id}/jobs?per_page=100",
        headers={"PRIVATE-TOKEN": status_token},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            jobs = json.loads(resp.read())
    except Exception as exc:  # pragma: no cover -- best-effort, never fatal
        print(f"WARNING: could not query pyats_verify status: {exc}", file=sys.stderr)
        return "unknown"

    pyats_jobs = [j for j in jobs if j["name"] == "pyats_verify"]
    if not pyats_jobs:
        return "unknown"
    return "stable" if pyats_jobs[0]["status"] == "success" else "failed"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: write_results.py <path-to-tenants.yaml>", file=sys.stderr)
        return 2

    netascode_yaml = sys.argv[1]
    status = _pyats_verify_status()

    with open(netascode_yaml, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    tenant_names = [t["name"] for t in data.get("apic", {}).get("tenants", [])]

    custom_fields = {
        "last_pipeline_id": int(os.environ["CI_PIPELINE_ID"]) if os.environ.get("CI_PIPELINE_ID") else None,
        "last_pipeline_url": os.environ.get("CI_PIPELINE_URL"),
        "last_validated_at": datetime.now(timezone.utc).isoformat(),
        "validation_status": status,
    }

    updated, missing = [], []
    for name in tenant_names:
        # The generator strips the "ACI:" namespace prefix nautobot-ssot adds
        # when writing NetAsCode YAML (see generator/transformer.py) -- add
        # it back to find the actual Nautobot object. Not every tenant is
        # guaranteed to have this prefix (e.g. a tenant authored directly via
        # forward intent, never through SSoT), so fall back to the bare name
        # if the prefixed lookup finds nothing.
        result = _nautobot_api("GET", f"/api/tenancy/tenants/?name={urllib.parse.quote('ACI:' + name)}")
        matches = [t for t in result.get("results", []) if t["name"] == f"ACI:{name}"]
        if not matches:
            result = _nautobot_api("GET", f"/api/tenancy/tenants/?name={urllib.parse.quote(name)}")
            matches = [t for t in result.get("results", []) if t["name"] == name]
        if not matches:
            missing.append(name)
            continue

        tenant_id = matches[0]["id"]
        try:
            _nautobot_api("PATCH", f"/api/tenancy/tenants/{tenant_id}/", {"custom_fields": custom_fields})
            updated.append(name)
        except urllib.error.HTTPError as exc:
            print(f"WARNING: failed to write results for tenant '{name}': {exc}", file=sys.stderr)

    print(f"Write Results: updated {len(updated)} tenant(s) in Nautobot with status='{status}': {updated}")
    if missing:
        print(f"WARNING: {len(missing)} tenant(s) from the YAML were not found in Nautobot: {missing}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
