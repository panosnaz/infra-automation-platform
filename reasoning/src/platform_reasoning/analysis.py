"""Deterministic cross-layer analysis -- no I/O, no LLM.

Every finding here is computed from the four MCP payloads, so the same inputs
always give the same diagnosis. ADR-010: AI is probabilistic and execution
must stay deterministic; the same discipline applies to what the platform
tells an engineer about why something failed.

Layers, in the order an object travels:
    1 intent     Nautobot                 get_tenant_intent
    2 generated  NetAsCode YAML           get_generated_intent
    3 execution  GitLab pipeline          get_pipeline_report (terraform)
    4 observed   APIC fault delta         get_pipeline_report (apic_fault_checks)
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# Keys whose list items are named ACI objects, mapped to one kind name so the
# two layers compare equal even where they spell the key differently.
KIND_KEYS: dict[str, str] = {
    "vrfs": "vrf",
    "bridge_domains": "bridge_domain",
    "application_profiles": "application_profile",
    "epgs": "epg",
    "endpoint_groups": "epg",
    "esgs": "esg",
    "endpoint_security_groups": "esg",
    "contracts": "contract",
    "filters": "filter",
    "l3outs": "l3out",
    "external_epgs": "external_epg",
    "node_profiles": "node_profile",
    "interface_profiles": "interface_profile",
    "devices": "l4l7_device",
    "service_graphs": "service_graph",
    "redirect_policies": "redirect_policy",
    "match_rules": "match_rule",
    "route_control_profiles": "route_control_profile",
}


@dataclass(frozen=True)
class FaultFamily:
    name: str
    summary: str
    dn: re.Pattern | None = None
    descr: re.Pattern | None = None
    kb_terms: tuple[str, ...] = ()

    def matches(self, fault: dict) -> bool:
        if self.dn is not None and self.dn.search(fault.get("dn", "")):
            return True
        return self.descr is not None and bool(self.descr.search(fault.get("descr", "")))


# Classification only. What each family MEANS is retrieved from the knowledge
# base at run time, so the explanation stays wherever the evidence was recorded.
FAULT_FAMILIES: tuple[FaultFamily, ...] = (
    FaultFamily(
        name="switch_absence",
        summary="policy cannot be pushed because the target node is not a registered switch",
        descr=re.compile(r"Node (Not Leaf|Cannot Deploy)", re.IGNORECASE),
        kb_terms=("Node Not Leaf", "Node Cannot Deploy", "switch-absence"),
    ),
    FaultFamily(
        name="l4l7_without_concrete_device",
        summary="L4-L7 device or service graph is invalid because no concrete device backs it",
        dn=re.compile(r"/(lDevVip|AbsGraph|CDev)-"),
        kb_terms=("missing-cdev", "concrete device"),
    ),
)

UNEXPLAINED = "unexplained"


@dataclass
class Layer:
    number: int
    name: str
    state: str  # "ok", "stop", "warn", "unknown"
    detail: str


@dataclass
class Diagnosis:
    tenant: str
    object_name: str | None
    pipeline_id: int | None
    layers: list[Layer] = field(default_factory=list)
    verdict: str = ""
    object_kinds: dict[str, list[str]] = field(default_factory=dict)
    fault_families: dict[str, list[dict]] = field(default_factory=dict)
    object_faults: list[dict] = field(default_factory=list)
    intent_only: list[str] = field(default_factory=list)
    generated_only: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    kb_terms: list[str] = field(default_factory=list)


def named_objects(payload: object) -> set[tuple[str, str]]:
    """Every (kind, name) pair reachable in an intent or generated payload."""
    found: set[tuple[str, str]] = set()

    def walk(node: object, kind: str | None) -> None:
        if isinstance(node, dict):
            if kind is not None and isinstance(node.get("name"), str):
                found.add((kind, node["name"]))
            for key, value in node.items():
                walk(value, KIND_KEYS.get(key))
        elif isinstance(node, list):
            for item in node:
                walk(item, kind)

    walk(payload, None)
    return found


def kinds_of(name: str, objects: set[tuple[str, str]]) -> list[str]:
    return sorted({kind for kind, n in objects if n == name})


def dn_mentions(dn: str, name: str) -> bool:
    """True when a DN segment is exactly this object, e.g. 'lDevVip-FW/' for FW."""
    return re.search(r"[-\[]" + re.escape(name) + r"(?=[/\]]|$)", dn) is not None


def classify_name(fault: dict) -> str:
    return next((f.name for f in FAULT_FAMILIES if f.matches(fault)), UNEXPLAINED)


def classify_faults(faults: list[dict]) -> dict[str, list[dict]]:
    families: dict[str, list[dict]] = {}
    for fault in faults:
        families.setdefault(classify_name(fault), []).append(fault)
    return families


def family(name: str) -> FaultFamily | None:
    return next((f for f in FAULT_FAMILIES if f.name == name), None)


def _fault_check(report: dict | None) -> dict | None:
    checks = (report or {}).get("apic_fault_checks") or {}
    return next(iter(checks.values()), None) if checks else None


def _terraform(report: dict | None, suffix: str) -> dict | None:
    for name, value in ((report or {}).get("terraform") or {}).items():
        if name.endswith(suffix):
            return value
    return None


def _awaiting(report: dict | None, suffix: str) -> bool:
    return any(name.endswith(suffix) for name in (report or {}).get("awaiting_approval") or [])


def analyse(
    tenant: str,
    object_name: str | None,
    intent: dict | None,
    generated: dict | None,
    report: dict | None,
    errors: dict[str, str] | None = None,
) -> Diagnosis:
    errors = errors or {}
    pipeline_id = ((report or {}).get("pipeline") or {}).get("id") or (generated or {}).get("pipeline_id")
    d = Diagnosis(tenant=tenant, object_name=object_name, pipeline_id=pipeline_id)

    intent_objects = named_objects(intent or {})
    generated_block = (generated or {}).get("intent") or {}
    generated_objects = named_objects(generated_block)

    # -- layer 1: intent ------------------------------------------------------
    if intent is None:
        d.layers.append(Layer(1, "intent (Nautobot)", "stop", errors.get("intent", "tenant not found")))
        d.verdict = f"Stops at layer 1: Nautobot holds no tenant '{tenant}'."
        return d
    if object_name:
        kinds = kinds_of(object_name, intent_objects)
        d.object_kinds["intent"] = kinds
        if kinds:
            d.layers.append(Layer(1, "intent (Nautobot)", "ok", f"{object_name} found as {', '.join(kinds)}"))
        else:
            close = difflib.get_close_matches(object_name, sorted({n for _, n in intent_objects}), n=3, cutoff=0.6)
            hint = f"; similar names: {', '.join(close)}" if close else ""
            d.layers.append(Layer(1, "intent (Nautobot)", "stop", f"no object named {object_name}{hint}"))
            d.verdict = f"Stops at layer 1: Nautobot holds no object named '{object_name}' in tenant '{tenant}'."
            d.suggestions.extend(f"did you mean '{c}'?" for c in close)
            return d
    else:
        d.layers.append(Layer(1, "intent (Nautobot)", "ok", f"{len(intent_objects)} named objects"))

    # -- layer 2: generated YAML ---------------------------------------------
    if generated is None or not generated.get("found"):
        reason = errors.get("generated") or (generated or {}).get("reason", "no generated file")
        d.layers.append(Layer(2, "generated YAML", "unknown", reason))
        d.verdict = "Cannot follow past layer 1: the generated NetAsCode file could not be read."
        return d
    source = generated.get("source", "")
    if generated.get("warning"):
        source = f"{source} -- WARNING: {generated['warning']}"
    if not generated.get("tenant_present"):
        d.layers.append(Layer(2, "generated YAML", "stop", f"tenant absent from the file ({source})"))
        d.verdict = (
            f"Stops at layer 2: pipeline {pipeline_id}'s generator did not emit tenant '{tenant}'. "
            "Either intent changed after that run, or the generator skipped the tenant."
        )
        return d

    names_intent = {f"{k}:{n}" for k, n in intent_objects}
    names_generated = {f"{k}:{n}" for k, n in generated_objects}
    d.intent_only = sorted(names_intent - names_generated)
    d.generated_only = sorted(names_generated - names_intent)

    if object_name:
        kinds = kinds_of(object_name, generated_objects)
        d.object_kinds["generated"] = kinds
        if not kinds:
            d.layers.append(Layer(2, "generated YAML", "stop", f"{object_name} absent ({source})"))
            d.verdict = (
                f"Stops at layer 2: '{object_name}' is in Nautobot but pipeline {pipeline_id} did not "
                "generate it. Either it was added after that run, or the generator drops it."
            )
            return d
        d.layers.append(Layer(2, "generated YAML", "ok", f"{object_name} present ({source})"))
    else:
        drift = f"; {len(d.intent_only)} only in Nautobot" if d.intent_only else ""
        d.layers.append(Layer(2, "generated YAML", "warn" if d.intent_only else "ok", f"tenant present{drift} ({source})"))

    # -- layer 3: execution ---------------------------------------------------
    if report is None or not report.get("found"):
        d.layers.append(Layer(3, "execution (GitLab)", "unknown", errors.get("report", "pipeline report unavailable")))
        d.verdict = "Cannot follow past layer 2: the pipeline report could not be read."
        return d
    plan = _terraform(report, "terraform_plan")
    apply = _terraform(report, "terraform_apply")
    plan_text = ""
    if plan and plan.get("plan"):
        p = plan["plan"]
        plan_text = f"plan +{p['add']} ~{p['change']} -{p['destroy']}"
    if _awaiting(report, "terraform_apply"):
        d.layers.append(Layer(3, "execution (GitLab)", "stop", f"{plan_text}; terraform_apply awaits manual approval".lstrip("; ")))
        d.verdict = f"Stops at layer 3: pipeline {pipeline_id} planned the change but nobody has approved terraform_apply."
        d.suggestions.append("approve terraform_apply in GitLab, then re-run this diagnosis")
        return d
    if apply is None:
        d.layers.append(Layer(3, "execution (GitLab)", "stop", f"{plan_text}; terraform_apply did not run".lstrip("; ")))
        d.verdict = f"Stops at layer 3: pipeline {pipeline_id} never ran terraform_apply."
        return d
    if apply.get("status") != "success" or apply.get("errors"):
        first = (apply.get("errors") or ["see the job log"])[0]
        d.layers.append(Layer(3, "execution (GitLab)", "stop", f"terraform_apply {apply.get('status')}: {first}"))
        d.verdict = f"Stops at layer 3: terraform_apply failed in pipeline {pipeline_id} -- {first}"
        return d
    a = apply.get("apply") or {}
    d.layers.append(Layer(
        3, "execution (GitLab)", "ok",
        f"{plan_text}; applied {a.get('added', 0)} added, {a.get('changed', 0)} changed, {a.get('destroyed', 0)} destroyed".lstrip("; "),
    ))

    # -- layer 4: observed ----------------------------------------------------
    check = _fault_check(report)
    if check is None:
        d.layers.append(Layer(4, "observed (APIC faults)", "unknown", "no fault check ran"))
        d.verdict = "Reached APIC (Terraform applied), but no fault check ran, so validity is unverified."
        return d
    status = check.get("status")
    if status == "clean":
        d.layers.append(Layer(4, "observed (APIC faults)", "ok", "no new faults"))
        d.verdict = (
            f"Reached APIC with no new faults (pipeline {pipeline_id}). If it is still not visible, "
            "compare the APIC GUI tab you are looking at with the object kind above."
        )
        return d
    if status != "new_faults":
        d.layers.append(Layer(4, "observed (APIC faults)", "unknown", f"fault check {status}: {check.get('detail', '')}"))
        d.verdict = "Reached APIC (Terraform applied), but the fault check could not verify the result."
        return d

    faults = check.get("faults") or []
    d.fault_families = classify_faults(faults)
    for name in d.fault_families:
        fam = family(name)
        d.kb_terms.extend(fam.kb_terms if fam else ())
    d.kb_terms.extend(sorted({f["code"] for f in d.fault_families.get(UNEXPLAINED, [])}))

    if object_name:
        d.object_faults = [f for f in faults if dn_mentions(f.get("dn", ""), object_name)]
        mine = len(d.object_faults)
        d.layers.append(Layer(4, "observed (APIC faults)", "stop" if mine else "warn",
                              f"{len(faults)} new faults, {mine} on {object_name}"))
        if mine:
            names = sorted({classify_name(f) for f in d.object_faults})
            d.verdict = (
                f"Stops at layer 4: APIC accepted '{object_name}' but raised {mine} fault(s) on it "
                f"({', '.join(names)}), so it is stored and not deployed."
            )
        else:
            d.verdict = (
                f"'{object_name}' reached APIC with no fault on it; the pipeline's other "
                f"{len(faults)} new fault(s) belong to other objects."
            )
    else:
        unexplained = len(d.fault_families.get(UNEXPLAINED, []))
        d.layers.append(Layer(4, "observed (APIC faults)", "stop" if unexplained else "warn",
                              f"{len(faults)} new faults, {unexplained} unexplained"))
        d.verdict = (
            f"{len(faults)} new fault(s) in pipeline {pipeline_id}: "
            + ", ".join(f"{len(v)} {k}" for k, v in d.fault_families.items())
            + (". Investigate the unexplained ones first." if unexplained else ".")
        )
    return d
