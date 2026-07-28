#!/usr/bin/env python3
"""Execution Framework -- Stage 7 (Knowledge Capture).

Appends one structured record per pipeline run to two places:
  1. A local artifact path (for this pipeline run's own GitLab CI artifacts).
  2. A persistent, growing JSONL log in MinIO (S3-compatible) -- this is the
     actual "knowledge/operational log" Milestone 2's plan referred to;
     GitLab CI artifacts alone are ephemeral per-run files, not an
     accumulating log, so persistence needs an external store. MinIO was
     already provisioned in Phase 1 for exactly this purpose (see
     knowledge/architecture/Platform-v2-Reference-Architecture.md §3.2).

Reuses the generic append-only JSONL primitive already proven by
docker/platform-api/app/jsonl_writer.py (ADR-009) -- reimplemented here
rather than imported, since this script runs inside a CI job container with
no access to the platform-api application package, not because the pattern
changed.

Usage:
    python3 capture_knowledge.py <local-output-path.jsonl> <minio-bucket> <minio-object-key>

Determines overall pipeline pass/fail by querying this pipeline's own job
statuses via the GitLab API (using CI_JOB_TOKEN, automatically available and
scoped to only this project) -- GitLab exposes no single predefined variable
for "did the whole pipeline pass" inside a job script, so this queries it
directly rather than guessing.

Reads pipeline/commit context from GitLab's predefined CI/CD variables, plus
MINIO_ENDPOINT/MINIO_ROOT_USER/MINIO_ROOT_PASSWORD for the MinIO upload.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.client import Config


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str))
        f.write("\n")


def _determine_pipeline_status() -> str:
    """Query this pipeline's own jobs via the GitLab API to determine
    overall pass/fail -- excludes this job itself (still running) and
    treats any failed/canceled sibling job as an overall failure.

    Uses PIPELINE_STATUS_TOKEN (a dedicated, read_api-scoped project access
    token) rather than CI_JOB_TOKEN -- confirmed via a live pipeline run that
    this GitLab instance's Pipeline Jobs API returns 404 for JOB-TOKEN auth,
    while the same request succeeds with a PRIVATE-TOKEN.
    """
    api_url = os.environ.get("CI_API_V4_URL")
    project_id = os.environ.get("CI_PROJECT_ID")
    pipeline_id = os.environ.get("CI_PIPELINE_ID")
    status_token = os.environ.get("PIPELINE_STATUS_TOKEN")
    this_job_id = os.environ.get("CI_JOB_ID")

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
        print(f"WARNING: could not query pipeline job statuses: {exc}", file=sys.stderr)
        return "unknown"

    other_jobs = [j for j in jobs if str(j["id"]) != str(this_job_id)]
    bad = [j for j in other_jobs if j["status"] in ("failed", "canceled")]
    return "failed" if bad else "success"


def _append_to_minio(bucket: str, key: str, record: dict) -> None:
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.environ.get("MINIO_ROOT_USER")
    secret_key = os.environ.get("MINIO_ROOT_PASSWORD")
    if not (access_key and secret_key):
        print("WARNING: MINIO_ROOT_USER/MINIO_ROOT_PASSWORD not set -- skipping MinIO persistence", file=sys.stderr)
        return

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

    try:
        existing = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    except s3.exceptions.NoSuchKey:
        existing = ""
    except Exception as exc:
        print(f"WARNING: could not fetch existing MinIO object {bucket}/{key}: {exc}", file=sys.stderr)
        existing = ""

    updated = existing + json.dumps(record, default=str) + "\n"
    s3.put_object(Bucket=bucket, Key=key, Body=updated.encode("utf-8"))
    print(f"Knowledge record appended to persistent log s3://{bucket}/{key} ({len(updated.splitlines())} total records)")


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: capture_knowledge.py <local-output-path.jsonl> <minio-bucket> <minio-object-key>", file=sys.stderr)
        return 2

    output_path, minio_bucket, minio_key = sys.argv[1], sys.argv[2], sys.argv[3]

    status = _determine_pipeline_status()

    record = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_status": status,
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
    print(f"Knowledge record appended to local artifact {output_path}: {json.dumps(record)}")

    _append_to_minio(minio_bucket, minio_key, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
