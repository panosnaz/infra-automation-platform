"""Thin python-gitlab wrapper -- read-only. The MCP Server queries pipeline
status here (Platform-v2-Reference-Architecture.md §7.7); it never triggers
pipelines itself -- that is a native Nautobot webhook (see the webhook
created against tenancy.tenant in Nautobot, not this client).
"""
from __future__ import annotations

import re

import gitlab

from mcp_server.errors import GitLabError

# ANSI colour codes and GitLab's per-line "<timestamp> 01O " / "01E " prefix.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TRACE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z \d{2}[OE][+ ]?")

# Lines printed by platform/workflows/scripts/check_apic_faults.py --compare.
_FAULT_OK_RE = re.compile(r"^OK: no new configuration faults under (?P<scope>.+)$")
_FAULT_FAIL_RE = re.compile(r"^FAIL: this deployment introduced (?P<count>\d+) new fault")
_FAULT_LINE_RE = re.compile(
    r"^\s*\[(?P<severity>\w+)(?: \((?P<lc>[\w-]+)\))?\] (?P<code>F\d+)\s+(?P<dn>\S+)$"
)
_FAULT_UNREACHABLE_RE = re.compile(r"^FAIL \(fail-closed\): (?P<reason>.+)$")

_TERRAFORM_PLAN_RE = re.compile(r"Plan: (\d+) to add, (\d+) to change, (\d+) to destroy")
_TERRAFORM_APPLY_RE = re.compile(r"Apply complete! Resources: (\d+) added, (\d+) changed, (\d+) destroyed")
_TERRAFORM_NO_CHANGES = "No changes. Your infrastructure matches the configuration."
_TERRAFORM_ERROR_RE = re.compile(r"^(?:│\s*)?Error: (.+)$")

_MAX_ERRORS = 10


def clean_trace(trace: str) -> list[str]:
    """Job trace as plain lines: ANSI colour and the timestamp prefix removed."""
    lines = []
    for raw in trace.splitlines():
        line = _TRACE_PREFIX_RE.sub("", _ANSI_RE.sub("", raw))
        lines.append(line.rstrip())
    return lines


def parse_fault_check(lines: list[str]) -> dict:
    """Interpret check_apic_faults.py --compare output.

    Returns a status of "clean", "new_faults" or "unverifiable", never a guess:
    output it does not recognise is reported as "unrecognised" so a format
    change in the script shows up instead of reading as clean.
    """
    faults: list[dict] = []
    pending: dict | None = None
    status = "unrecognised"
    detail = ""
    for line in lines:
        if m := _FAULT_OK_RE.match(line):
            status, detail = "clean", m.group("scope")
        elif m := _FAULT_UNREACHABLE_RE.match(line):
            status, detail = "unverifiable", m.group("reason")
        elif _FAULT_FAIL_RE.match(line):
            status = "new_faults"
        elif m := _FAULT_LINE_RE.match(line):
            pending = {k: v for k, v in m.groupdict().items() if v is not None}
            faults.append(pending)
        elif pending is not None and line.startswith("      ") and line.strip():
            pending["descr"] = line.strip()
            pending = None
    return {"status": status, "detail": detail, "faults": faults}


def parse_terraform(lines: list[str]) -> dict:
    """Pull the plan or apply summary, and any errors, out of a Terraform job trace."""
    text = "\n".join(lines)
    result: dict = {}
    if m := _TERRAFORM_PLAN_RE.search(text):
        result["plan"] = dict(zip(("add", "change", "destroy"), map(int, m.groups())))
    elif _TERRAFORM_NO_CHANGES in text:
        result["plan"] = {"add": 0, "change": 0, "destroy": 0}
    if m := _TERRAFORM_APPLY_RE.search(text):
        result["apply"] = dict(zip(("added", "changed", "destroyed"), map(int, m.groups())))
    errors = []
    for line in lines:
        if (m := _TERRAFORM_ERROR_RE.match(line)) and len(errors) < _MAX_ERRORS:
            errors.append(m.group(1).strip())
    if errors:
        result["errors"] = errors
    return result


# --- plan content (get_plan_changes, 2026-10-18) -----------------------------------

_PLAN_ACTIONS_START = "Terraform will perform the following actions:"
_RESOURCE_LINE_RE = re.compile(
    r"^\s*# (?P<address>\S+) (?P<verb>will be created|will be updated in-place|will be destroyed|"
    r"must be replaced|will be read during apply|has changed|has been deleted)$"
)
_ACTIONS = {
    "will be created": "create", "will be updated in-place": "update", "will be destroyed": "delete",
    "must be replaced": "replace", "will be read during apply": "read",
}
_DRIFT = {"has changed": "changed", "has been deleted": "deleted"}
_ADDRESS_RE = re.compile(r'^(?P<resource>[a-z0-9_]+\.[A-Za-z0-9_-]+)(?:\[(?P<key>.+)\])?$')


def _split_address(address: str) -> dict:
    m = _ADDRESS_RE.match(address)
    resource = m.group("resource") if m else address.split("[", 1)[0]
    key = (m.group("key") if m else None) or ""
    return {"resource": resource, "type": resource.split(".", 1)[0], "key": key.strip('"')}


def parse_plan_changes(lines: list[str]) -> dict:
    """Every resource a terraform_plan trace will create / update / delete /
    replace, and any drift Terraform noticed while refreshing.

    Terraform prints "changed outside of Terraform" notes BEFORE the action
    list; those are drift, not part of the plan. The parsed actions are
    counted the way Terraform counts them (a replace is one add plus one
    destroy) and compared with its own "Plan:" line, so a list this parser
    only partly understood is flagged rather than presented as complete.
    """
    changes: list[dict] = []
    drift: list[dict] = []
    in_actions = False
    for line in lines:
        if line.strip() == _PLAN_ACTIONS_START:
            in_actions = True
            continue
        m = _RESOURCE_LINE_RE.match(line)
        if not m:
            continue
        address, verb = m.group("address"), m.group("verb")
        parts = _split_address(address)
        if verb in _DRIFT:
            drift.append({"address": address, "type": parts["type"], "key": parts["key"], "kind": _DRIFT[verb]})
        elif in_actions:
            changes.append({"address": address, **parts, "action": _ACTIONS[verb]})

    summary = parse_terraform(lines).get("plan")
    actions = [c["action"] for c in changes]
    counted = {
        "add": actions.count("create") + actions.count("replace"),
        "change": actions.count("update"),
        "destroy": actions.count("delete") + actions.count("replace"),
    }
    return {"summary": summary, "counted": counted, "consistent": summary is not None and summary == counted,
            "changes": changes, "drift": drift}


# [ \t]*, not \s*: in MULTILINE mode \s also eats newlines, and a match would
# then start on the blank line above the comment.
_MARKER_RE = re.compile(r"^[ \t]*# (?:EVIDENCE:|NOT-SETTABLE\[NS-\d+\]:)", re.MULTILINE)
_NEXT_RESOURCE_RE = re.compile(r'^resource "(?P<type>[a-z0-9_]+)" "(?P<name>[^"]+)"', re.MULTILINE)
_NS_ID_RE = re.compile(r"NOT-SETTABLE\[(NS-\d+)\]")


def parse_resource_markers(main_tf: str) -> dict[str, dict]:
    """`# EVIDENCE:` notes and `# NOT-SETTABLE[NS-xx]:` ids per resource
    ("type.name"), each attached to the next resource block below it -- the
    same rule tests/unit/test_not_settable.py applies. Only resources that
    carry a marker are returned."""
    markers: dict[str, dict] = {}
    for m in _MARKER_RE.finditer(main_tf):
        nxt = _NEXT_RESOURCE_RE.search(main_tf, m.end())
        if nxt is None:
            continue
        entry = markers.setdefault(f"{nxt.group('type')}.{nxt.group('name')}", {"not_settable": [], "evidence": []})
        line_end = main_tf.find("\n", m.start())
        line = main_tf[m.start():line_end if line_end != -1 else len(main_tf)]
        if ns := _NS_ID_RE.search(line):
            if ns.group(1) not in entry["not_settable"]:
                entry["not_settable"].append(ns.group(1))
            continue
        # EVIDENCE: the note runs over the following comment lines.
        text, pos = [line.split("EVIDENCE:", 1)[1].strip()], line_end + 1
        while 0 < pos < len(main_tf):
            end = main_tf.find("\n", pos)
            nxt_line = main_tf[pos:end if end != -1 else len(main_tf)].strip()
            if not nxt_line.startswith("#") or _MARKER_RE.match(nxt_line) or "NOT-SETTABLE[" in nxt_line:
                break
            text.append(nxt_line.lstrip("#").strip())
            pos = end + 1 if end != -1 else len(main_tf)
        entry["evidence"].append(" ".join(t for t in text if t))
    return markers


class GitLabClient:
    def __init__(self, url: str, token: str, project_id: str) -> None:
        self._url = url
        self._token = token
        self._project_id = project_id
        self._gl: gitlab.Gitlab | None = None

    @property
    def _client(self) -> gitlab.Gitlab:
        if self._gl is None:
            self._gl = gitlab.Gitlab(self._url, private_token=self._token or None, keep_base_url=True)
        return self._gl

    def _project(self):
        try:
            return self._client.projects.get(self._project_id)
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"GitLab unreachable or auth failed: {exc}") from exc

    def latest_pipeline(self) -> dict | None:
        """Most recent pipeline on the default branch -- used by show_status
        to report the pipeline a create_tenant call most likely triggered.
        """
        try:
            project = self._client.projects.get(self._project_id)
            pipelines = project.pipelines.list(per_page=1, order_by="id", sort="desc", get_all=False)
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"GitLab unreachable or auth failed: {exc}") from exc
        if not pipelines:
            return None
        p = pipelines[0]
        return {
            "id": p.id,
            "status": p.status,
            "web_url": p.web_url,
            "ref": p.ref,
            "sha": p.sha,
            "source": getattr(p, "source", None),
        }

    def pipeline(self, pipeline_id: int) -> dict | None:
        try:
            project = self._client.projects.get(self._project_id)
            p = project.pipelines.get(pipeline_id)
        except gitlab.exceptions.GitlabGetError:
            return None
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"GitLab unreachable or auth failed: {exc}") from exc
        return {
            "id": p.id,
            "status": p.status,
            "web_url": p.web_url,
            "ref": p.ref,
            "sha": p.sha,
        }

    def latest_run_pipeline(self) -> dict | None:
        """Most recent pipeline that actually ran jobs.

        `latest_pipeline()` is usually the generator's own `[skip ci]` commit,
        which GitLab records as a pipeline with status `skipped` and no jobs.
        """
        project = self._project()
        try:
            pipelines = project.pipelines.list(per_page=20, order_by="id", sort="desc", get_all=False)
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"GitLab pipeline listing failed: {exc}") from exc
        for p in pipelines:
            if p.status != "skipped":
                return {"id": p.id, "status": p.status, "web_url": p.web_url, "ref": p.ref, "sha": p.sha}
        return None

    def recent_run_pipelines(self, limit: int = 20) -> list[dict]:
        """Newest pipelines that ran jobs (not the generator's [skip ci] ones), newest first."""
        project = self._project()
        try:
            pipelines = project.pipelines.list(per_page=limit, order_by="id", sort="desc", get_all=False)
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"GitLab pipeline listing failed: {exc}") from exc
        return [{"id": p.id, "status": p.status, "web_url": p.web_url, "ref": p.ref, "sha": p.sha}
                for p in pipelines if p.status != "skipped"]

    def pipeline_jobs(self, pipeline_id: int) -> list[dict]:
        project = self._project()
        try:
            jobs = project.pipelines.get(pipeline_id, lazy=True).jobs.list(get_all=True)
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"could not list jobs of pipeline {pipeline_id}: {exc}") from exc
        return sorted(
            ({"id": j.id, "name": j.name, "stage": j.stage, "status": j.status, "web_url": j.web_url} for j in jobs),
            key=lambda j: j["id"],
        )

    def job_trace(self, job_id: int) -> str:
        project = self._project()
        try:
            raw = project.jobs.get(job_id, lazy=True).trace()
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"could not read the log of job {job_id}: {exc}") from exc
        return (raw or b"").decode("utf-8", errors="replace")

    def job_artifact_file(self, job_id: int, path: str) -> str | None:
        """One file from a job's artifacts; None when the job kept no such file."""
        project = self._project()
        try:
            raw = project.jobs.get(job_id, lazy=True).artifact(path)
        except gitlab.exceptions.GitlabGetError:
            return None
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"could not read artifact {path} of job {job_id}: {exc}") from exc
        return (raw or b"").decode("utf-8", errors="replace")

    def repository_file(self, path: str, ref: str) -> str | None:
        project = self._project()
        try:
            raw = project.files.raw(file_path=path, ref=ref)
        except gitlab.exceptions.GitlabGetError:
            return None
        except Exception as exc:  # noqa: BLE001
            raise GitLabError(f"could not read {path} at {ref}: {exc}") from exc
        return (raw or b"").decode("utf-8", errors="replace")
