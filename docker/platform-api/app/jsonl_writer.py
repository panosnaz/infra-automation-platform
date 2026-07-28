"""Generic append-only JSON Lines writer — a shared platform primitive.

Used by audit_log.py (Milestone 2) and, later, Knowledge Capture
(Milestone 5, docs/05-Operations/14-Vertical-Slice-v0.1-Roadmap.md). Knows
nothing about policies, intents, or any other domain concept — it appends
whatever record dict it's given to whatever path it's given.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append `record` as one JSON line to `path`, creating parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str))
        f.write("\n")
