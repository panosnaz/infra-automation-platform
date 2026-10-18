"""Keyword retrieval over the knowledge base (knowledge/**/*.md).

Deliberately not a vector store: ADR-022 starts with plain, deterministic
retrieval and adds embeddings only if keyword search proves insufficient.
Archived documents are excluded -- they describe superseded designs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3]
_SNIPPET = 260
# One table that repeats a fault code forty times must not outrank a section
# that explains it once.
_COUNT_CAP = 3
# Records about the reasoning layer itself: citing them would present a past
# diagnosis as independent evidence for the next one.
_SELF_REFERENCE = "ADR-022"


@dataclass(frozen=True)
class Section:
    path: str
    heading: str
    line: int
    lines: tuple[str, ...]


def load_sections(repo_root: Path = DEFAULT_ROOT) -> list[Section]:
    root = repo_root / "knowledge"
    sections: list[Section] = []
    for md in sorted(root.rglob("*.md")):
        if "archive" in md.relative_to(root).parts or md.name.startswith(_SELF_REFERENCE):
            continue
        rel = md.relative_to(repo_root).as_posix()
        heading, start, buf, fenced = "(top of file)", 1, [], False
        for number, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
            if line.startswith("#") and not fenced:
                if buf:
                    sections.append(Section(rel, heading, start, tuple(buf)))
                heading, start, buf = line.lstrip("#").strip(), number, []
            # Blanked rather than dropped, so reported line numbers stay exact.
            buf.append("" if _SELF_REFERENCE in line else line)
        if buf:
            sections.append(Section(rel, heading, start, tuple(buf)))
    return sections


def search(sections: list[Section], terms: list[str], limit: int = 3) -> list[dict]:
    wanted = [t.lower() for t in dict.fromkeys(terms) if t]
    if not wanted:
        return []
    scored = []
    for section in sections:
        # Table rows are evidence logs; prose is where a cause is explained.
        text = "\n".join(line for line in section.lines if not line.lstrip().startswith("|")).lower()
        counts = {t: min(text.count(t), _COUNT_CAP) for t in wanted}
        distinct = sum(1 for c in counts.values() if c)
        if distinct:
            scored.append((distinct * 10 + sum(counts.values()), len(text), section))
    scored.sort(key=lambda item: (-item[0], item[1], item[2].path, item[2].line))
    return [_hit(section, wanted) for _, _, section in scored[:limit]]


def _hit(section: Section, wanted: list[str]) -> dict:
    # Prefer a body line over the heading, which rarely explains anything.
    candidates = [(o, line) for o, line in enumerate(section.lines) if not line.startswith("#")]
    candidates += [(o, line) for o, line in enumerate(section.lines) if line.startswith("#")]
    for offset, line in candidates:
        low = line.lower()
        term = next((t for t in wanted if t in low), None)
        if term is not None:
            at = low.index(term)
            begin = max(0, at - _SNIPPET // 3)
            snippet = line[begin:begin + _SNIPPET].strip()
            prefix = "..." if begin else ""
            suffix = "..." if begin + _SNIPPET < len(line) else ""
            return {
                "path": section.path,
                "line": section.line + offset,
                "heading": section.heading,
                "snippet": f"{prefix}{snippet}{suffix}",
            }
    return {"path": section.path, "line": section.line, "heading": section.heading, "snippet": ""}
