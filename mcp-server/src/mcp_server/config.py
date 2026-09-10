"""Environment-based configuration for the MCP Server.

Same fail-fast convention Platform v1 already established (NAUTOBOT_TOKEN /
VAULT_TOKEN required at startup, not lazily) -- reused as a pattern here,
not as shared code, per Platform-v2-Reference-Architecture.md ADR-016
("replacement, not migration").
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # Nautobot -- the Source of Truth every tool ultimately writes to.
    nautobot_url: str = Field(default="http://localhost:8080", alias="NAUTOBOT_URL")
    nautobot_token: str = Field(alias="NAUTOBOT_TOKEN")

    # GitLab -- queried (never orchestrated) by show_status per
    # Platform-v2-Reference-Architecture.md §7.7. A dedicated, least-privilege
    # read_api-scoped token, matching the PIPELINE_STATUS_TOKEN precedent
    # from Execution-Framework.md Milestone 4 -- never the token that
    # triggers pipelines (that lives in Nautobot's own webhook config, not
    # here, since triggering is a native Nautobot webhook, not an MCP tool).
    gitlab_url: str = Field(default="http://localhost:8929", alias="GITLAB_URL")
    gitlab_token: str = Field(default="", alias="GITLAB_TOKEN")
    gitlab_project_id: str = Field(default="1", alias="GITLAB_PROJECT_ID")

    # AI-client-facing auth (Section 7.3's first boundary). The MCP Server's
    # own credentials above (Nautobot/GitLab) are the second boundary and
    # are never returned to a client, per ADR-010's "AI never receives
    # privileged or direct access to execution engines."
    mcp_api_key: str = Field(default="", alias="MCP_API_KEY")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # "stdio" (default -- how Claude Desktop / VS Code Copilot Agent spawn a
    # local MCP server process directly) or "streamable-http" (used by the
    # containerized docker/mcp-server/ stack, which needs a real listening
    # port for Section 7.6's health endpoint to mean anything).
    mcp_transport: str = Field(default="stdio", alias="MCP_TRANSPORT")
    mcp_host: str = Field(default="127.0.0.1", alias="MCP_HOST")
    mcp_port: int = Field(default=8001, alias="MCP_PORT")


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
