#!/usr/bin/env python3
"""Execution Framework -- Stage 7 (Knowledge Capture).

Appends one structured record per pipeline run. Reuses the generic
append-only JSONL primitive already proven by
docker/platform-api/app/jsonl_writer.py (ADR-009) -- reimplemented here
rather than imported, since this script runs inside a CI job container with
no access to the platform-api application package, not because the pattern
changed.

Usage:
    python3 capture_knowledge.py <output-path.jsonl>

Reads pipeline/commit context from GitLab's predefined CI/CD variables.

Note: this record does not yet attempt to capture pass/fail of the overall
pipeline -- GitLab has no single predefined variable exposing that inside a
job script (CI_JOB_STATUS only reflects the *current* job, in an
after_script). Accurately aggregating prior stage results (e.g. by querying
the GitLab API for this pipeline's job statuses) is explicit Milestone 4
scope (knowledge/architecture/Execution-Framework.md §6) -- for now, GitLab's
own pipeline status remains the authoritative pass/fail record, queryable
separately; this record captures *what ran*, not *whether it passed*.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str))
        f.write("\n")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: capture_knowledge.py <output-path.jsonl>", file=sys.stderr)
        return 2

    output_path = sys.argv[1]

    record = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_id": os.environ.get("CI_PIPELINE_ID"),
        "pipeline_url": os.environ.get("CI_PIPELINE_URL"),
        "commit_sha": os.environ.get("CI_COMMIT_SHA"),
        "job_id": os.environ.get("CI_JOB_ID"),
        "operator": os.environ.get("GITLAB_USER_LOGIN", "unknown"),
        "domain_id": os.environ.get("POLICY_DOMAIN"),
        "netascode_yaml": os.environ.get("NETASCODE_YAML"),
        "environment": os.environ.get("CI_ENVIRONMENT_NAME", "lab"),
    }

    append_jsonl(Path(output_path), record)
    print(f"Knowledge record appended to {output_path}: {json.dumps(record)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
