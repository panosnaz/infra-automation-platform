"""Exception hierarchy -> MCP tool error mapping.

No raw stack traces ever reach the AI agent (Platform-v2-Reference-Architecture.md
§7.5) -- every client-facing failure is one of these, with a short, safe
message.
"""
from __future__ import annotations


class MCPServerError(Exception):
    """Base class for all errors this server raises to a tool caller."""


class ValidationError(MCPServerError):
    """Tool input failed Pydantic schema validation."""


class NautobotError(MCPServerError):
    """Nautobot API call failed (auth, 4xx/5xx, or unreachable)."""


class GitLabError(MCPServerError):
    """GitLab API call failed (auth, 4xx/5xx, or unreachable)."""


class VaultError(MCPServerError):
    """Vault API call failed (auth, 4xx/5xx, or unreachable)."""


class PolicyDeniedError(MCPServerError):
    """Reserved for a future direct-OPA-call tool. Not used by create_tenant
    today -- policy is enforced pipeline-side by the existing policy_check
    GitLab CI job (Execution Framework Stage 3), not duplicated here."""
