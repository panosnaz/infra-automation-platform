"""Platform API — skeleton FastAPI service.

Per ADR-004 (Platform API as the Unified Platform Interface), this service is
the intended single entry point for all platform consumers. This is a Phase-0
skeleton: it exposes liveness/readiness/version endpoints only.

Explicitly NOT implemented yet (future scope, tracked in
docs/01-Vision/01-Current-State.md):
  - Authentication / authorization (RBAC)
  - Request validation & Canonical Intent normalisation
  - OPA policy enforcement
  - Event Bus publication (IntentReceived, etc.)
  - Any routes that mutate platform state

Do not add business logic here until the Event Bus and Canonical Intent
Model (ADR-006/ADR-007) are implemented — see ADR-004 "Standard Request Flow".
"""

from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Response, status
from pydantic import BaseModel

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://host.docker.internal:8200")
NAUTOBOT_URL = os.environ.get("NAUTOBOT_URL", "http://host.docker.internal:8080")

_HTTP_TIMEOUT = 3.0

app = FastAPI(
    title="Platform API",
    description="Network Platform Engineering Platform — unified platform interface (skeleton).",
    version="0.1.0",
)


class DependencyStatus(BaseModel):
    name: str
    reachable: bool
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    dependencies: list[DependencyStatus]


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe. No external dependencies — always returns 200 if the process is up."""
    return {"status": "ok"}


@app.get("/version", tags=["meta"])
def version() -> dict[str, str]:
    """Report service identity and implementation phase."""
    return {
        "service": "platform-api",
        "version": app.version,
        "phase": "skeleton — interface only, no business logic (see ADR-004)",
    }


@app.get("/readiness", response_model=ReadinessResponse, tags=["meta"])
def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe. Checks connectivity to Vault and Nautobot.

    A dependency is considered "reachable" if it returns any HTTP response,
    including 4xx/5xx — this checks network reachability, not authentication
    or authorization state.
    """
    dependencies = [
        _check_http("vault", f"{VAULT_ADDR.rstrip('/')}/v1/sys/health"),
        _check_http("nautobot", NAUTOBOT_URL.rstrip("/")),
    ]

    all_reachable = all(dep.reachable for dep in dependencies)
    response.status_code = status.HTTP_200_OK if all_reachable else status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if all_reachable else "degraded",
        dependencies=dependencies,
    )


def _check_http(name: str, url: str) -> DependencyStatus:
    try:
        resp = httpx.get(url, timeout=_HTTP_TIMEOUT)
        return DependencyStatus(name=name, reachable=True, detail=f"HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        return DependencyStatus(name=name, reachable=False, detail=str(exc))
