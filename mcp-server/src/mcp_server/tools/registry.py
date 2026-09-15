"""Tool registration/dispatch -- domain-agnostic. Per
Platform-v2-Reference-Architecture.md §7.2, this module must never import
from a domain-specific tools module (tools/aci.py, future tools/evpn.py,
etc.) -- it dispatches by name only and knows nothing about any domain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, get_args

from pydantic import BaseModel

# How far a tool has actually been proven, weakest first. These are the three
# levels CLAUDE.md's Definition of Done already required be stated -- but
# stating them only in prose meant nothing enforced or surfaced them, and the
# distinction kept getting lost. Holding the value on the ToolSpec makes it
# checkable, and lets the catalogue report it to the AI client that is about
# to call the tool.
#
#   unit-tested    Schema validation and dispatch are covered by offline
#                  tests. Nothing has touched live Nautobot or the APIC.
#                  Says nothing about whether the tool works end to end.
#   plan-verified  The Terraform it eventually drives produces a clean plan
#                  against a real APIC. Validates against the provider schema
#                  only, never against live APIC state -- a clean plan is NOT
#                  evidence the resource is even produced (see ADR-020's OSPF
#                  fixture, which planned cleanly while emitting zero OSPF
#                  interface profiles).
#   live-verified  Exercised for real: the tool called over the MCP protocol
#                  against live Nautobot, and/or a genuine apply + destroy
#                  cycle against the APIC with the fault delta checked.
EvidenceLevel = Literal["unit-tested", "plan-verified", "live-verified"]

EVIDENCE_LEVELS: tuple[str, ...] = get_args(EvidenceLevel)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    domain: str
    description: str
    schema: type[BaseModel]
    handler: Callable[..., Any]
    # Defaults to the WEAKEST claim on purpose. Forgetting to declare evidence
    # then understates what has been proven, never overstates it -- the whole
    # failure mode this exists to prevent.
    evidence: EvidenceLevel = "unit-tested"
    evidence_note: str = ""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        *,
        name: str,
        domain: str,
        description: str,
        schema: type[BaseModel],
        evidence: EvidenceLevel = "unit-tested",
        evidence_note: str = "",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if evidence not in EVIDENCE_LEVELS:
            raise ValueError(
                f"Tool '{name}': evidence must be one of {EVIDENCE_LEVELS}, got '{evidence}'"
            )

        def _decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._tools:
                raise ValueError(f"Tool '{name}' already registered")
            self._tools[name] = ToolSpec(
                name=name, domain=domain, description=description,
                schema=schema, handler=handler,
                evidence=evidence, evidence_note=evidence_note,
            )
            return handler

        return _decorator

    def by_evidence(self, level: EvidenceLevel) -> list[ToolSpec]:
        """Every tool proven only to `level`. Used by the catalogue report and
        by tests that assert the documented counts still match reality."""
        return [spec for spec in self._tools.values() if spec.evidence == level]

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def catalogue(self) -> list[ToolSpec]:
        """What the MCP protocol advertises to AI clients."""
        return list(self._tools.values())


# One process-wide registry, imported by every tools/<domain>.py module.
registry = ToolRegistry()
