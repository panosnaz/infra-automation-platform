#!/usr/bin/env python3
"""Declare the Nautobot schema this platform requires, before anything writes to it.

WHY THIS EXISTS
---------------
Nautobot knows nothing about Cisco ACI. Every ACI concept without a native
Nautobot model -- VLAN pools, AEPs, L3Outs, service graphs, route maps -- is
stored in a JSON Custom Field, and a Custom Field must be DECLARED before it
can hold anything.

Writing to an undeclared field is the worst failure mode this platform has:
Nautobot answers **HTTP 200** and silently discards the data. No error, no
warning, no log line. Every MCP tool reports success, the generator emits an
empty document, and Terraform applies nothing. It looks like it worked.

That is not hypothetical. On 2026-09-15 a full L4-L7/PBR lab was built
through the MCP tools, every call reported OK, and nothing persisted --
`aci_l4l7_services` had never been declared.

Until this script existed, all 20 fields had been created by hand, one API
call at a time, over several weeks. They lived only inside one running
database. This file is now the authoritative, reviewable answer to "what
schema does this platform need?".

USAGE
-----
    # check an environment without changing it (safe anywhere, anytime)
    python bootstrap_nautobot.py --verify

    # create whatever is missing; safe to re-run
    python bootstrap_nautobot.py

    # also create the Location that fabric-wide intent hangs off
    python bootstrap_nautobot.py --location "Customer DC1"

Environment:
    NAUTOBOT_URL    default http://localhost:8080
    NAUTOBOT_TOKEN  required

Exit codes:
    0  everything present (or created successfully)
    1  --verify found something missing
    2  configuration/connection error

Idempotent by design. Re-running is a no-op, which is what makes --verify
usable as a pre-flight check at a customer site rather than a deploy step.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# The schema. Exported from a known-good instance rather than hand-written, so
# it matches what the generator and the MCP clients actually read.
#
# `content_types` matters as much as the name: the same field on the wrong
# object type is silently useless in exactly the same way as a missing one.
# ---------------------------------------------------------------------------
CUSTOM_FIELDS: list[dict] = [
    # --- tenancy.tenant : everything tenant-scoped -------------------------
    {"key": "aci_contracts", "type": "json", "content_types": ["tenancy.tenant"],
     "label": "ACI Contracts",
     "description": "Contracts, subjects and filters for this tenant."},
    {"key": "aci_l3outs", "type": "json", "content_types": ["tenancy.tenant"],
     "label": "ACI L3Outs",
     "description": "L3Outs: node/interface profiles, external EPGs, route maps."},
    {"key": "aci_l4l7_services", "type": "json", "content_types": ["tenancy.tenant"],
     "label": "ACI L4-L7 Services",
     "description": "L4-L7 devices, service graphs, PBR redirect policies, health groups."},
    {"key": "aci_vrf_route_leaks", "type": "json", "content_types": ["tenancy.tenant"],
     "label": "ACI VRF Route Leaks",
     "description": "Inter-VRF route leaking for shared services."},
    {"key": "aci_ospf_interface_policies", "type": "json", "content_types": ["tenancy.tenant"],
     "label": "ACI OSPF Interface Policies",
     "description": "Tenant-scoped OSPF interface policies referenced by L3Outs."},
    {"key": "aci_interface_policies", "type": "json", "content_types": ["tenancy.tenant"],
     "label": "ACI Interface Policies",
     "description": "L3Out interface-profile sub-policies: ND, DPP, PIM, IGMP, Custom QoS."},
    {"key": "aci_route_control", "type": "json", "content_types": ["tenancy.tenant"],
     "label": "ACI Route Control",
     "description": "Route-map match rules (rtctrlSubjP). Route maps live under aci_l3outs."},

    # --- dcim.location : fabric-wide objects with no tenant ----------------
    {"key": "aci_fabric_policies", "type": "json", "content_types": ["dcim.location"],
     "label": "ACI Fabric Policies",
     "description": "VLAN pools, domains, AEPs, policy groups, leaf/interface profiles, POD policies."},
    {"key": "aci_aaa_policies", "type": "json", "content_types": ["dcim.location"],
     "label": "ACI AAA Policies",
     "description": "Security domains and local users (RBAC). Never stores passwords."},

    # --- ipam.vlan : an EPG is modelled as a VLAN --------------------------
    {"key": "aci_application_profile", "type": "text", "content_types": ["ipam.vlan"],
     "label": "ACI Application Profile",
     "description": "Application Profile this EPG belongs to."},
    {"key": "aci_epg_bridge_domain", "type": "text", "content_types": ["ipam.vlan"],
     "label": "ACI EPG Bridge Domain",
     "description": "Bridge Domain this EPG is attached to."},
    {"key": "aci_epg_contracts", "type": "json", "content_types": ["ipam.vlan"],
     "label": "ACI EPG Contracts",
     "description": "Contracts this EPG provides and consumes."},
    {"key": "aci_epg_domains", "type": "json", "content_types": ["ipam.vlan"],
     "label": "ACI EPG Domains",
     "description": "Physical/VMM domain bindings, with resolution and deployment immediacy."},
    {"key": "aci_epg_subnets", "type": "json", "content_types": ["ipam.vlan"],
     "label": "ACI EPG Subnets",
     "description": "Subnets defined directly on the EPG rather than the Bridge Domain."},
    {"key": "aci_static_paths", "type": "json", "content_types": ["ipam.vlan"],
     "label": "ACI Static Paths",
     "description": "Port-level static path bindings for this EPG."},

    # --- ipam.prefix : a Bridge Domain is modelled as a Prefix -------------
    {"key": "aci_gateway_ip", "type": "text", "content_types": ["ipam.prefix"],
     "label": "ACI Gateway IP",
     "description": "Explicit pervasive gateway. Without it the generator assumes the first host."},
    {"key": "aci_bd_subnet_scope", "type": "text", "content_types": ["ipam.prefix"],
     "label": "ACI BD Subnet Scope",
     "description": "'public' and/or 'shared'. Empty means private. Needed for external advertisement."},
    {"key": "aci_bd_l3outs", "type": "json", "content_types": ["ipam.prefix"],
     "label": "ACI BD L3Outs",
     "description": "L3Outs this BD may advertise through. A public subnet with no L3Out is still never advertised."},

    # --- ipam.vrf : VRF attribute depth (ADR-020 Phase A item 1) -----------
    # These were read by the generator but had NEVER been declared in the lab
    # Nautobot -- found 2026-09-17 by the cross-check test below. Setting any
    # of them would have been silently discarded, so the documented "VRF
    # attribute depth" capability could not actually work through Nautobot.
    {"key": "aci_ip_data_plane_learning", "type": "boolean", "content_types": ["ipam.vrf"],
     "label": "ACI IP Data Plane Learning",
     "description": "VRF data-plane IP learning. Unset means the provider's own ACI default."},
    {"key": "aci_policy_control_enforcement_direction", "type": "text", "content_types": ["ipam.vrf"],
     "label": "ACI Policy Control Enforcement Direction",
     "description": "'ingress' or 'egress'. Unset means the ACI default."},
    {"key": "aci_policy_control_enforcement_mode", "type": "text", "content_types": ["ipam.vrf"],
     "label": "ACI Policy Control Enforcement Mode",
     "description": "'enforced' or 'unenforced'. Unset means the ACI default."},

    # --- ipam.prefix : Bridge Domain attribute depth -----------------------
    {"key": "aci_bd_mac", "type": "text", "content_types": ["ipam.prefix"],
     "label": "ACI BD MAC",
     "description": "Custom BD MAC address. Unset means ACI's default 00:22:BD:F8:19:FF."},
    {"key": "aci_bd_arp_flooding", "type": "boolean", "content_types": ["ipam.prefix"],
     "label": "ACI BD ARP Flooding",
     "description": "Flood ARP rather than unicast it to the known endpoint."},
    {"key": "aci_bd_advertise_host_routes", "type": "boolean", "content_types": ["ipam.prefix"],
     "label": "ACI BD Advertise Host Routes",
     "description": "Advertise /32 host routes out of an L3Out."},
    {"key": "aci_bd_l2_unknown_unicast", "type": "text", "content_types": ["ipam.prefix"],
     "label": "ACI BD L2 Unknown Unicast",
     "description": "'proxy' or 'flood' for unknown L2 unicast."},
    {"key": "aci_bd_l3_unknown_multicast", "type": "text", "content_types": ["ipam.prefix"],
     "label": "ACI BD L3 Unknown Multicast",
     "description": "'flood' or 'opt-flood' for unknown L3 multicast."},
    {"key": "aci_bd_multi_destination", "type": "text", "content_types": ["ipam.prefix"],
     "label": "ACI BD Multi Destination Flooding",
     "description": "Multi-destination flood scope, e.g. 'bd-flood' or 'drop'."},
    {"key": "aci_bd_ep_move_detect_mode", "type": "text", "content_types": ["ipam.prefix"],
     "label": "ACI BD Endpoint Move Detection",
     "description": "Endpoint move detection mode, e.g. 'garp'."},
    {"key": "aci_bd_pim", "type": "boolean", "content_types": ["ipam.prefix"],
     "label": "ACI BD PIM",
     "description": "Enable PIM (L3 multicast) on this Bridge Domain."},

    # --- ipam.vlan : EPG attribute depth -----------------------------------
    {"key": "aci_epg_preferred_group_member", "type": "boolean", "content_types": ["ipam.vlan"],
     "label": "ACI EPG Preferred Group Member",
     "description": "Include this EPG in the VRF's preferred group (contract-free communication)."},

    # --- dcim.device : the fabric node roster ------------------------------
    {"key": "aci_node_id", "type": "integer", "content_types": ["dcim.device"],
     "label": "ACI Node ID",
     "description": "Fabric node ID. Every topology/pod-N/paths-M path DN is validated against this roster."},
    {"key": "aci_pod_id", "type": "integer", "content_types": ["dcim.device"],
     "label": "ACI Pod ID",
     "description": "APIC POD this node belongs to. Required for multi-pod fabrics."},
]


class BootstrapError(RuntimeError):
    """Configuration or connectivity problem -- not a missing field."""


def _request(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Token {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise BootstrapError(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BootstrapError(f"Cannot reach Nautobot at {url}: {exc}") from exc


def existing_fields(url: str, token: str) -> dict[str, dict]:
    """Every Custom Field currently declared, keyed by name."""
    data = _request(f"{url}/api/extras/custom-fields/?limit=500", token)
    out = {}
    for row in data.get("results", []):
        field_type = row["type"]["value"] if isinstance(row.get("type"), dict) else row.get("type")
        out[row["key"]] = {
            "type": field_type,
            "content_types": sorted(row.get("content_types") or []),
        }
    return out


def diff_fields(present: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Split the required schema into (missing, mismatched).

    A field declared on the WRONG object type is as useless as a missing one
    and far harder to spot, so it is reported separately rather than treated
    as present.
    """
    missing, mismatched = [], []
    for spec in CUSTOM_FIELDS:
        current = present.get(spec["key"])
        if current is None:
            missing.append(spec)
            continue
        wanted_types = sorted(spec["content_types"])
        if current["type"] != spec["type"] or current["content_types"] != wanted_types:
            mismatched.append(
                f"{spec['key']}: declared as {current['type']} on "
                f"{','.join(current['content_types'])}, expected {spec['type']} on "
                f"{','.join(wanted_types)}"
            )
    return missing, mismatched


def create_field(url: str, token: str, spec: dict) -> None:
    _request(
        f"{url}/api/extras/custom-fields/",
        token,
        method="POST",
        payload={
            "key": spec["key"],
            "label": spec["label"],
            "type": spec["type"],
            "content_types": spec["content_types"],
            "description": spec["description"],
        },
    )


def locations(url: str, token: str) -> list[str]:
    data = _request(f"{url}/api/dcim/locations/?limit=200", token)
    return [row.get("name") or row.get("display") for row in data.get("results", [])]


def create_location(url: str, token: str, name: str) -> None:
    """Create the Location that fabric-wide intent hangs off.

    Needs a LocationType and a Status, neither of which this platform cares
    about -- any existing one will do, so an existing one is reused rather
    than inventing more objects in someone else's Nautobot.
    """
    types = _request(f"{url}/api/dcim/location-types/?limit=1", token).get("results", [])
    if not types:
        types = [_request(
            f"{url}/api/dcim/location-types/", token, method="POST",
            payload={"name": "Site", "nestable": True},
        )]
    statuses = _request(f"{url}/api/extras/statuses/?limit=50", token).get("results", [])
    active = next((s for s in statuses if str(s.get("name", "")).lower() == "active"), None)
    if active is None:
        raise BootstrapError(
            "No 'Active' Status found in Nautobot. Create one, or create the "
            "Location by hand and re-run without --location."
        )
    _request(
        f"{url}/api/dcim/locations/", token, method="POST",
        payload={"name": name, "location_type": types[0]["id"], "status": active["id"]},
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Declare the Nautobot Custom Fields this platform requires.",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Report what is missing and change nothing. Exit 1 if incomplete.",
    )
    parser.add_argument(
        "--location", metavar="NAME",
        help="Also ensure a Location with this name exists (fabric-wide intent hangs off it).",
    )
    args = parser.parse_args()

    url = os.environ.get("NAUTOBOT_URL", "http://localhost:8080").rstrip("/")
    token = os.environ.get("NAUTOBOT_TOKEN", "")
    if not token:
        print("ERROR: NAUTOBOT_TOKEN is not set.", file=sys.stderr)
        return 2

    try:
        present = existing_fields(url, token)
        missing, mismatched = diff_fields(present)
        current_locations = locations(url, token)
    except BootstrapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    total = len(CUSTOM_FIELDS)
    print(f"Nautobot: {url}")
    print(f"Custom Fields: {total - len(missing)}/{total} present")

    if mismatched:
        print("\nWRONG DEFINITION -- these exist but cannot hold what this platform writes:")
        for line in mismatched:
            print(f"  {line}")

    location_missing = bool(args.location) and args.location not in current_locations

    if args.verify:
        if missing:
            print(f"\nMISSING ({len(missing)}):")
            for spec in missing:
                print(f"  {spec['key']:<32} {spec['type']:<8} {','.join(spec['content_types'])}")
        if location_missing:
            print(f"\nMISSING Location: {args.location!r} (have: {current_locations or 'none'})")
        if missing or mismatched or location_missing:
            print(
                "\nIncomplete. Writes to an undeclared field are silently discarded by "
                "Nautobot -- tools will report success and persist nothing.\n"
                "Run without --verify to create what is missing."
            )
            return 1
        print("\nOK: schema complete. MCP tools will persist correctly.")
        return 0

    if mismatched:
        print(
            "\nRefusing to continue. A field declared on the wrong object type must be "
            "corrected or deleted by hand -- changing it automatically could orphan "
            "data already stored in it.",
            file=sys.stderr,
        )
        return 2

    for spec in missing:
        try:
            create_field(url, token, spec)
        except BootstrapError as exc:
            print(f"ERROR creating {spec['key']}: {exc}", file=sys.stderr)
            return 2
        print(f"  created {spec['key']:<32} {spec['type']:<8} {','.join(spec['content_types'])}")

    if location_missing:
        try:
            create_location(url, token, args.location)
        except BootstrapError as exc:
            print(f"ERROR creating Location {args.location!r}: {exc}", file=sys.stderr)
            return 2
        print(f"  created Location {args.location!r}")

    created = len(missing) + (1 if location_missing else 0)
    print(f"\nOK: {'nothing to do, already complete' if not created else f'{created} object(s) created'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
