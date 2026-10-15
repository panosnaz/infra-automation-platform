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
                inspect.Parameter.KEYWORD_ONLY,  # mirrors main.py
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
    """Platform-Status-and-Pending-Items.md states 51 tools: 21 live-verified
    and 30 unit-tested only. If a tool is promoted or added without updating
    that document, this fails -- which is the documentation drift that let the
    catalogue sit at "18 tools" while 48 were registered.

    Raised 18 -> 21 on 2026-09-15 by the PBR lab apply, which exercised
    create_filter, create_pbr_policy and create_pbr_contract end to end
    (MCP -> Nautobot -> generator -> terraform apply -> APIC object
    confirmed fault-free). create_l4l7_device and create_service_graph were
    deliberately NOT promoted in the same run: their objects exist in APIC
    but APIC flags them invalid, so the apply is not evidence they deploy.

    Catalogue 50 -> 51 the same day: create_concrete_device, which closes the
    gap that made those two undeployable. It stays unit-tested -- its VIRTUAL
    path needs a real vCenter and its PHYSICAL path needs leaf switches.

    51 -> 57 and 21 -> 27 on 2026-09-16: the six L3Out Logical Interface
    Profile policy tools (ND, DPP, PIM, IGMP, Custom QoS, and the binding
    tool). These are live-verified rather than unit-tested because the
    objects need no leaf port, switch or vCenter -- a real apply + destroy
    against the lab APIC was possible and was run, with every MO read back.

    57 -> 60 and 27 -> 30 the same day: the three route-control tools
    (create_match_rule, create_route_control_profile,
    set_external_epg_subnet_scope,
    bind_external_epg_route_control_profile), built for the transit-routing
    lab and verified the same way.

    65 -> 76 and unit-tested 30 -> 41 on 2026-10-12: the eleven read / update
    / delete tools (list_aci_tenants, get_tenant_intent, get_fabric_intent,
    update_vrf, update_bridge_domain, update_epg, delete_tenant_object,
    delete_fabric_object, unbind_epg_contract, unbind_epg_domain,
    delete_tenant). Live 35 -> 46 the same day: all eleven were driven over
    the real MCP protocol against live Nautobot (48/48 checks), so they were
    promoted together.

    76 -> 88 and live 46 -> 59 the same day: the twelve port-channel / vPC /
    node-management tools (68/68 live MCP checks plus a fixture apply +
    destroy against the lab APIC), and create_static_path_binding, promoted
    from unit-tested because its port / PC / vPC bindings were driven live and
    read back. Unit-tested 30 -> 29.

    88 -> 107 and live 59 -> 78 on 2026-10-13: the nineteen fabric-wide
    policy tools (NTP / DNS / SNMP / COOP / ISIS / fault / syslog), 46/46 live
    MCP checks plus a fixture apply + destroy against the lab APIC.

    107 -> 111 and live 78 -> 82 on 2026-10-14: the BGP route reflector policy
    and pod assignment tools, 30/30 live MCP checks plus a fixture apply +
    destroy against the lab APIC.

    111 -> 121 and live 82 -> 92 on 2026-10-15: the ten ESG / vzAny tools,
    51/51 live MCP checks plus a fixture apply, intent-clearing update and
    destroy against the lab APIC.

    121 -> 135 and live 92 -> 106 on 2026-10-16: the fourteen L3Out depth
    tools, 60/60 live MCP checks plus a 14/14 Terraform cycle (apply, re-plan,
    intent removal, destroy) against the lab APIC.
    """
    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.evpn  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import registry

    assert len(registry.by_evidence("live-verified")) == 106
    assert len(registry.by_evidence("unit-tested")) == 29
    assert len(registry.catalogue()) == 135


def test_live_verified_tools_carry_a_note_saying_how():
    """A bare 'live-verified' is an assertion; a note is evidence."""
    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.evpn  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import registry

    for spec in registry.by_evidence("live-verified"):
        assert spec.evidence_note, f"{spec.name} claims live-verified with no note"


def test_optional_fields_with_a_default_factory_are_not_advertised_as_required():
    """A field declared `Field(default_factory=list)` has `.default` set to
    PydanticUndefined, not to []. Passing that into inspect.Parameter made
    the MCP SDK advertise the field as REQUIRED, so a client omitting it got
    "Field required" and could not call the tool at all.

    Eleven fields across nine tools were affected -- including create_epg and
    create_aep, both already marked live-verified, because every unit test
    calls the handler function directly and never exercises the signature
    main.py generates. Found 2026-09-16 over the real MCP protocol.

    Deliberately does NOT import mcp_server.main: that module needs the `mcp`
    SDK, which is only installed in the container, and this suite must stay
    runnable offline. The rule it guards lives in main.py's
    _register_with_mcp, which resolves the default with
    get_default(call_default_factory=True).
    """
    from pydantic_core import PydanticUndefined

    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.evpn  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import registry

    offenders = []
    for spec in registry.catalogue():
        for field_name, field_info in spec.schema.model_fields.items():
            if field_info.is_required():
                continue
            resolved = field_info.get_default(call_default_factory=True)
            if resolved is PydanticUndefined:
                offenders.append(f"{spec.name}.{field_name}")

    assert not offenders, (
        "these optional fields resolve to PydanticUndefined and would be "
        f"advertised as required over MCP: {offenders}"
    )


def test_every_tool_has_a_schema_test_and_a_dispatch_test():
    """CLAUDE.md's Definition of Done requires both for every MCP tool. It was
    stated, never checked -- and create_contract and create_l3out had shipped
    with no dispatch test at all (found 2026-10-12). This makes the rule
    structural: a new tool without both fails here.

    "Has a schema test" = its request schema class is referenced in a
    test_schemas_*.py file. "Has a dispatch test" = its handler is called
    in a test_tools_*.py file, directly or as a parametrize row.
    """
    import re
    from pathlib import Path

    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.evpn  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import registry

    here = Path(__file__).parent
    schema_src = "".join(p.read_text(encoding="utf-8") for p in here.glob("test_schemas_*.py"))
    dispatch_src = "".join(p.read_text(encoding="utf-8") for p in here.glob("test_tools_*.py"))
    # show_status's request schema is defined inline in tools/generic.py and
    # is exercised by its dispatch tests; it has no separate schema file.
    schema_exempt = {"show_status"}

    missing = []
    for spec in registry.catalogue():
        if spec.name not in schema_exempt and spec.schema.__name__ not in schema_src:
            missing.append(f"{spec.name}: no schema test ({spec.schema.__name__})")
        # A direct call `name(`, or a parametrize row `(name, ...)`. The row
        # form allows no whitespace after "(", so the first name in a
        # multi-line `from ... import (` block does not count.
        call = r"\b" + re.escape(spec.name) + r"\("
        row = r"\(" + re.escape(spec.name) + r","
        if not re.search(call + "|" + row, dispatch_src):
            missing.append(f"{spec.name}: no dispatch test")

    assert not missing, "\n".join(missing)


def test_no_tool_requires_a_location():
    """A Location name is a fact about the environment, not the code, so every
    location-scoped tool auto-resolves it when omitted (2026-09-17). Nine
    access-hierarchy tools were missed then and still required it -- found
    when the pc/vPC live run could not create an access port profile without
    naming the lab's Location (2026-10-12)."""
    import mcp_server.tools.aci  # noqa: F401
    import mcp_server.tools.evpn  # noqa: F401
    import mcp_server.tools.generic  # noqa: F401
    from mcp_server.tools.registry import registry

    required = [s.name for s in registry.catalogue()
                if (f := s.schema.model_fields.get("location")) is not None and f.is_required()]
    assert not required, f"these tools still require location=: {required}"
