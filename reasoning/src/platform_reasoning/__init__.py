"""LangGraph reasoning layer (ADR-022).

Reads platform state only through the MCP Server, never holds infrastructure
credentials, and never writes. The first workflow is read-only diagnosis.
"""

__version__ = "0.1.0"
