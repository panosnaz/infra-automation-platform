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
