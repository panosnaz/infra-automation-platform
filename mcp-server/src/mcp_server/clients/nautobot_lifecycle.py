"""Read, update and delete for ACI intent in Nautobot.

Every create_* in clients/nautobot.py writes intent; until this module nothing
could read it back as a whole, change an attribute, or remove an object, so a
mistake could only be fixed by editing raw JSON in the Nautobot UI.

Mixed into NautobotClient rather than added to nautobot.py, which is already
the largest file in the server. Same conventions as the create_* methods:
pynautobot errors become NautobotError, and every nested Custom Field is
DEEP-copied before it is changed -- pynautobot diffs a record against its own
cached state, so mutating a shallow copy silently sends nothing (measured
2026-09-16, see create_l3out_node_profile).
"""
from __future__ import annotations

import copy
from collections import defaultdict
from contextlib import contextmanager

import pynautobot

from mcp_server import intent_refs as refs
from mcp_server.errors import NautobotError

# Tenant-level JSON Custom Fields that carry ACI intent (as opposed to the
# status fields write_results.py maintains).
_TENANT_INTENT_FIELDS = (
    "aci_contracts", "aci_l3outs", "aci_l4l7_services", "aci_vrf_route_leaks",
    "aci_ospf_interface_policies", "aci_interface_policies", "aci_route_control",
    "aci_endpoint_security_groups", "aci_protocol_policies",
)
_STATUS_FIELDS = ("validation_status", "last_pipeline_id", "last_pipeline_url", "last_validated_at")

_VRF_ATTRIBUTE_FIELDS = {
    "ip_data_plane_learning": "aci_ip_data_plane_learning",
    "policy_control_enforcement_direction": "aci_policy_control_enforcement_direction",
    "policy_control_enforcement_mode": "aci_policy_control_enforcement_mode",
    # 2026-10-15: the VRF's vzAny preferred-group switch (closes NS-01).
    "preferred_group": "aci_vrf_preferred_group",
}
_BD_ATTRIBUTE_FIELDS = {
    "l3outs": "aci_bd_l3outs",
    "mac": "aci_bd_mac",
    "arp_flooding": "aci_bd_arp_flooding",
    "advertise_host_routes": "aci_bd_advertise_host_routes",
    "l2_unknown_unicast": "aci_bd_l2_unknown_unicast",
    "l3_unknown_multicast": "aci_bd_l3_unknown_multicast",
    "multi_destination": "aci_bd_multi_destination",
    "ep_move_detect_mode": "aci_bd_ep_move_detect_mode",
    "pim": "aci_bd_pim",
}

# What each kind of change does to deployment. The tenant webhook fires on
# tenancy.tenant create/update only (Platform-Administration-Guide.md), so
# only changes stored ON the Tenant start a pipeline by themselves.
DEPLOY_VIA_TENANT = (
    "Stored on the Tenant, so Nautobot's tenant webhook starts a pipeline; the "
    "APIC changes after the manual apply approval."
)
DEPLOY_NOT_TRIGGERED = (
    "This change is on a {what}, which does NOT fire the tenant webhook. It "
    "reaches the APIC on the next pipeline run (any change to this tenant, or "
    "a manual run)."
)


@contextmanager
def _nautobot_errors(what: str):
    try:
        yield
    except NautobotError:
        raise
    except pynautobot.RequestError as exc:
        raise NautobotError(f"Nautobot rejected {what}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - network/auth, mapped uniformly
        raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc


def _cf(record) -> dict:
    return copy.deepcopy(dict(getattr(record, "custom_fields", None) or {}))


def _tenant_id(record):
    tenant = getattr(record, "tenant", None)
    return getattr(tenant, "id", None) if tenant is not None else None


class LifecycleMixin:
    """Requires the host class to provide `api`, `_get_tenant_or_raise` and
    `_get_location_or_raise` (NautobotClient does)."""

    # ------------------------------------------------------------------
    # Snapshots: the shapes intent_refs reasons about.
    # ------------------------------------------------------------------

    def _tenant_bridge_domains(self, tenant_obj) -> list[dict]:
        """One entry per Prefix in the tenant, named the way the generator
        names it, with the VRFs it is assigned to."""
        vrf_names_by_prefix: dict = defaultdict(list)
        for vrf in self.api.ipam.vrfs.filter(tenant_id=tenant_obj.id):
            for assignment in self.api.ipam.vrf_prefix_assignments.filter(vrf=vrf.id):
                vrf_names_by_prefix[assignment.prefix.id].append(vrf.name)
        result = []
        for prefix in self.api.ipam.prefixes.filter(tenant_id=tenant_obj.id):
            result.append({
                "name": refs.bd_name_for_prefix(str(prefix.prefix), prefix.description),
                "prefix": str(prefix.prefix),
                "description": prefix.description or "",
                "vrfs": vrf_names_by_prefix.get(prefix.id, []),
                "cf": _cf(prefix),
                "record": prefix,
            })
        return result

    def _tenant_epgs(self, tenant_obj) -> list[dict]:
        """Every VLAN in the tenant. Not filtered to ACI EPGs here, because
        EVPN bridge domains are VLANs too and can reference a VRF."""
        return [
            {"name": v.name, "vid": v.vid, "description": v.description or "", "cf": _cf(v), "record": v}
            for v in self.api.ipam.vlans.filter(tenant_id=tenant_obj.id)
        ]

    def _all_tenants_snapshot(self) -> list[dict]:
        """Every tenant's Custom Fields and EPGs -- fabric objects (domains)
        are referenced across tenants, so a delete must look at all of them."""
        epgs_by_tenant: dict = defaultdict(list)
        for vlan in self.api.ipam.vlans.all():
            tid = _tenant_id(vlan)
            if tid is not None:
                epgs_by_tenant[tid].append({"name": vlan.name, "cf": _cf(vlan)})
        return [
            {"name": t.name, "cf": _cf(t), "epgs": epgs_by_tenant.get(t.id, [])}
            for t in self.api.tenancy.tenants.all()
        ]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_aci_tenants(self) -> list[dict]:
        with _nautobot_errors("tenant listing"):
            tenants = list(self.api.tenancy.tenants.all())
            vrf_count: dict = defaultdict(int)
            for vrf in self.api.ipam.vrfs.all():
                vrf_count[_tenant_id(vrf)] += 1
            bds: dict = defaultdict(set)
            for prefix in self.api.ipam.prefixes.all():
                bds[_tenant_id(prefix)].add(refs.bd_name_for_prefix(str(prefix.prefix), prefix.description))
            epg_count: dict = defaultdict(int)
            for vlan in self.api.ipam.vlans.all():
                if (vlan.custom_fields or {}).get("aci_application_profile"):
                    epg_count[_tenant_id(vlan)] += 1

        result = []
        for t in tenants:
            cf = dict(t.custom_fields or {})
            json_intent = {}
            for key in _TENANT_INTENT_FIELDS:
                value = cf.get(key)
                if isinstance(value, dict):
                    counts = {k: len(v) for k, v in value.items() if isinstance(v, list) and v}
                    if counts:
                        json_intent[key] = counts
            result.append({
                "name": t.name,
                "description": t.description or "",
                "system_tenant": refs.bare_tenant_name(t.name).lower() in refs.SYSTEM_TENANTS,
                "vrfs": vrf_count.get(t.id, 0),
                "bridge_domains": len(bds.get(t.id, ())),
                "epgs": epg_count.get(t.id, 0),
                "json_intent": json_intent,
                "validation_status": cf.get("validation_status"),
            })
        return sorted(result, key=lambda r: r["name"].lower())

    def get_tenant_intent(self, tenant: str) -> dict:
        with _nautobot_errors(f"tenant '{tenant}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            vrfs = list(self.api.ipam.vrfs.filter(tenant_id=tenant_obj.id))
            bridge_domains = self._tenant_bridge_domains(tenant_obj)
            vlans = self._tenant_epgs(tenant_obj)

        cf = dict(tenant_obj.custom_fields or {})

        vrf_out = []
        for vrf in vrfs:
            vcf = dict(vrf.custom_fields or {})
            attrs = {k: vcf[f] for k, f in _VRF_ATTRIBUTE_FIELDS.items() if vcf.get(f) is not None}
            vzany = {k: v for k, v in (vcf.get("aci_vzany_contracts") or {}).items() if v}
            protocol = {k: v for k, v in (vcf.get("aci_vrf_protocol_policies") or {}).items() if v}
            vrf_out.append({"name": vrf.name, "description": vrf.description or "", **attrs,
                            **({"vzany_contracts": vzany} if vzany else {}),
                            **({"protocol_policies": protocol} if protocol else {})})

        bd_out: dict[str, dict] = {}
        for bd in bridge_domains:
            entry = bd_out.setdefault(bd["name"], {"name": bd["name"], "vrfs": [], "subnets": [], "attributes": {}})
            entry["vrfs"] = sorted(set(entry["vrfs"]) | set(bd["vrfs"]))
            no_subnet, scope_marker, text = refs.parse_bd_description(bd["description"])
            if not no_subnet:
                entry["subnets"].append({
                    "prefix": bd["prefix"],
                    "gateway_ip": bd["cf"].get("aci_gateway_ip"),
                    "scope": bd["cf"].get("aci_bd_subnet_scope") or scope_marker or "private",
                })
            if text:
                entry["description"] = text
            for key, field in _BD_ATTRIBUTE_FIELDS.items():
                if bd["cf"].get(field) not in (None, "", []):
                    entry["attributes"].setdefault(key, bd["cf"][field])

        aps: dict[str, list] = defaultdict(list)
        for vlan in vlans:
            vcf = vlan["cf"]
            ap = vcf.get("aci_application_profile")
            if not ap or not vcf.get("aci_epg_bridge_domain"):
                continue
            epg = {"name": vlan["name"], "vid": vlan["vid"], "bridge_domain": vcf["aci_epg_bridge_domain"]}
            if vlan["description"]:
                epg["description"] = vlan["description"]
            if vcf.get("aci_epg_preferred_group_member"):
                epg["preferred_group_member"] = True
            for field, key in (("aci_epg_contracts", "contracts"), ("aci_epg_domains", "domains"),
                               ("aci_epg_subnets", "subnets"), ("aci_static_paths", "static_paths")):
                if vcf.get(field):
                    epg[key] = vcf[field]
            aps[ap].append(epg)

        return {
            "tenant": tenant_obj.name,
            "description": tenant_obj.description or "",
            "system_tenant": refs.bare_tenant_name(tenant_obj.name).lower() in refs.SYSTEM_TENANTS,
            "vrfs": vrf_out,
            "bridge_domains": list(bd_out.values()),
            "application_profiles": [{"name": ap, "epgs": epgs} for ap, epgs in aps.items()],
            "json_intent": {k: cf[k] for k in _TENANT_INTENT_FIELDS if cf.get(k)},
            "deployment_status": {k: cf.get(k) for k in _STATUS_FIELDS},
        }

    def get_fabric_intent(self, location: str | None = None) -> dict:
        with _nautobot_errors("fabric intent"):
            location_obj = self._get_location_or_raise(location)
            # `location`, not `location_id`: Nautobot 2.x rejects the latter with a 400.
            devices = list(self.api.dcim.devices.filter(location=location_obj.id))
        cf = dict(location_obj.custom_fields or {})
        fabric_nodes = []
        for device in devices:
            dcf = dict(device.custom_fields or {})
            if dcf.get("aci_node_id") is None:
                continue
            fabric_nodes.append({
                "name": device.name,
                "role": getattr(getattr(device, "role", None), "name", None),
                "node_id": dcf.get("aci_node_id"),
                "pod_id": dcf.get("aci_pod_id"),
                "serial": device.serial or "",
            })
        by_node: dict = defaultdict(list)
        with _nautobot_errors("node management addresses"):
            for addr in self.node_mgmt_addresses():
                by_node[addr["node_id"]].append({k: addr[k] for k in ("type", "address", "gateway", "epg")})
        for node in fabric_nodes:
            node["management"] = by_node.get(node["node_id"], [])
        return {
            "location": location_obj.name,
            "fabric_policies": cf.get("aci_fabric_policies") or {},
            "aaa_policies": cf.get("aci_aaa_policies") or {},
            "fabric_nodes": sorted(fabric_nodes, key=lambda n: n["node_id"]),
        }

    # ------------------------------------------------------------------
    # Update -- typed, one object kind each. Only fields passed (not None)
    # change. Clearing is deliberately not offered: removing a value from
    # Nautobot makes Terraform STOP MANAGING the attribute, it does not put
    # APIC back to its default. Set the default value explicitly instead.
    # ------------------------------------------------------------------

    def update_vrf(self, tenant: str, name: str, description: str | None = None, **attributes) -> dict:
        with _nautobot_errors(f"VRF '{name}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            vrf = self.api.ipam.vrfs.get(name=name, tenant_id=tenant_obj.id)
            if vrf is None:
                known = ", ".join(sorted(v.name for v in self.api.ipam.vrfs.filter(tenant_id=tenant_obj.id))) or "none"
                raise NautobotError(f"VRF '{name}' not found in tenant '{tenant}' (known: {known})")
            # L3Out depth (2026-10-16): VRF-wide BGP timers / OSPF timers /
            # route tag, by policy name; "" clears (Terraform then writes the
            # empty name, i.e. tn-common's default -- proven clean).
            protocol_refs = {k: attributes.pop(k) for k in ("bgp_timers_policy", "ospf_timers_policy", "route_tag_policy")
                             if attributes.get(k) is not None}
            changes = {_VRF_ATTRIBUTE_FIELDS[k]: v for k, v in attributes.items() if v is not None}
            if protocol_refs:
                from mcp_server.clients.nautobot_l3out_depth import L3OutDepthMixin
                current = dict(_cf(vrf).get("aci_vrf_protocol_policies") or {})
                for key, value in protocol_refs.items():
                    if value == "":
                        current.pop(key, None)
                    else:
                        L3OutDepthMixin.require_protocol_policy(_cf(tenant_obj), tenant, key, value)
                        current[key] = value
                changes["aci_vrf_protocol_policies"] = current
            payload: dict = {}
            if changes:
                payload["custom_fields"] = {**_cf(vrf), **changes}
            if description is not None:
                payload["description"] = description
            vrf.update(payload)
        return {"tenant": tenant, "vrf": name, "changed": {**changes, **({"description": description} if description is not None else {})}}

    def update_bridge_domain(
        self, tenant: str, name: str, description: str | None = None,
        subnet_scope: str | None = None, **attributes,
    ) -> dict:
        """Applies to EVERY Prefix of the bridge domain. A multi-subnet BD is
        several Prefixes, and the generator takes BD-level attributes from
        whichever it reads first -- updating only one would make the result
        depend on Nautobot's row order."""
        with _nautobot_errors(f"bridge domain '{name}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            bridge_domains = self._tenant_bridge_domains(tenant_obj)
            targets = [bd for bd in bridge_domains if bd["name"] == name]
            if not targets:
                known = ", ".join(sorted({bd["name"] for bd in bridge_domains})) or "none"
                raise NautobotError(f"Bridge domain '{name}' not found in tenant '{tenant}' (known: {known})")

            if attributes.get("l3outs") is not None:
                known_l3outs = {o.get("name") for o in (dict(tenant_obj.custom_fields or {}).get("aci_l3outs") or {}).get("l3outs") or []}
                missing = sorted(set(attributes["l3outs"]) - known_l3outs)
                if missing:
                    raise NautobotError(
                        f"L3Out(s) {missing} do not exist in tenant '{tenant}' -- the generator "
                        "rejects a bridge domain associated with an undeclared L3Out"
                    )

            changes = {_BD_ATTRIBUTE_FIELDS[k]: v for k, v in attributes.items() if v is not None}
            if subnet_scope is not None:
                changes["aci_bd_subnet_scope"] = "" if subnet_scope == "private" else subnet_scope

            bare = refs.bare_tenant_name(tenant_obj.name)
            for bd in targets:
                payload: dict = {}
                if changes:
                    payload["custom_fields"] = {**bd["cf"], **changes}
                if description is not None or subnet_scope is not None:
                    no_subnet, marker, text = refs.parse_bd_description(bd["description"])
                    payload["description"] = refs.compose_bd_description(
                        name, bare, no_subnet=no_subnet,
                        # The Custom Field becomes the single source of the scope;
                        # leaving the marker would let the old scope win.
                        scope_marker=None if subnet_scope is not None else marker,
                        text=description if description is not None else text,
                    )
                bd["record"].update(payload)
        changed = dict(changes)
        if description is not None:
            changed["description"] = description
        return {"tenant": tenant, "bridge_domain": name, "prefixes_updated": [bd["prefix"] for bd in targets], "changed": changed}

    def update_epg(
        self, tenant: str, application_profile: str, name: str,
        bridge_domain: str | None = None, description: str | None = None,
        preferred_group_member: bool | None = None,
    ) -> dict:
        with _nautobot_errors(f"EPG '{name}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            vlan = self.api.ipam.vlans.get(name=name, tenant_id=tenant_obj.id, cf_aci_application_profile=application_profile)
            if vlan is None:
                raise NautobotError(
                    f"EPG '{name}' not found in tenant '{tenant}' / application profile '{application_profile}'"
                )
            changes: dict = {}
            if bridge_domain is not None:
                known = {bd["name"] for bd in self._tenant_bridge_domains(tenant_obj)}
                if bridge_domain not in known:
                    raise NautobotError(
                        f"Bridge domain '{bridge_domain}' does not exist in tenant '{tenant}' "
                        f"(known: {', '.join(sorted(known)) or 'none'})"
                    )
                changes["aci_epg_bridge_domain"] = bridge_domain
            if preferred_group_member is not None:
                changes["aci_epg_preferred_group_member"] = preferred_group_member
            payload: dict = {}
            if changes:
                payload["custom_fields"] = {**_cf(vlan), **changes}
            if description is not None:
                payload["description"] = description
            vlan.update(payload)
        changed = dict(changes)
        if description is not None:
            changed["description"] = description
        return {"tenant": tenant, "application_profile": application_profile, "epg": name, "changed": changed}

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @staticmethod
    def _refuse_if_referenced(kind: str, name: str, found: list[str]) -> None:
        if found:
            listed = "; ".join(found)
            raise NautobotError(
                f"Refusing to delete {kind.replace('_', ' ')} '{name}': still referenced -- {listed}. "
                "Remove or repoint those first; deleting now would leave the next "
                "pipeline with a dangling reference."
            )

    def delete_tenant_object(
        self, tenant: str, kind: str, name: str,
        application_profile: str | None = None, l3out: str | None = None,
    ) -> dict:
        if kind not in refs.TENANT_KINDS:
            raise NautobotError(f"Unknown tenant object kind '{kind}'")
        with _nautobot_errors(f"{kind} '{name}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            tenant_cf = _cf(tenant_obj)

            if kind == "epg":
                vlan = self.api.ipam.vlans.get(name=name, tenant_id=tenant_obj.id, cf_aci_application_profile=application_profile)
                if vlan is None:
                    raise NautobotError(
                        f"EPG '{name}' not found in tenant '{tenant}' / application profile '{application_profile}'"
                    )
                self._refuse_if_referenced(kind, name, refs.tenant_references(
                    kind, name, tenant_cf, application_profile=application_profile))
                vlan.delete()
                return {"tenant": tenant, "kind": kind, "name": name, "removed": 1,
                        "deploy": DEPLOY_NOT_TRIGGERED.format(what="VLAN (EPG)")}

            bridge_domains = self._tenant_bridge_domains(tenant_obj)
            epgs = self._tenant_epgs(tenant_obj)
            vrfs = [{"name": v.name, "cf": _cf(v)} for v in self.api.ipam.vrfs.filter(tenant_id=tenant_obj.id)]
            found = refs.tenant_references(kind, name, tenant_cf, bridge_domains, epgs, l3out=l3out, vrfs=vrfs)

            if kind == "vrf":
                vrf = self.api.ipam.vrfs.get(name=name, tenant_id=tenant_obj.id)
                if vrf is None:
                    raise NautobotError(f"VRF '{name}' not found in tenant '{tenant}'")
                self._refuse_if_referenced(kind, name, found)
                vrf.delete()
                return {"tenant": tenant, "kind": kind, "name": name, "removed": 1,
                        "deploy": DEPLOY_NOT_TRIGGERED.format(what="VRF")}

            if kind == "bridge_domain":
                targets = [bd for bd in bridge_domains if bd["name"] == name]
                if not targets:
                    known = ", ".join(sorted({bd["name"] for bd in bridge_domains})) or "none"
                    raise NautobotError(f"Bridge domain '{name}' not found in tenant '{tenant}' (known: {known})")
                self._refuse_if_referenced(kind, name, found)
                for bd in targets:
                    bd["record"].delete()
                return {"tenant": tenant, "kind": kind, "name": name, "removed": len(targets),
                        "prefixes_deleted": [bd["prefix"] for bd in targets],
                        "deploy": DEPLOY_NOT_TRIGGERED.format(what="Prefix (bridge domain)")}

            if kind == "route_control_profile":
                if not l3out:
                    raise NautobotError("Deleting a route_control_profile needs l3out= (route maps live inside an L3Out)")
                data = _cf_dict(tenant_cf, "aci_l3outs")
                out = next((o for o in data.get("l3outs") or [] if o.get("name") == l3out), None)
                if out is None:
                    raise NautobotError(f"L3Out '{l3out}' not found in tenant '{tenant}'")
                kept, removed = refs.remove_named(list(out.get("route_control_profiles") or []), name)
                if not removed:
                    raise NautobotError(f"Route map '{name}' not found in L3Out '{l3out}'")
                self._refuse_if_referenced(kind, name, found)
                out["route_control_profiles"] = kept
                tenant_cf["aci_l3outs"] = data
                tenant_obj.update({"custom_fields": tenant_cf})
                return {"tenant": tenant, "kind": kind, "name": name, "l3out": l3out, "removed": removed,
                        "deploy": DEPLOY_VIA_TENANT}

            field, list_key = refs.TENANT_JSON_KINDS[kind]
            data = _cf_dict(tenant_cf, field)
            entries = list(data.get(list_key) or [])
            kept, removed = refs.remove_named(entries, name)
            if not removed:
                known = ", ".join(sorted(str(e.get("name")) for e in entries if isinstance(e, dict))) or "none"
                raise NautobotError(f"{kind.replace('_', ' ').capitalize()} '{name}' not found in tenant '{tenant}' (known: {known})")
            self._refuse_if_referenced(kind, name, found)
            _set_or_drop(data, list_key, kept)
            tenant_cf[field] = data
            tenant_obj.update({"custom_fields": tenant_cf})
        return {"tenant": tenant, "kind": kind, "name": name, "removed": removed, "deploy": DEPLOY_VIA_TENANT}

    def delete_fabric_object(self, kind: str, name: str, location: str | None = None) -> dict:
        if kind not in refs.FABRIC_KINDS:
            raise NautobotError(f"Unknown fabric object kind '{kind}'")
        field, list_key = refs.FABRIC_KINDS[kind]
        with _nautobot_errors(f"{kind} '{name}'"):
            location_obj = self._get_location_or_raise(location)
            location_cf = _cf(location_obj)
            data = _cf_dict(location_cf, field)
            entries = list(data.get(list_key) or [])
            kept, removed = refs.remove_named(entries, name)
            if not removed:
                known = ", ".join(sorted(str(e.get("name")) for e in entries if isinstance(e, dict))) or "none"
                raise NautobotError(
                    f"{kind.replace('_', ' ').capitalize()} '{name}' not found on Location "
                    f"'{location_obj.name}' (known: {known})"
                )
            tenants = self._all_tenants_snapshot() if kind in refs.FABRIC_KINDS_NEEDING_TENANTS else []
            mgmt = self.node_mgmt_addresses() if kind == "inband_mgmt_epg" else []
            self._refuse_if_referenced(kind, name, refs.fabric_references(kind, name, location_cf, tenants, mgmt))
            _set_or_drop(data, list_key, kept)
            location_cf[field] = data
            location_obj.update({"custom_fields": location_cf})
        return {
            "location": location_obj.name, "kind": kind, "name": name, "removed": removed,
            "deploy": DEPLOY_NOT_TRIGGERED.format(what="Location (fabric-wide policy)"),
        }

    def _get_epg_vlan(self, tenant_obj, tenant: str, application_profile: str, epg: str):
        vlan = self.api.ipam.vlans.get(name=epg, tenant_id=tenant_obj.id, cf_aci_application_profile=application_profile)
        if vlan is None:
            raise NautobotError(f"EPG '{epg}' not found in tenant '{tenant}' / application profile '{application_profile}'")
        return vlan

    def unbind_epg_contract(self, tenant: str, application_profile: str, epg: str, contract: str, relation: str) -> dict:
        with _nautobot_errors(f"contract binding on EPG '{epg}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            vlan = self._get_epg_vlan(tenant_obj, tenant, application_profile, epg)
            fields = _cf(vlan)
            bound = dict(fields.get("aci_epg_contracts") or {})
            current = list(bound.get(relation) or [])
            if contract not in current:
                raise NautobotError(
                    f"EPG '{epg}' does not have contract '{contract}' as {relation} "
                    f"(it has: {', '.join(current) or 'none'})"
                )
            bound[relation] = [c for c in current if c != contract]
            fields["aci_epg_contracts"] = bound
            vlan.update({"custom_fields": fields})
        return {"tenant": tenant, "epg": epg, "provided": bound.get("provided", []), "consumed": bound.get("consumed", []),
                "deploy": DEPLOY_NOT_TRIGGERED.format(what="VLAN (EPG)")}

    def unbind_epg_domain(self, tenant: str, application_profile: str, epg: str, domain: str, domain_type: str) -> dict:
        with _nautobot_errors(f"domain binding on EPG '{epg}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            vlan = self._get_epg_vlan(tenant_obj, tenant, application_profile, epg)
            fields = _cf(vlan)
            existing = dict(fields.get("aci_epg_domains") or {})
            domains = list(existing.get("domains") or [])
            kept = [d for d in domains if not (d.get("name") == domain and d.get("domain_type") == domain_type)]
            if len(kept) == len(domains):
                have = ", ".join(f"{d.get('name')} ({d.get('domain_type')})" for d in domains) or "none"
                raise NautobotError(f"EPG '{epg}' is not bound to {domain_type} domain '{domain}' (bound: {have})")
            fields["aci_epg_domains"] = {**existing, "domains": kept}
            vlan.update({"custom_fields": fields})
        return {"tenant": tenant, "epg": epg, "domains": kept,
                "deploy": DEPLOY_NOT_TRIGGERED.format(what="VLAN (EPG)")}

    def delete_tenant(self, name: str) -> dict:
        """Delete a tenant and every VRF, Prefix (bridge domain) and VLAN
        (EPG) it owns. The caller (the tool) has already checked the typed
        confirmation; this method still refuses ACI system tenants itself, so
        no other caller can bypass that."""
        if refs.bare_tenant_name(name).lower() in refs.SYSTEM_TENANTS:
            raise NautobotError(f"Refusing to delete '{name}': it is an ACI system tenant (common/infra/mgmt)")
        with _nautobot_errors(f"tenant '{name}'"):
            tenant_obj = self._get_tenant_or_raise(name)
            # Objects this tool does not own -- deleting the tenant would fail
            # on them halfway through, after the VRFs were already gone.
            blockers = [f"device '{d.name}'" for d in self.api.dcim.devices.filter(tenant_id=tenant_obj.id)]
            blockers += [f"IP address {ip.address}" for ip in self.api.ipam.ip_addresses.filter(tenant_id=tenant_obj.id)]
            if blockers:
                raise NautobotError(
                    f"Refusing to delete tenant '{name}': it also owns objects this tool does not manage "
                    f"({'; '.join(blockers[:10])}{' ...' if len(blockers) > 10 else ''}). Reassign or remove them first."
                )
            vlans = list(self.api.ipam.vlans.filter(tenant_id=tenant_obj.id))
            prefixes = list(self.api.ipam.prefixes.filter(tenant_id=tenant_obj.id))
            vrfs = list(self.api.ipam.vrfs.filter(tenant_id=tenant_obj.id))
            for record in (*vlans, *prefixes, *vrfs):
                record.delete()
            tenant_obj.delete()
            # create_vrf gives every tenant its own IPAM Namespace (named after
            # it). Leaving it behind is harmless but is debris nothing else
            # owns, so remove it -- only if nothing else is still in it.
            namespace_deleted = False
            namespace = self.api.ipam.namespaces.get(name=tenant_obj.name)
            if namespace is not None and not (
                self.api.ipam.prefixes.filter(namespace=namespace.id)
                or self.api.ipam.vrfs.filter(namespace=namespace.id)
            ):
                namespace.delete()
                namespace_deleted = True
        return {
            "tenant": name,
            "deleted": {"epgs_and_vlans": len(vlans), "prefixes": len(prefixes), "vrfs": len(vrfs)},
            "namespace_deleted": namespace_deleted,
            "deploy": (
                "Nautobot's tenant webhook does not fire on delete. On the next pipeline run the "
                "generator no longer emits this tenant and terraform plans to DESTROY it on the "
                "APIC -- review that plan before approving the apply."
            ),
        }


def _cf_dict(fields: dict, key: str) -> dict:
    value = fields.get(key)
    return value if isinstance(value, dict) else {}


def _set_or_drop(data: dict, key: str, values: list) -> None:
    """Write the remaining entries, or remove the key once none remain -- a
    delete should leave intent as it found it, not an empty list behind."""
    if values:
        data[key] = values
    else:
        data.pop(key, None)
