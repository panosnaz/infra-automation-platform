"""Plain-text rendering of a diagnosis. No decisions are made here."""
from __future__ import annotations

from platform_reasoning import analysis

_MARK = {"ok": "ok  ", "warn": "warn", "stop": "STOP", "unknown": "??  "}
_MAX_FAULTS = 8
_MAX_DRIFT = 8


def render(state: dict, reads: list[str]) -> str:
    d = state.get("diagnosis") or {}
    target = f", object {d['object_name']}" if d.get("object_name") else ""
    pipeline = f" (pipeline {d['pipeline_id']})" if d.get("pipeline_id") else ""
    env = d.get("environment") or "production"
    out = [f"Diagnosis: tenant {d.get('tenant')}{target}{pipeline}, environment {env}", "",
           f"Verdict: {d.get('verdict')}", ""]

    for layer in d.get("layers") or []:
        out.append(f"  [{_MARK.get(layer['state'], layer['state'])}] {layer['number']} {layer['name']:<24} {layer['detail']}")

    if d.get("object_name"):
        faults = d.get("object_faults") or []
        families = analysis.classify_faults(faults)
        title = f"Faults on {d['object_name']}"
    else:
        faults = None
        families = d.get("fault_families") or {}
        title = "New faults by family"
    if families:
        out += ["", f"{title}:"]
        out += _families(families, env, show_all=faults is not None)
    shared = {} if d.get("object_name") else (d.get("shared_fault_families") or {})
    if shared:
        out += ["", "Fabric-wide new faults (no tenant in the DN; not attributable to this tenant):"]
        out += _families(shared, env, show_all=False)
    if d.get("other_tenant_faults"):
        out += ["", f"{d['other_tenant_faults']} new fault(s) belong to other tenants and are not counted here."]

    if not d.get("object_name") and (d.get("intent_only") or d.get("generated_only")):
        out += ["", "Nautobot vs generated YAML:"]
        for label, items in (("only in Nautobot", d.get("intent_only")), ("only in YAML", d.get("generated_only"))):
            if items:
                shown = ", ".join(items[:_MAX_DRIFT]) + (f" (+{len(items) - _MAX_DRIFT} more)" if len(items) > _MAX_DRIFT else "")
                out.append(f"  {label}: {shown}")

    cited = state.get("knowledge") or {}
    if any(cited.values()):
        out += ["", "What the knowledge base already records:"]
        for name, hits in cited.items():
            if not hits:
                continue
            out.append(f"  {name}")
            for hit in hits:
                out.append(f"    {hit['path']}:{hit['line']} ({hit['heading']})")
                if hit["snippet"]:
                    out.append(f"      \"{hit['snippet']}\"")

    if d.get("suggestions"):
        out += ["", "Next:"] + [f"  - {s}" for s in d["suggestions"]]

    errors = state.get("errors") or {}
    if errors:
        out += ["", "Read errors:"] + [f"  {k}: {v}" for k, v in errors.items()]

    out += ["", f"Read-only: {len(reads)} MCP call(s) ({', '.join(reads)}), 0 writes."]
    return "\n".join(out)


def _families(families: dict[str, list[dict]], environment: str, show_all: bool) -> list[str]:
    lines = []
    for name, items in families.items():
        fam = analysis.family(name)
        if fam is None:
            meaning = "no known family -- investigate"
        elif analysis.expected(name, environment):
            meaning = f"{fam.summary} (expected on the {environment})"
        else:
            meaning = f"{fam.summary} (a lab floor; NOT expected in {environment} -- investigate)"
        lines.append(f"  {name} ({len(items)}): {meaning}")
        lines += _faults(items if show_all else items[:3], indent="    ")
    return lines


def _faults(faults: list[dict], indent: str = "  ") -> list[str]:
    lines = []
    for fault in faults[:_MAX_FAULTS]:
        lines.append(f"{indent}{fault['code']} {fault['severity']:<8} {fault['dn']}")
        if fault.get("descr"):
            lines.append(f"{indent}    {fault['descr']}")
    if len(faults) > _MAX_FAULTS:
        lines.append(f"{indent}... {len(faults) - _MAX_FAULTS} more")
    return lines
