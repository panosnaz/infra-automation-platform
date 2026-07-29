"""ACI-specific per-tool request schemas -- thin argument validation only,
never a cross-domain intent envelope (ADR-018)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Same naming convention the live OPA policy_check job already enforces
# (Execution-Framework.md Milestone 3, docker/platform-api/policy/cisco_aci/tenant_naming.rego)
# -- validating it here too gives a fast, clear MCP-side error instead of a
# slower round trip that only fails once the pipeline's policy_check job runs.
_TENANT_NAME_RE = re.compile(r"^[a-z0-9-]+$")


class CreateTenantRequest(BaseModel):
    name: str = Field(description="Tenant name, e.g. 'finance'. Must match ^[a-z0-9-]+$ (lowercase, digits, hyphens only) -- the same rule the pipeline's OPA policy_check job enforces.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _TENANT_NAME_RE.match(v):
            raise ValueError(
                f"tenant name '{v}' does not match required pattern ^[a-z0-9-]+$ "
                "(this mirrors the pipeline's own policy_check job -- fixing it "
                "here avoids a guaranteed pipeline denial later)"
            )
        return v
