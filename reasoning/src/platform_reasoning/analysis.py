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


ENVIRONMENTS = ("production", "simulator")

# This diagnosis reads only the ACI domain's jobs. Exact names, never a suffix
# match: endswith("terraform_apply") also matched evpn_terraform_apply, and an
# applied ACI change was reported as unapproved (review fix, 2026-10-18).
ACI_JOBS = {"plan": "terraform_plan", "apply": "terraform_apply", "faults": "verify_apic_faults"}


@dataclass(frozen=True)
class FaultFamily:
    name: str
    summary: str
    dn: re.Pattern | None = None
    descr: re.Pattern | None = None
    kb_terms: tuple[str, ...] = ()
    # Where this family is EXPECTED -- a known floor rather than a problem.
    # Every family below exists because the lab simulator registers no
    # switch and backs no L4-L7 device; on a real fabric the same fault is a
    # genuine problem, so it is still classified but no longer explained away.
    expected_in: frozenset[str] = frozenset({"simulator"})

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
    # Measured 2026-10-14 (ADR-020, BGP route reflector policy).
    FaultFamily(
        name="rr_node_not_registered_spine",
        summary="a BGP route-reflector node is not a registered spine",
        descr=re.compile(r"Only spine nodes can be BGP Route-Reflectors", re.IGNORECASE),
        kb_terms=("F1893", "Only spine nodes can be BGP Route-Reflectors"),
    ),
    # Measured 2026-10-16 (ADR-020, L3Out depth).
    FaultFamily(
        name="vpc_pair_not_in_fabric",
        summary="a vPC pair's leaves are not registered in the fabric",
        descr=re.compile(r"Both Nodes in VPC Not in Fabric", re.IGNORECASE),
        kb_terms=("F0749", "vPC pair"),
    ),
)

UNEXPLAINED = "unexplained"

# A tenant segment anywhere in a DN, including inside a bracketed target,
# e.g. uni/epp/rtd-[uni/tn-sales/out-X/...]/node-101/... -> sales.
_TENANT_IN_DN = re.compile(r"(?:^|[/\[])tn-([^/\]]+)")


def bare_tenant(name: str) -> str:
    """Nautobot names tenants 'ACI:<name>'; APIC DNs carry only <name>."""
    return name[4:] if name.startswith("ACI:") else name


def fault_tenants(dn: str) -> set[str]:
    return set(_TENANT_IN_DN.findall(dn))


def expected(family_name: str, environment: str) -> bool:
    fam = family(family_name)
    return fam is not None and environment in fam.expected_in


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
    environment: str = "production"
    # Faults with no tenant in their DN (fabric / access policies): reported,
    # but not attributable to this tenant.
    shared_fault_families: dict[str, list[dict]] = field(default_factory=dict)
    # Faults in OTHER tenants: excluded from this tenant's verdict, only counted.
    other_tenant_faults: int = 0


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
    return ((report or {}).get("apic_fault_checks") or {}).get(ACI_JOBS["faults"])


def _terraform(report: dict | None, job: str) -> dict | None:
    return ((report or {}).get("terraform") or {}).get(job)


def _awaiting(report: dict | None, job: str) -> bool:
    return job in ((report or {}).get("awaiting_approval") or [])


def _unexpected(families: dict[str, list[dict]], environment: str) -> list[dict]:
    """Faults that are not a known floor in this environment."""
    return [f for name, items in families.items() if not expected(name, environment) for f in items]


def _floor_note(names: list[str], environment: str) -> str:
    known = [n for n in names if family(n) is not None]
    if known and all(expected(n, environment) for n in names):
        return f" All are known {environment} floors."
    lab_only = [n for n in known if not expected(n, environment)]
    if lab_only:
        return (f" {', '.join(lab_only)} is a lab floor, not expected outside the simulator "
                f"(environment: {environment}) -- investigate.")
    return ""


def analyse(
    tenant: str,
    object_name: str | None,
    intent: dict | None,
    generated: dict | None,
    report: dict | None,
    errors: dict[str, str] | None = None,
    environment: str = "production",
) -> Diagnosis:
    """`environment` decides whether a known fault family is a floor or a
    problem. The default is the strict one: forgetting it can only make a
    diagnosis stop where it might not need to, never explain a real fault away."""
    if environment not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of {ENVIRONMENTS}, got {environment!r}")
    errors = errors or {}
    pipeline_id = ((report or {}).get("pipeline") or {}).get("id") or (generated or {}).get("pipeline_id")
    d = Diagnosis(tenant=tenant, object_name=object_name, pipeline_id=pipeline_id, environment=environment)

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
    plan = _terraform(report, ACI_JOBS["plan"])
    apply = _terraform(report, ACI_JOBS["apply"])
    plan_text = ""
    if plan and plan.get("plan"):
        p = plan["plan"]
        plan_text = f"plan +{p['add']} ~{p['change']} -{p['destroy']}"
    if _awaiting(report, ACI_JOBS["apply"]):
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

    # The fault check covers every tenant the pipeline manages plus fabric-wide
    # objects. Split it three ways so one tenant never inherits another's
    # faults (review fix, 2026-10-18): this tenant's, fabric-wide (no tenant in
    # the DN -- access / fabric policies), and other tenants' (excluded).
    faults = check.get("faults") or []
    me = bare_tenant(tenant)
    own = [f for f in faults if me in fault_tenants(f.get("dn", ""))]
    shared = [f for f in faults if not fault_tenants(f.get("dn", ""))]
    d.other_tenant_faults = len(faults) - len(own) - len(shared)
    d.fault_families = classify_faults(own)
    d.shared_fault_families = classify_faults(shared)
    for families in (d.fault_families, d.shared_fault_families):
        for name in families:
            fam = family(name)
            d.kb_terms.extend(t for t in (fam.kb_terms if fam else ()) if t not in d.kb_terms)
    unexplained_codes = {f["code"] for fams in (d.fault_families, d.shared_fault_families) for f in fams.get(UNEXPLAINED, [])}
    d.kb_terms.extend(sorted(unexplained_codes))
    others = f", {d.other_tenant_faults} belong to other tenants" if d.other_tenant_faults else ""

    if object_name:
        d.object_faults = [f for f in own if dn_mentions(f.get("dn", ""), object_name)]
        mine = len(d.object_faults)
        d.layers.append(Layer(4, "observed (APIC faults)", "stop" if mine else "warn",
                              f"{len(own)} new faults on this tenant, {mine} on {object_name}{others}"))
        if mine:
            names = sorted({classify_name(f) for f in d.object_faults})
            d.verdict = (
                f"Stops at layer 4: APIC accepted '{object_name}' but raised {mine} fault(s) on it "
                f"({', '.join(names)}), so it is stored and not deployed." + _floor_note(names, environment)
            )
        else:
            d.verdict = (
                f"'{object_name}' reached APIC with no fault on it; the tenant's other "
                f"{len(own)} new fault(s) belong to other objects."
            )
    else:
        unexpected_own = _unexpected(d.fault_families, environment)
        unexpected_shared = _unexpected(d.shared_fault_families, environment)
        state = "stop" if unexpected_own else ("warn" if own or shared else "ok")
        d.layers.append(Layer(
            4, "observed (APIC faults)", state,
            f"{len(own)} new faults on this tenant, {len(shared)} fabric-wide{others}; "
            f"{len(unexpected_own) + len(unexpected_shared)} not expected in {environment}",
        ))
        parts = ", ".join(f"{len(v)} {k}" for k, v in d.fault_families.items()) or "none"
        shared_text = (f"; fabric-wide, not attributable to one tenant: "
                       + ", ".join(f"{len(v)} {k}" for k, v in d.shared_fault_families.items())) if shared else ""
        d.verdict = (
            f"{len(own)} new fault(s) on tenant '{me}' in pipeline {pipeline_id}: {parts}{shared_text}{others}."
            + (" Investigate the ones not expected here first." if unexpected_own else "")
            + _floor_note(sorted(d.fault_families), environment)
        )
    return d
