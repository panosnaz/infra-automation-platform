"""Tool registration/dispatch -- domain-agnostic. Per
Platform-v2-Reference-Architecture.md §7.2, this module must never import
from a domain-specific tools module (tools/aci.py, future tools/evpn.py,
etc.) -- it dispatches by name only and knows nothing about any domain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    domain: str
    description: str
    schema: type[BaseModel]
    handler: Callable[..., Any]


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
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def _decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._tools:
                raise ValueError(f"Tool '{name}' already registered")
            self._tools[name] = ToolSpec(
                name=name, domain=domain, description=description,
                schema=schema, handler=handler,
            )
            return handler

        return _decorator

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def catalogue(self) -> list[ToolSpec]:
        """What the MCP protocol advertises to AI clients."""
        return list(self._tools.values())


# One process-wide registry, imported by every tools/<domain>.py module.
registry = ToolRegistry()
