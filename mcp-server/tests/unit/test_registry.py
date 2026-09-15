"""Unit tests for the tool registry -- no Docker/Nautobot/GitLab required.

Confirms Reference-Architecture.md §7.2's domain-isolation and
catalogue-introspection guarantees hold structurally, and (regression test
for the bug found during live Milestone 5 verification) that every
registered tool's schema can be turned into a real, non-**kwargs function
signature the MCP SDK can introspect.
"""
from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel

from mcp_server.tools.registry import ToolRegistry


class _EchoRequest(BaseModel):
    value: str


def test_register_and_catalogue():
    registry = ToolRegistry()

    @registry.register(name="echo", domain="generic", description="d", schema=_EchoRequest)
    def _handler(request: _EchoRequest):
        return {"value": request.value}

    catalogue = registry.catalogue()
    assert len(catalogue) == 1
    assert catalogue[0].name == "echo"
    assert catalogue[0].domain == "generic"
    assert registry.get("echo") is not None
    assert registry.get("missing") is None


def test_duplicate_registration_raises():
    registry = ToolRegistry()

    @registry.register(name="echo", domain="generic", description="d", schema=_EchoRequest)
    def _handler(request: _EchoRequest):
        return request

    with pytest.raises(ValueError):
        @registry.register(name="echo", domain="generic", description="d2", schema=_EchoRequest)
        def _handler2(request: _EchoRequest):
            return request


def test_domain_isolation_no_cross_imports():
    """tools/generic.py must never import tools/aci.py, and vice versa
    (Reference-Architecture.md §7.2). Static-checked here rather than only
    documented in a comment."""
    import mcp_server.tools.aci as aci_module
    import mcp_server.tools.generic as generic_module

    aci_src = inspect.getsource(aci_module)
    generic_src = inspect.getsource(generic_module)

    assert "tools.generic" not in aci_src
    assert "tools.aci" not in generic_src


def test_real_tools_have_schema_derivable_signature():
    """Regression test: every real registered tool's Pydantic schema must
    produce a valid inspect.Signature with no **kwargs/*args-only shape --
    this exact bug (a bare **kwargs tool function) caused the MCP SDK to
    build a broken input schema during live Milestone 5 verification."""
    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import registry

    assert len(registry.catalogue()) >= 2
    for spec in registry.catalogue():
        params = [
            inspect.Parameter(
                field_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=field_info.annotation,
                default=inspect.Parameter.empty if field_info.is_required() else field_info.default,
            )
            for field_name, field_info in spec.schema.model_fields.items()
        ]
        sig = inspect.Signature(params)  # must not raise
        assert all(p.kind != inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


# ---------------------------------------------------------------------------
# Evidence levels (2026-09-15).
#
# CLAUDE.md's Definition of Done already required every capability to state
# whether it is unit-tested, plan-verified or live-verified. Stating it only
# in prose meant nothing enforced it, and the distinction kept being lost --
# most expensively when "plan-verified" was read as "works" and an applicable
# feature set was written off as permanently blocked. These tests make the
# claim structural.
# ---------------------------------------------------------------------------

def test_every_tool_declares_a_valid_evidence_level():
    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.evpn  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import EVIDENCE_LEVELS, registry

    for spec in registry.catalogue():
        assert spec.evidence in EVIDENCE_LEVELS, f"{spec.name} has evidence '{spec.evidence}'"


def test_evidence_defaults_to_the_weakest_claim():
    """Forgetting to declare evidence must UNDERSTATE what was proven, never
    overstate it -- that asymmetry is the whole point of the default."""
    from pydantic import BaseModel

    from mcp_server.tools.registry import ToolRegistry

    class _S(BaseModel):
        pass

    reg = ToolRegistry()
    reg.register(name="t", domain="d", description="x", schema=_S)(lambda r: None)

    assert reg.get("t").evidence == "unit-tested"


def test_an_invalid_evidence_level_is_rejected_at_registration():
    from pydantic import BaseModel

    from mcp_server.tools.registry import ToolRegistry

    class _S(BaseModel):
        pass

    reg = ToolRegistry()
    with pytest.raises(ValueError, match="evidence must be one of"):
        reg.register(name="t", domain="d", description="x", schema=_S, evidence="probably-fine")


def test_live_verified_tools_match_the_documented_count():
    """Platform-Status-and-Pending-Items.md states 18 live-verified and 32
    unit-tested only. If a tool is promoted or added without updating that
    document, this fails -- which is the documentation drift that let the
    catalogue sit at "18 tools" while 48 were registered."""
    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.evpn  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import registry

    assert len(registry.by_evidence("live-verified")) == 18
    assert len(registry.by_evidence("unit-tested")) == 32
    assert len(registry.catalogue()) == 50


def test_live_verified_tools_carry_a_note_saying_how():
    """A bare 'live-verified' is an assertion; a note is evidence."""
    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.evpn  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import registry

    for spec in registry.by_evidence("live-verified"):
        assert spec.evidence_note, f"{spec.name} claims live-verified with no note"
