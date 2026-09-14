"""Unit tests for tools/generic.py -- no live Nautobot or GitLab needed.

`show_status` is described in Platform-v2-Reference-Architecture.md §7.7 as
"the one piece of genuinely new logic the MCP Server owns" -- everything
else in the catalogue is a thin write-through to Nautobot. It is also the
only tool that depends on two clients at once, and the only one with real
branching: tenant-missing, a recorded pipeline id, and a fallback to the
project's latest pipeline when that id resolves to nothing.

It shipped with no tests at all. These cover each branch, using the same
duck-typed fake-client convention as test_tools_aci.py rather than mocking
either client's HTTP layer -- the point is to pin what show_status *does*
with the two clients' return values, not to re-test the clients.
"""
from __future__ import annotations

from mcp_server.tools.generic import ShowStatusRequest, show_status


class _FakeNautobotClient:
    def __init__(self, tenant=None):
        self._tenant = tenant
        self.calls: list[tuple[str, str]] = []

    def get_tenant_status(self, name):
        self.calls.append(("get_tenant_status", name))
        return self._tenant


class _FakeGitLabClient:
    """Records which lookup path was taken. `pipeline_result` is what
    pipeline(id) returns; None simulates an id GitLab no longer knows about
    (expired, or from a pipeline deleted since write_results ran)."""

    def __init__(self, pipeline_result=None, latest_result=None):
        self._pipeline_result = pipeline_result
        self._latest_result = latest_result
        self.calls: list[tuple[str, object]] = []

    def pipeline(self, pipeline_id):
        self.calls.append(("pipeline", pipeline_id))
        return self._pipeline_result

    def latest_pipeline(self):
        self.calls.append(("latest_pipeline", None))
        return self._latest_result


def _tenant(**custom_fields):
    return {"id": "tenant-id", "name": "ACI:sales", "custom_fields": custom_fields}


def test_show_status_reports_not_found_without_touching_gitlab():
    """A tenant that does not exist must short-circuit -- querying GitLab
    for a tenant Nautobot has never heard of would report an unrelated
    pipeline as if it belonged to it."""
    nautobot = _FakeNautobotClient(tenant=None)
    gitlab = _FakeGitLabClient()

    result = show_status(ShowStatusRequest(name="nonexistent"), nautobot=nautobot, gitlab=gitlab)

    assert result == {"found": False, "name": "nonexistent"}
    assert gitlab.calls == []


def test_show_status_surfaces_all_four_write_results_custom_fields():
    """These four fields are exactly what the pipeline's write_results job
    writes back (Execution Framework stage 7). If write_results starts
    writing a fifth, or renames one, this is where the mismatch shows up."""
    nautobot = _FakeNautobotClient(
        tenant=_tenant(
            validation_status="stable",
            last_pipeline_id=42,
            last_pipeline_url="http://gitlab.local:8929/root/p/-/pipelines/42",
            last_validated_at="2026-09-14T10:00:00+00:00",
        )
    )
    gitlab = _FakeGitLabClient(pipeline_result={"id": 42, "status": "success"})

    result = show_status(ShowStatusRequest(name="sales"), nautobot=nautobot, gitlab=gitlab)

    assert result["found"] is True
    assert result["name"] == "sales"
    assert result["nautobot"] == {
        "validation_status": "stable",
        "last_pipeline_id": 42,
        "last_pipeline_url": "http://gitlab.local:8929/root/p/-/pipelines/42",
        "last_validated_at": "2026-09-14T10:00:00+00:00",
    }
    assert result["gitlab_live_pipeline"] == {"id": 42, "status": "success"}


def test_show_status_looks_up_the_recorded_pipeline_not_the_latest():
    """The whole value of this tool is answering "what happened to MY
    change" -- falling through to the project's latest pipeline when a
    recorded id exists would answer a different question entirely."""
    nautobot = _FakeNautobotClient(tenant=_tenant(last_pipeline_id=42))
    gitlab = _FakeGitLabClient(pipeline_result={"id": 42, "status": "running"}, latest_result={"id": 99})

    show_status(ShowStatusRequest(name="sales"), nautobot=nautobot, gitlab=gitlab)

    assert gitlab.calls == [("pipeline", 42)]


def test_show_status_coerces_a_string_pipeline_id_to_int():
    """Nautobot custom fields round-trip through JSON and an integer field
    can come back as a string; gitlab.pipeline() expects an int."""
    nautobot = _FakeNautobotClient(tenant=_tenant(last_pipeline_id="42"))
    gitlab = _FakeGitLabClient(pipeline_result={"id": 42, "status": "success"})

    show_status(ShowStatusRequest(name="sales"), nautobot=nautobot, gitlab=gitlab)

    assert gitlab.calls == [("pipeline", 42)]
    assert isinstance(gitlab.calls[0][1], int)


def test_show_status_falls_back_to_latest_pipeline_when_none_recorded():
    """The real case this exists for: an MCP tool has just written to
    Nautobot and the webhook-triggered pipeline is still in flight, so
    write_results has not stamped a pipeline id yet. Returning the project's
    latest pipeline shows the caller that something is running."""
    nautobot = _FakeNautobotClient(tenant=_tenant(validation_status=None))
    gitlab = _FakeGitLabClient(latest_result={"id": 99, "status": "pending"})

    result = show_status(ShowStatusRequest(name="sales"), nautobot=nautobot, gitlab=gitlab)

    assert gitlab.calls == [("latest_pipeline", None)]
    assert result["gitlab_live_pipeline"] == {"id": 99, "status": "pending"}


def test_show_status_falls_back_when_the_recorded_pipeline_is_gone():
    """A recorded id that GitLab no longer resolves (expired or deleted)
    must not leave gitlab_live_pipeline as None -- it falls through to the
    latest pipeline, so both lookups are expected here."""
    nautobot = _FakeNautobotClient(tenant=_tenant(last_pipeline_id=42))
    gitlab = _FakeGitLabClient(pipeline_result=None, latest_result={"id": 99, "status": "success"})

    result = show_status(ShowStatusRequest(name="sales"), nautobot=nautobot, gitlab=gitlab)

    assert gitlab.calls == [("pipeline", 42), ("latest_pipeline", None)]
    assert result["gitlab_live_pipeline"] == {"id": 99, "status": "success"}


def test_show_status_tolerates_a_tenant_with_no_custom_fields_key():
    """`tenant.get("custom_fields") or {}` -- a tenant created outside the
    pipeline (directly in the Nautobot UI) has never been stamped, and must
    report nulls rather than raising."""
    nautobot = _FakeNautobotClient(tenant={"id": "tenant-id", "name": "ACI:sales"})
    gitlab = _FakeGitLabClient(latest_result=None)

    result = show_status(ShowStatusRequest(name="sales"), nautobot=nautobot, gitlab=gitlab)

    assert result["found"] is True
    assert result["nautobot"] == {
        "validation_status": None,
        "last_pipeline_id": None,
        "last_pipeline_url": None,
        "last_validated_at": None,
    }
