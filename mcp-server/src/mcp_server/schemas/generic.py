"""Request schemas for domain-agnostic tools."""
from __future__ import annotations

from pydantic import BaseModel, Field


class GetPipelineReportRequest(BaseModel):
    pipeline_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "GitLab pipeline id, e.g. the last_pipeline_id show_status returns for a tenant. "
            "Omit to report the most recent pipeline that actually ran jobs."
        ),
    )
