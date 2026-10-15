"""Fabric-wide policies: NTP, DNS, SNMP, COOP, ISIS, fault lifecycle, syslog
(2026-10-13).

Terraform has applied these from the Location's `aci_fabric_policies` JSON
since ADR-020 Phases C/E/G; until now nothing but a hand edit could write
them. Each is an APIC singleton that always exists (uni/fabric/time-default,
dnsp-default, snmppol-default, pol-default, isisDomP-default, and three under
moncommon), so the tools SET them rather than create them, and
`reset_fabric_policy` removes the intent so Terraform puts APIC back to its
defaults.

SNMP community strings are credentials. Nautobot stores only a reference
name; the string itself is supplied at apply time through the sensitive
Terraform variable `snmp_community_strings`, keyed by that reference -- the
same rule as Local User passwords and vCenter credentials. It never reaches
Nautobot or the committed YAML.
"""
from __future__ import annotations

from mcp_server.clients.nautobot_lifecycle import DEPLOY_NOT_TRIGGERED, _nautobot_errors
from mcp_server.errors import NautobotError

_DEPLOY = DEPLOY_NOT_TRIGGERED.format(what="Location (fabric-wide policy)")

# policy name used by the tools -> key in aci_fabric_policies
SINGLETON_KEYS = {
    "ntp": "ntp",
    "dns": "dns",
    "snmp": "snmp",
    "coop": "coop",
    "isis": "isis",
    "fault_lifecycle": "fault_lifecycle",
    "syslog_message": "syslog_system_msg",
    "syslog_rate_limit": "syslog_rate_limit",
    # 2026-10-14
    "bgp_route_reflector": "bgp_route_reflector",
    "pod_profile": "pod_profile",
}

# What removing the intent does on the APIC, per policy. aci_rest_managed
# resets the singleton through content_on_destroy; the typed COOP/ISIS
# resources cannot delete their singleton and leave the last value in place
# (ADR-020 Phase E, confirmed live) -- see NS-21.
_RESET_EFFECT = {
    "coop": "APIC KEEPS the last COOP type -- the provider cannot delete or reset this singleton. Set the original value explicitly (APIC default: compatible) before resetting.",
    "isis": "APIC KEEPS the last ISIS MTU / metric -- the provider cannot delete or reset this singleton. Set the original values explicitly (APIC defaults: MTU 1492, metric 32) before resetting.",
}
_RESET_DEFAULT = "Terraform restores APIC's default for this singleton on the next apply (content_on_destroy)."
_RESET_EFFECT.update({
    "bgp_route_reflector": "Terraform removes the fabric AS and the route-reflector spines on the next apply -- "
                           "external routes stop being distributed across the fabric.",
    "pod_profile": "Terraform removes the Pod Policy Group assignment from the default pod selector on the next apply.",
})


class FabricPolicyMixin:
    """Requires `_fabric` (AccessMixin) on the host class."""

    def _singleton(self, location, policy: str, changes: dict, validate=None) -> dict:
        key = SINGLETON_KEYS[policy]
        location_obj, fields, fabric = self._fabric(location)
        current = dict(fabric.get(key) or {})
        applied = {k: v for k, v in changes.items() if v is not None}
        candidate = {**current, **applied}
        if validate:
            validate(candidate)
        fabric[key] = candidate
        location_obj.update({"custom_fields": fields})
        return {"location": location_obj.name, "policy": policy, policy: candidate, "changed": applied, "deploy": _DEPLOY}

    def _item(self, location, policy: str, list_key: str, ident: str, ident_value, mode: str,
              entry: dict | None = None, label: str = "") -> dict:
        """Create, update or delete one entry in a singleton's list."""
        key = SINGLETON_KEYS[policy]
        location_obj, fields, fabric = self._fabric(location)
        container = dict(fabric.get(key) or {})
        items = list(container.get(list_key) or [])
        existing = next((i for i in items if i.get(ident) == ident_value), None)
        known = ", ".join(str(i.get(ident)) for i in items) or "none"
        if mode == "create":
            if existing is not None:
                raise NautobotError(f"{label} '{ident_value}' already exists -- use the update tool to change it")
            items.append({ident: ident_value, **{k: v for k, v in (entry or {}).items() if v is not None}})
        elif mode == "update":
            if existing is None:
                raise NautobotError(f"{label} '{ident_value}' not found (known: {known})")
            existing.update({k: v for k, v in (entry or {}).items() if v is not None})
        else:
            if existing is None:
                raise NautobotError(f"{label} '{ident_value}' not found (known: {known})")
            items = [i for i in items if i.get(ident) != ident_value]
        if items:
            container[list_key] = items
        else:
            container.pop(list_key, None)
        if container:
            fabric[key] = container
        else:
            fabric.pop(key, None)
        location_obj.update({"custom_fields": fields})
        return {"location": location_obj.name, "policy": policy, list_key: items, "deploy": _DEPLOY}

    # --- NTP --------------------------------------------------------------------

    def set_ntp_policy(self, location, admin_state) -> dict:
        with _nautobot_errors("NTP policy"):
            return self._singleton(location, "ntp", {"admin_state": admin_state})

    def create_ntp_server(self, location, address, preferred=False, min_poll=4, max_poll=6) -> dict:
        with _nautobot_errors(f"NTP server {address}"):
            return self._item(location, "ntp", "servers", "address", address, "create",
                              {"preferred": preferred, "min_poll": min_poll, "max_poll": max_poll}, "NTP server")

    def update_ntp_server(self, location, address, preferred=None, min_poll=None, max_poll=None) -> dict:
        with _nautobot_errors(f"NTP server {address}"):
            _, _, fabric = self._fabric(location)
            current = next((s for s in (fabric.get("ntp") or {}).get("servers") or [] if s.get("address") == address), {})
            lo = min_poll if min_poll is not None else current.get("min_poll", 4)
            hi = max_poll if max_poll is not None else current.get("max_poll", 6)
            if lo > hi:
                raise NautobotError(f"min_poll ({lo}) cannot exceed max_poll ({hi})")
            return self._item(location, "ntp", "servers", "address", address, "update",
                              {"preferred": preferred, "min_poll": min_poll, "max_poll": max_poll}, "NTP server")

    def delete_ntp_server(self, location, address) -> dict:
        with _nautobot_errors(f"NTP server {address}"):
            return self._item(location, "ntp", "servers", "address", address, "delete", label="NTP server")

    # --- DNS --------------------------------------------------------------------

    def create_dns_server(self, location, address, preferred=False) -> dict:
        with _nautobot_errors(f"DNS server {address}"):
            return self._item(location, "dns", "servers", "address", address, "create", {"preferred": preferred}, "DNS server")

    def update_dns_server(self, location, address, preferred=None) -> dict:
        with _nautobot_errors(f"DNS server {address}"):
            return self._item(location, "dns", "servers", "address", address, "update", {"preferred": preferred}, "DNS server")

    def delete_dns_server(self, location, address) -> dict:
        with _nautobot_errors(f"DNS server {address}"):
            return self._item(location, "dns", "servers", "address", address, "delete", label="DNS server")

    def _one_default_domain(self, location, name) -> None:
        """APIC allows one default DNS search domain: making this one the
        default demotes any other, rather than leaving two."""
        location_obj, fields, fabric = self._fabric(location)
        dns = dict(fabric.get("dns") or {})
        domains = [dict(d, is_default=False) if d.get("name") != name and d.get("is_default") else d
                   for d in dns.get("domains") or []]
        if domains != (dns.get("domains") or []):
            dns["domains"] = domains
            fabric["dns"] = dns
            location_obj.update({"custom_fields": fields})

    def create_dns_domain(self, location, name, is_default=False) -> dict:
        with _nautobot_errors(f"DNS domain {name}"):
            if is_default:
                self._one_default_domain(location, name)
            return self._item(location, "dns", "domains", "name", name, "create", {"is_default": is_default}, "DNS domain")

    def update_dns_domain(self, location, name, is_default=None) -> dict:
        with _nautobot_errors(f"DNS domain {name}"):
            if is_default:
                self._one_default_domain(location, name)
            return self._item(location, "dns", "domains", "name", name, "update", {"is_default": is_default}, "DNS domain")

    def delete_dns_domain(self, location, name) -> dict:
        with _nautobot_errors(f"DNS domain {name}"):
            return self._item(location, "dns", "domains", "name", name, "delete", label="DNS domain")

    # --- SNMP -------------------------------------------------------------------

    def set_snmp_policy(self, location, admin_state=None, contact=None, system_location=None) -> dict:
        with _nautobot_errors("SNMP policy"):
            return self._singleton(location, "snmp",
                                   {"admin_state": admin_state, "contact": contact, "location": system_location})

    def create_snmp_community(self, location, ref) -> dict:
        with _nautobot_errors(f"SNMP community reference {ref}"):
            result = self._item(location, "snmp", "communities", "ref", ref, "create", label="SNMP community reference")
        result["secret"] = (
            f"Only the reference '{ref}' is stored. Supply the community string at apply time in the "
            f"sensitive Terraform variable snmp_community_strings, e.g. TF_VAR_snmp_community_strings="
            f"'{{\"{ref}\": \"<string from Vault>\"}}' -- the plan fails if it is missing."
        )
        return result

    def delete_snmp_community(self, location, ref) -> dict:
        with _nautobot_errors(f"SNMP community reference {ref}"):
            return self._item(location, "snmp", "communities", "ref", ref, "delete", label="SNMP community reference")

    # --- COOP / ISIS / fault lifecycle / syslog ---------------------------------

    def set_coop_policy(self, location, type) -> dict:
        with _nautobot_errors("COOP policy"):
            return self._singleton(location, "coop", {"type": type})

    def set_isis_policy(self, location, mtu=None, redistrib_metric=None) -> dict:
        with _nautobot_errors("ISIS policy"):
            return self._singleton(location, "isis", {"mtu": mtu, "redistrib_metric": redistrib_metric})

    def set_fault_lifecycle_policy(self, location, soak=None, retain=None, clear=None) -> dict:
        with _nautobot_errors("fault lifecycle policy"):
            return self._singleton(location, "fault_lifecycle", {"soak": soak, "retain": retain, "clear": clear})

    def set_syslog_message_policy(self, location, admin_state) -> dict:
        with _nautobot_errors("syslog system message policy"):
            return self._singleton(location, "syslog_message", {"admin_state": admin_state})

    def set_syslog_rate_limit(self, location, enabled=None, limit_per_sec=None) -> dict:
        with _nautobot_errors("syslog rate limit"):
            return self._singleton(location, "syslog_rate_limit", {"enabled": enabled, "limit_per_sec": limit_per_sec})

    # --- reset --------------------------------------------------------------------

    def reset_fabric_policy(self, location, policy) -> dict:
        key = SINGLETON_KEYS[policy]
        with _nautobot_errors(f"{policy} policy"):
            location_obj, fields, fabric = self._fabric(location)
            if key not in fabric:
                raise NautobotError(f"No {policy} intent on Location '{location_obj.name}' -- nothing to reset")
            removed = fabric.pop(key)
            location_obj.update({"custom_fields": fields})
        return {"location": location_obj.name, "policy": policy, "removed": removed,
                "effect": _RESET_EFFECT.get(policy, _RESET_DEFAULT), "deploy": _DEPLOY}

    # --- BGP route reflector policy (2026-10-14) ----------------------------------
    #
    # The fabric's MP-BGP: one AS for the whole fabric and the spines that act
    # as route reflectors. Without it, routes an L3Out learns never leave the
    # border leaf. Written to the default BGP instance policy
    # (uni/fabric/bgpInstP-default); it takes effect through a Pod Policy Group
    # that names it, assigned to the pod -- see assign_pod_policy_group.

    def set_bgp_route_reflector_policy(self, location, asn) -> dict:
        with _nautobot_errors("BGP route reflector policy"):
            result = self._singleton(location, "bgp_route_reflector", {"asn": asn})
        result["warning"] = (
            "Changing the fabric AS on a running fabric resets every MP-BGP session in it. "
            "It takes effect only once a Pod Policy Group is assigned to the pod "
            "(assign_pod_policy_group) -- the group resolves to this 'default' policy."
        )
        return result

    def create_bgp_route_reflector_node(self, location, node, pod_id=None) -> dict:
        with _nautobot_errors(f"route reflector node {node}"):
            device = self._resolve_fabric_device(node)
            role = getattr(getattr(device, "role", None), "name", "") or ""
            if role.lower() != "spine":
                raise NautobotError(
                    f"'{device.name}' is a {role or 'device without a role'}, not a spine -- "
                    "only spines can be BGP route reflectors in ACI"
                )
            node_id = int(device.custom_fields["aci_node_id"])
            pod = int(pod_id or device.custom_fields.get("aci_pod_id") or 1)
            _, _, fabric = self._fabric(location)
            if any(n.get("node_id") == node_id for n in (fabric.get("bgp_route_reflector") or {}).get("nodes") or []):
                # _item's message points at an update tool; a node has nothing to update.
                raise NautobotError(f"'{device.name}' (node {node_id}) is already a route reflector")
            return self._item(location, "bgp_route_reflector", "nodes", "node_id", node_id, "create",
                              {"pod_id": pod}, "Route reflector node")

    def delete_bgp_route_reflector_node(self, location, node_id) -> dict:
        with _nautobot_errors(f"route reflector node {node_id}"):
            return self._item(location, "bgp_route_reflector", "nodes", "node_id", int(node_id), "delete",
                              label="Route reflector node")

    def assign_pod_policy_group(self, location, policy_group) -> dict:
        """Assign a Pod Policy Group to the default pod selector (all pods).
        This is what makes the BGP route reflector policy -- and the other
        pod-level policies the group names -- apply."""
        with _nautobot_errors(f"pod policy group {policy_group}"):
            _, _, fabric = self._fabric(location)
            if self._named(fabric, "pod_policy_groups", policy_group) is None:
                known = ", ".join(sorted(g.get("name", "") for g in fabric.get("pod_policy_groups") or [])) or "none"
                raise NautobotError(
                    f"Pod Policy Group '{policy_group}' does not exist (known: {known}) -- create it with "
                    "create_pod_policy_group first"
                )
            return self._singleton(location, "pod_profile", {"policy_group": policy_group})
