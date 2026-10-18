"""Unit tests for domain-agnostic tool input validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.schemas.generic import GetPipelineReportRequest


def test_get_pipeline_report_request_defaults_to_the_latest_run():
    assert GetPipelineReportRequest().pipeline_id is None
    assert GetPipelineReportRequest(pipeline_id=60).pipeline_id == 60


@pytest.mark.parametrize("bad", [0, -1])
def test_get_pipeline_report_request_rejects_a_non_positive_id(bad):
    with pytest.raises(ValidationError):
        GetPipelineReportRequest(pipeline_id=bad)
