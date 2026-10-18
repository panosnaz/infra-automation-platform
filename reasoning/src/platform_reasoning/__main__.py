"""python -m platform_reasoning diagnose --tenant sales [--object BGP_L3Out] [--pipeline 60]"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from platform_reasoning import knowledge
from platform_reasoning.diagnose import diagnose
from platform_reasoning.mcp_reader import ToolCallFailed, connect

_DEFAULT_URL = "http://localhost:8071/mcp"


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="platform_reasoning")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("diagnose", help="Read-only: why is an object not (validly) on the APIC?")
    d.add_argument("--tenant", required=True, help="Tenant name, e.g. sales or ACI:sales")
    d.add_argument("--object", dest="object_name", help="Object name, e.g. BGP_L3Out, FW, Web_EPG")
    d.add_argument("--pipeline", dest="pipeline_id", type=int, help="Pipeline id; default: the tenant's last recorded one")
    d.add_argument("--mcp-url", default=os.environ.get("MCP_URL", _DEFAULT_URL))
    d.add_argument(
        "--environment", choices=("production", "simulator"),
        default=os.environ.get("PLATFORM_ENVIRONMENT", "production"),
        help="'simulator' treats the lab's known fault floors (no registered switch, no L4-L7 "
             "device) as expected. Default 'production': they stop the diagnosis.",
    )
    d.add_argument("--json", action="store_true", help="Print the full graph state as JSON")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    async with connect(args.mcp_url) as reader:
        state = await diagnose(
            reader, args.tenant, args.object_name, args.pipeline_id, knowledge.load_sections(),
            environment=args.environment,
        )
    if args.json:
        print(json.dumps({k: v for k, v in state.items() if k != "report"}, indent=2, default=str))
    else:
        print(state["report"])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    try:
        return asyncio.run(_run(args))
    except ToolCallFailed as exc:
        print(f"diagnosis aborted: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"MCP Server unreachable at {args.mcp_url}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
