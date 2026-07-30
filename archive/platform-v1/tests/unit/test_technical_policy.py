"""Contract tests for Technical Policy — no Docker, no OPA required.

Uses httpx.MockTransport to exercise the real TechnicalPolicyClient's
request/response handling against fabricated OPA responses, rather than a
throwaway parallel stub implementation — this tests the actual production
parsing/failure-handling code, not a duplicate of it.
"""

from __future__ import annotations

from datetime import timezone

import httpx
import pytest
from canonical_intent import CanonicalIntent

from app.technical_policy import TechnicalPolicyClient, TechnicalPolicyUnavailableError

_VALID_DOMAIN_INTENT = {
    "apic": {
        "tenants": [
            {
                "name": "web-tenant",
                "vrfs": [{"name": "web-vrf"}],
                "bridge_domains": [],
            }
        ]
    }
}


def _intent(name: str = "web-tenant") -> CanonicalIntent:
    domain_intent = {
        "apic": {"tenants": [{"name": name, "vrfs": [{"name": "web-vrf"}], "bridge_domains": []}]}
    }
    return CanonicalIntent(
        engineering_version=1,
        domain_id="cisco_aci",
        domain_intent=domain_intent,
        owner="platform-engineering",
    )


def _client_with_response(json_body: dict, status_code: int = 200) -> TechnicalPolicyClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body)

    return TechnicalPolicyClient(transport=httpx.MockTransport(handler))


def test_allow_decision_is_parsed() -> None:
    client = _client_with_response({"result": {"allow": True, "reasons": []}})
    decision = client.evaluate(_intent())
    assert decision.allow is True
    assert decision.reasons == []
    assert decision.evaluated_at.tzinfo is not None
    assert decision.evaluated_at.tzinfo.utcoffset(decision.evaluated_at) == timezone.utc.utcoffset(None)


def test_deny_decision_is_parsed() -> None:
    client = _client_with_response({"result": {"allow": False, "reasons": ["bad-name"]}})
    decision = client.evaluate(_intent("Bad_Name"))
    assert decision.allow is False
    assert decision.reasons == ["bad-name"]


def test_query_path_uses_domain_id() -> None:
    seen_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"result": {"allow": True, "reasons": []}})

    client = TechnicalPolicyClient(transport=httpx.MockTransport(handler))
    client.evaluate(_intent())
    assert seen_paths == ["/v1/data/platform/cisco_aci/decision"]


def test_missing_result_key_is_unavailable_not_allow() -> None:
    client = _client_with_response({})
    with pytest.raises(TechnicalPolicyUnavailableError):
        client.evaluate(_intent())


def test_malformed_allow_type_is_unavailable() -> None:
    client = _client_with_response({"result": {"allow": "yes", "reasons": []}})
    with pytest.raises(TechnicalPolicyUnavailableError):
        client.evaluate(_intent())


def test_malformed_reasons_type_is_unavailable() -> None:
    client = _client_with_response({"result": {"allow": True, "reasons": "not-a-list"}})
    with pytest.raises(TechnicalPolicyUnavailableError):
        client.evaluate(_intent())


def test_non_200_response_is_unavailable() -> None:
    client = _client_with_response({"error": "internal"}, status_code=500)
    with pytest.raises(TechnicalPolicyUnavailableError):
        client.evaluate(_intent())


def test_connection_error_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = TechnicalPolicyClient(transport=httpx.MockTransport(handler))
    with pytest.raises(TechnicalPolicyUnavailableError):
        client.evaluate(_intent())
