"""Technical Policy — Vertical Slice v0.1, Milestone 2.

Per ADR-014, evaluates a CanonicalIntent for technical validity/compliance
at SubmitIntent time, before Nautobot persistence. Produces a PolicyDecision
only — it never persists anything and never mutates the intent it's given.

Domain independence (ADR-014 Appendix A): the query path is built from
intent.domain_id alone. This module never knows a rule name — every domain
package exposes exactly one entry point, `decision`, returning a combined
{"allow": bool, "reasons": [...]}"} object. Adding a domain is a new Rego
package; this file never changes.

Failure semantics: OPA unreachable, a non-200 response, or a response
missing/malformed the expected {allow, reasons} shape are ALL treated
identically — TechnicalPolicyUnavailableError, fail closed. `allow` is
never defaulted; a missing or wrong-typed field is unavailable, not allow
and not deny.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

from canonical_intent import CanonicalIntent

OPA_URL = os.environ.get("OPA_URL", "http://opa:8181")


class PolicyDecision(BaseModel):
    allow: bool
    reasons: list[str]
    evaluated_at: datetime  # timezone-aware UTC


class TechnicalPolicyUnavailableError(Exception):
    """Raised when no real decision could be produced at all —

    OPA unreachable, timed out, or returned a missing/malformed result.
    Distinct from a deny: a deny is an actual evaluated outcome; this is
    the absence of one, and must never be conflated with either allow or
    deny by a caller.
    """


class TechnicalPolicyClient:
    def __init__(self, base_url: str = OPA_URL, timeout: float = 5.0, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def evaluate(self, intent: CanonicalIntent) -> PolicyDecision:
        path = f"/v1/data/platform/{intent.domain_id}/decision"
        try:
            response = self._client.post(path, json={"input": intent.model_dump(mode="json")})
        except httpx.HTTPError as exc:
            raise TechnicalPolicyUnavailableError(f"OPA unreachable at {path}: {exc}") from exc

        if response.status_code != 200:
            raise TechnicalPolicyUnavailableError(f"OPA returned {response.status_code} for {path}: {response.text}")

        result = response.json().get("result")
        if not isinstance(result, dict) or not isinstance(result.get("allow"), bool):
            # OPA returns HTTP 200 with an empty/undefined result for an
            # undefined rule or a bundle that failed to compile — this is
            # NOT an error response, so it must be checked explicitly.
            # allow is never defaulted to True (or False) here.
            raise TechnicalPolicyUnavailableError(f"OPA returned a missing or malformed decision for {path}: {response.json()!r}")

        reasons = result.get("reasons", [])
        if not isinstance(reasons, list):
            raise TechnicalPolicyUnavailableError(f"OPA returned a malformed 'reasons' field for {path}: {result!r}")

        return PolicyDecision(allow=result["allow"], reasons=reasons, evaluated_at=datetime.now(timezone.utc))
