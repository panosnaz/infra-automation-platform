---
title: "Platform v1 Archive"
description: "Superseded Platform v1 code (FastAPI Platform API + CanonicalIntent), preserved for history, not deleted."
---

# Platform v1 Archive

This directory holds Platform v1 code that [ADR-016](../../knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md) marked superseded by Platform v2 (Nautobot + generator + GitLab CI Execution Framework + MCP Server). It is preserved for history via `git mv` (never deleted), matching this repo's established convention for superseded material (see `knowledge/adr/archive/`, `knowledge/architecture/archive/`).

**Archived 2026-07-30, after ADR-016/017/018/019/020/021 were all built and the current architecture had zero further use for this code.**

## What's here

| Path | Was | Why archived |
|---|---|---|
| `platform/canonical_intent/` | Contract #1's Pydantic reference implementation -- the `CanonicalIntent`/`DeploymentContext`/`ExecutionState` model | ADR-018 explicitly rejected an MCP-owned intent schema in favor of NetAsCode YAML as the one authoritative intent artifact. This module is that rejected design's executable form. |
| `docker/platform-api/app/` | The legacy FastAPI Platform API (`main.py`, `nautobot_store.py`, `execution_store.py`, `terraform_executor.py`, `approval_workflow.py`, `technical_policy.py`, `aci_materializer.py`, `audit_log.py`, `knowledge_capture.py`, `validation_stub.py`, `terraform_stub.py`) | Replaced, not migrated, by the GitLab CI Execution Framework + MCP Server (ADR-016/017/018). |
| `docker/platform-api/Dockerfile`, `requirements*.txt`, `.dockerignore`, `data/` | Build/runtime artifacts for the above | Same reason -- the container is no longer part of the running stack. `docker/platform-api/docker-compose.yml` now defines only the `opa` service, which remains live and in active use by the Execution Framework's Policy stage. |
| `tests/unit/test_terraform_executor.py`, `test_execution_store.py`, `test_technical_policy.py`, `test_deployment_stubs.py`, `test_approval_workflow.py`, `test_knowledge_capture.py`, `test_aci_materializer.py` | Unit tests for the above | Tested code that no longer exists in the live architecture. None of these were wired into `.gitlab-ci.yml` -- their presence in `tests/unit/` inflated the apparent test count without contributing real CI signal. |

## What's still live and was deliberately NOT archived

- `docker/platform-api/policy/` (both `cisco_aci/` and `vxlan_evpn/` OPA policies) -- actively used by the GitLab CI `policy_check` job today. Still lives at this path; only the FastAPI app that used to share the directory was archived.
- `tests/unit/test_transformer.py` -- tests the current `platform/python/generator/transformer.py`, unrelated to this legacy code.
- `tests/unit/conftest.py` -- kept, with its `canonical_intent`/`docker/platform-api` `sys.path` entries removed (no longer needed) and only the `platform/python` entry retained (still needed for `test_transformer.py`'s `import generator`).

## If you need the old code

`git log --follow` on any path under `archive/platform-v1/` will show its full history before the move. Nothing here should be extended or reused going forward -- if a piece of logic looks reusable (e.g. `aci_materializer.py`'s domain-write pattern), treat it as a reference for reimplementing in the current architecture (MCP tools, generator), not as code to import.
