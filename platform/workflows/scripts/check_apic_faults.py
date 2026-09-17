#!/usr/bin/env python3
"""Execution Framework -- Stage 6 (Verification), APIC fault-delta half.

Answers a question nothing else in this pipeline asks: *did the change we
just applied leave the fabric in a valid state?*

`terraform apply` reporting success only means the APIC accepted the POSTs.
The APIC routinely accepts configuration it then marks invalid, raising a
fault and deploying nothing. That gap is not hypothetical -- on 2026-09-15 an
apply of this repo's own L4-L7 fixture completed cleanly, every relation
reported `state: formed`, and the service device was flagged invalid the
whole time because `trunking` is a VMM-only option that had been set on a
PHYSICAL device. Nothing noticed, because nothing looks at faults.

Two modes, because a bare fault count means nothing on a fabric that already
has unrelated faults (undiscovered nodes, licensing, and so on):

    check_apic_faults.py --snapshot faults-before.json
    check_apic_faults.py --compare  faults-before.json <path-to-tenants.yaml>

Only *new* faults whose DN sits under a tenant named in the generated
NetAsCode YAML are treated as failures -- everything else is pre-existing
fabric noise this pipeline did not cause and must not block on.

Reads TF_VAR_aci_url / TF_VAR_aci_username / TF_VAR_aci_password, which
platform/terraform/aci/scripts/load-vault-creds.sh already exports from
Vault -- no new secret path, no credentials on the command line.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

import yaml

# Severities that represent a real configuration problem. "cleared" faults are
# resolved history, and "info" is not actionable.
_FAILING_SEVERITIES = frozenset({"critical", "major", "minor", "warning"})


class ApicError(RuntimeError):
    """APIC unreachable or rejected the request."""


def _ssl_context(insecure: bool):
    if not insecure:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _login(url: str, username: str, password: str, ctx) -> str:
    body = json.dumps({"aaaUser": {"attributes": {"name": username, "pwd": password}}}).encode()
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/aaaLogin.json", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30, context=ctx) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApicError(f"could not reach APIC at {url}: {exc}") from exc
    return payload["imdata"][0]["aaaLogin"]["attributes"]["token"]


def fetch_faults(url: str, username: str, password: str, insecure: bool = True) -> dict[str, dict]:
    """Return {fault_dn: {code, severity, descr}} for every current fault."""
    ctx = _ssl_context(insecure)
    token = _login(url, username, password, ctx)
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/class/faultInst.json", headers={"Cookie": f"APIC-cookie={token}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60, context=ctx) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApicError(f"could not query faults from {url}: {exc}") from exc

    faults: dict[str, dict] = {}
    for item in payload.get("imdata", []):
        attrs = item["faultInst"]["attributes"]
        faults[attrs["dn"]] = {
            "code": attrs.get("code", ""),
            "severity": attrs.get("severity", ""),
            "descr": attrs.get("descr", ""),
        }
    return faults


# Objects this platform creates OUTSIDE any tenant, and the DN fragment that
# identifies one by name. Scoping faults to `tn-<name>/` alone was the
# original design, and it has a blind spot: the generator also emits VMM
# domains, VLAN pools, physical/L3 domains, AEPs and the whole access-policy
# hierarchy, none of which live under a tenant at all. The 2026-09-15 PBR lab
# apply raised 7 faults on exactly those objects and the check reported none
# of them -- they happened to all be `cleared`, so nothing was missed that
# time, but a real one would have passed silently.
#
# Each entry maps a NetAsCode key path to the `uni/...` DN fragment APIC uses,
# with `{name}` substituted from the YAML. Matching by exact name keeps the
# same discipline as the tenant anchor: we claim a fault only for an object we
# actually declared, never for a same-class object someone else created.
_GLOBAL_SCOPES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("fabric_policies", "vlan_pools"), "vlanns-[{name}]"),
    (("fabric_policies", "vmm_domains"), "dom-{name}/"),
    (("fabric_policies", "pod_policy_groups"), "podpgrp-{name}"),
    (("access_policies", "physical_domains"), "phys-{name}"),
    (("access_policies", "l3_domains"), "l3dom-{name}"),
    (("access_policies", "aeps"), "attentp-{name}"),
    (("access_policies", "leaf_interface_policy_groups"), "accportgrp-{name}"),
    (("access_policies", "access_port_profiles"), "accportprof-{name}"),
    (("access_policies", "leaf_profiles"), "nprof-{name}"),
)


def managed_tenants(netascode_yaml: str) -> list[str]:
    """Tenant names this pipeline is responsible for."""
    with open(netascode_yaml, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return [t["name"] for t in (data.get("apic", {}).get("tenants") or []) if t.get("name")]


def managed_global_objects(netascode_yaml: str) -> list[str]:
    """DN fragments for every non-tenant object this deployment declares.

    Returns the concrete `uni/...` fragments (e.g. `dom-vCenter_VMM/`) to look
    for, so a fault on a VMM domain or a VLAN pool we created is attributed to
    this deployment rather than dismissed as unrelated fabric noise.
    """
    with open(netascode_yaml, encoding="utf-8") as handle:
        apic = (yaml.safe_load(handle) or {}).get("apic") or {}

    fragments: list[str] = []
    for key_path, template in _GLOBAL_SCOPES:
        node: object = apic
        for key in key_path:
            node = (node or {}).get(key) if isinstance(node, dict) else None
        for item in node or []:
            name = item.get("name") if isinstance(item, dict) else None
            if name:
                fragments.append(template.format(name=name))
    return fragments


def is_managed(fault_dn: str, tenants: list[str], global_objects: list[str] | None = None) -> bool:
    """True when the fault's DN belongs to something this deployment declared.

    Tenant scope is matched on the exact `tn-<name>/` segment rather than a
    bare substring, so tenant `sales` never claims a fault belonging to
    `sales-archive`. Non-tenant objects are matched on their own DN fragment
    (see `_GLOBAL_SCOPES`).
    """
    if any(f"tn-{tenant}/" in fault_dn or fault_dn.endswith(f"tn-{tenant}") for tenant in tenants):
        return True
    return any(fragment in fault_dn for fragment in global_objects or [])


def new_managed_faults(
    before: dict[str, dict],
    after: dict[str, dict],
    tenants: list[str],
    global_objects: list[str] | None = None,
) -> dict[str, dict]:
    """Faults present after but not before, scoped to what we manage."""
    return {
        dn: info
        for dn, info in after.items()
        if dn not in before
        and info.get("severity") in _FAILING_SEVERITIES
        and is_managed(dn, tenants, global_objects)
    }


def _credentials() -> tuple[str, str, str]:
    url = os.environ.get("TF_VAR_aci_url", "")
    username = os.environ.get("TF_VAR_aci_username", "")
    password = os.environ.get("TF_VAR_aci_password", "")
    if not all([url, username, password]):
        raise ApicError(
            "TF_VAR_aci_url/username/password must be set -- source "
            "platform/terraform/aci/scripts/load-vault-creds.sh first"
        )
    return url, username, password


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", metavar="FILE", help="Write current faults to FILE.")
    group.add_argument("--compare", metavar="FILE", help="Compare current faults against FILE.")
    parser.add_argument(
        "netascode_yaml",
        nargs="?",
        help="Generated YAML naming the managed tenants (required with --compare).",
    )
    args = parser.parse_args()

    try:
        url, username, password = _credentials()
        faults = fetch_faults(url, username, password)
    except ApicError as exc:
        # Fail closed, same principle as policy_check.py per ADR-014: an
        # unverifiable fabric is not a verified one.
        print(f"FAIL (fail-closed): {exc}", file=sys.stderr)
        return 1

    if args.snapshot:
        with open(args.snapshot, "w", encoding="utf-8") as handle:
            json.dump(faults, handle, indent=2, sort_keys=True)
        print(f"Snapshot: {len(faults)} pre-existing fault(s) recorded to {args.snapshot}")
        return 0

    if not args.netascode_yaml:
        print("ERROR: --compare requires the NetAsCode YAML path", file=sys.stderr)
        return 2

    try:
        with open(args.compare, encoding="utf-8") as handle:
            before = json.load(handle)
    except OSError as exc:
        print(f"FAIL: could not read snapshot {args.compare}: {exc}", file=sys.stderr)
        return 1

    tenants = managed_tenants(args.netascode_yaml)
    global_objects = managed_global_objects(args.netascode_yaml)
    introduced = new_managed_faults(before, faults, tenants, global_objects)
    scope = f"managed tenant(s) {tenants} + {len(global_objects)} non-tenant object(s)"

    if not introduced:
        print(
            f"OK: no new configuration faults under {scope} "
            f"({len(before)} before, {len(faults)} now)"
        )
        return 0

    print(
        f"FAIL: this deployment introduced {len(introduced)} new fault(s) under "
        f"{scope}:",
        file=sys.stderr,
    )
    for dn, info in sorted(introduced.items()):
        print(f"  [{info['severity']}] {info['code']}  {dn}", file=sys.stderr)
        print(f"      {info['descr']}", file=sys.stderr)
    print(
        "\nTerraform reported success, so these objects exist -- but APIC "
        "considers them invalid and will not deploy them. Treat this as a "
        "failed deployment, not a warning.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
