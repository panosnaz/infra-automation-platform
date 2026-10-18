"""Keyword retrieval over a throwaway knowledge tree."""
from __future__ import annotations

from platform_reasoning.knowledge import load_sections, search


def _write(root, rel, text):
    path = root / "knowledge" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_archived_documents_are_excluded(tmp_path):
    _write(tmp_path, "adr/ADR-1.md", "# Live\nNode Not Leaf explained here.\n")
    _write(tmp_path, "adr/archive/ADR-0.md", "# Old\nNode Not Leaf in a superseded design.\n")
    paths = {s.path for s in load_sections(tmp_path)}
    assert paths == {"knowledge/adr/ADR-1.md"}


def test_a_section_matching_more_terms_ranks_first_and_reports_its_line(tmp_path):
    _write(tmp_path, "a.md", "# One\nmissing-cdev only.\n")
    _write(tmp_path, "b.md", "# Intro\ntext\n## Both\nfirst line\nmissing-cdev and concrete device together.\n")
    hits = search(load_sections(tmp_path), ["missing-cdev", "concrete device"])
    assert hits[0]["path"] == "knowledge/b.md"
    assert hits[0]["heading"] == "Both"
    assert hits[0]["line"] == 5


def test_table_rows_do_not_outrank_prose(tmp_path):
    rows = "\n".join("| x | F1298 Node Cannot Deploy |" for _ in range(40))
    _write(tmp_path, "matrix.md", f"# Matrix\n{rows}\n")
    _write(tmp_path, "adr.md", "# Why\nF1298 Node Cannot Deploy happens because there are no switches.\n")
    hits = search(load_sections(tmp_path), ["Node Cannot Deploy"])
    assert hits[0]["path"] == "knowledge/adr.md"


def test_hash_lines_inside_code_fences_are_not_headings(tmp_path):
    _write(tmp_path, "c.md", "# Real\n```bash\n# just a comment\n```\nbody\n")
    assert [s.heading for s in load_sections(tmp_path)] == ["Real"]


def test_no_terms_returns_nothing(tmp_path):
    _write(tmp_path, "a.md", "# A\ntext\n")
    assert search(load_sections(tmp_path), []) == []


def test_the_reasoning_layers_own_records_are_never_cited(tmp_path):
    """A past diagnosis recorded in the status tracker is not evidence for the next one."""
    _write(tmp_path, "adr/ADR-022-LangGraph.md", "# Self\nmissing-cdev seen by the diagnosis.\n")
    _write(tmp_path, "status.md", "# Done\n- diagnosis ([ADR-022](x)) found missing-cdev\n"
                                  "- the device has no concrete device: missing-cdev\n")
    hits = search(load_sections(tmp_path), ["missing-cdev"])
    assert [(h["path"], h["line"]) for h in hits] == [("knowledge/status.md", 3)]
