"""Port-channels, vPC and node management addresses (2026-10-12).

Two storage models, chosen per object:

* PC/vPC policy objects -- LACP policies, vPC domains (explicit protection
  groups), PC/vPC interface policy groups, in-band management EPGs -- are
  fabric-wide policy with no Nautobot model, so they live in the Location's
  existing `aci_fabric_policies` JSON next to the access policies they work
  with. No new Custom Field.
* Node management addresses are real IP Addresses, so they are native Nautobot
  IP Addresses on the switch's management interface, marked by the
  `aci_mgmt_*` Custom Fields. IPAM then refuses a duplicate address and ties
  the address to the device for free -- neither of which a JSON entry would do.

Same conventions as the rest of the client: NautobotError for anything the
caller can act on, and nested Custom Fields deep-copied before they change.
"""
from __future__ import annotations

import copy
import ipaddress

import pynautobot

from mcp_server import intent_refs as refs
from mcp_server.clients.nautobot_lifecycle import DEPLOY_NOT_TRIGGERED, _nautobot_errors
from mcp_server.errors import NautobotError

MGMT_INTERFACE = {"out_of_band": "mgmt0", "in_band": "inband-mgmt"}
_DEPLOY_LOCATION = DEPLOY_NOT_TRIGGERED.format(what="Location (fabric-wide policy)")
_DEPLOY_IP = DEPLOY_NOT_TRIGGERED.format(what="IP Address (node management)")


class AccessMixin:
    """Requires `api` and `_get_location_or_raise` from the host class."""

    # ------------------------------------------------------------------
    # Location JSON helpers
    # ------------------------------------------------------------------

    def _fabric(self, location):
        location_obj = self._get_location_or_raise(location)
        fields = copy.deepcopy(dict(location_obj.custom_fields or {}))
        fabric = fields.setdefault("aci_fabric_policies", {}) or {}
        fields["aci_fabric_policies"] = fabric
        return location_obj, fields, fabric

    @staticmethod
    def _named(fabric: dict, key: str, name: str) -> dict | None:
        return next((e for e in fabric.get(key) or [] if e.get("name") == name), None)

    def _require_named(self, fabric: dict, key: str, name: str, label: str, location_obj) -> dict:
        entry = self._named(fabric, key, name)
        if entry is None:
            known = ", ".join(sorted(e.get("name", "") for e in fabric.get(key) or [])) or "none"
            raise NautobotError(f"{label} '{name}' not found on Location '{location_obj.name}' (known: {known})")
        return entry

    def _add_named(self, location, key: str, entry: dict, label: str) -> dict:
        location_obj, fields, fabric = self._fabric(location)
        if self._named(fabric, key, entry["name"]) is not None:
            raise NautobotError(
                f"{label} '{entry['name']}' already exists on Location '{location_obj.name}' -- "
                f"use the update tool to change it"
            )
        fabric[key] = list(fabric.get(key) or []) + [entry]
        location_obj.update({"custom_fields": fields})
        return {"location": location_obj.name, key[:-1]: entry, "deploy": _DEPLOY_LOCATION}

    def _update_named(self, location, key: str, name: str, label: str, changes: dict, validate=None) -> dict:
        location_obj, fields, fabric = self._fabric(location)
        entry = self._require_named(fabric, key, name, label, location_obj)
        applied = {k: v for k, v in changes.items() if v is not None}
        candidate = {**entry, **applied}
        if validate:
            validate(fabric, candidate, entry)
        entry.update(applied)
        location_obj.update({"custom_fields": fields})
        return {"location": location_obj.name, key[:-1]: entry, "changed": applied, "deploy": _DEPLOY_LOCATION}

    def _fabric_node_ids(self) -> dict[int, str]:
        """Node ID -> device name for every switch in the DCIM roster."""
        roster = {}
        for device in self.api.dcim.devices.all():
            node_id = (device.custom_fields or {}).get("aci_node_id")
            if node_id is not None:
                roster[int(node_id)] = device.name
        return roster

    # ------------------------------------------------------------------
    # LACP policy
    # ------------------------------------------------------------------

    def create_lacp_policy(self, location, name, mode, min_links=None, max_links=None, controls=None) -> dict:
        entry = {"name": name, "mode": mode}
        for k, v in (("min_links", min_links), ("max_links", max_links), ("controls", controls)):
            if v is not None:
                entry[k] = v
        with _nautobot_errors(f"LACP policy '{name}'"):
            return self._add_named(location, "lacp_policies", entry, "LACP policy")

    def update_lacp_policy(self, location, name, **changes) -> dict:
        def _check(_fabric, candidate, _old):
            if candidate.get("min_links") and candidate.get("max_links") and candidate["min_links"] > candidate["max_links"]:
                raise NautobotError("min_links cannot exceed max_links")
        with _nautobot_errors(f"LACP policy '{name}'"):
            return self._update_named(location, "lacp_policies", name, "LACP policy", changes, _check)

    # ------------------------------------------------------------------
    # vPC domain (explicit VPC protection group)
    # ------------------------------------------------------------------

    def _check_vpc_domain(self, fabric: dict, candidate: dict, old: dict | None) -> None:
        """ACI rules a vPC pair must satisfy, checked before the write rather
        than left for the APIC to fault on."""
        pair = {int(candidate["node1"]), int(candidate["node2"])}
        if len(pair) != 2:
            raise NautobotError("A vPC domain needs two different leaf switches")
        roster = self._fabric_node_ids()
        if roster:
            missing = sorted(n for n in pair if n not in roster)
            if missing:
                known = ", ".join(f"{n} ({d})" for n, d in sorted(roster.items()))
                raise NautobotError(
                    f"Node(s) {missing} are not in the Nautobot fabric inventory (known: {known}). "
                    "Register them with create_fabric_device first."
                )
        for other in fabric.get("vpc_domains") or []:
            if old is not None and other.get("name") == old.get("name"):
                continue
            if int(other.get("domain_id", -1)) == int(candidate["domain_id"]):
                raise NautobotError(f"vPC domain ID {candidate['domain_id']} is already used by '{other.get('name')}'")
            shared = pair & {int(other.get("node1", -1)), int(other.get("node2", -1))}
            if shared:
                raise NautobotError(
                    f"Node(s) {sorted(shared)} already belong to vPC domain '{other.get('name')}' -- "
                    "an ACI leaf can be in only one vPC pair"
                )

    def create_vpc_domain(self, location, name, domain_id, node1, node2) -> dict:
        entry = {"name": name, "domain_id": domain_id, "node1": node1, "node2": node2}
        with _nautobot_errors(f"vPC domain '{name}'"):
            _, _, fabric = self._fabric(location)
            self._check_vpc_domain(fabric, entry, None)
            return self._add_named(location, "vpc_domains", entry, "vPC domain")

    def update_vpc_domain(self, location, name, domain_id=None, node1=None, node2=None) -> dict:
        def _check(fabric, candidate, old):
            self._check_vpc_domain(fabric, candidate, old)
            if {candidate["node1"], candidate["node2"]} != {old["node1"], old["node2"]}:
                # Moving the pair orphans every vPC binding built on the old one.
                found = refs.fabric_references("vpc_domain", name, {"aci_fabric_policies": fabric},
                                               self._all_tenants_snapshot())
                if found:
                    raise NautobotError(
                        f"Refusing to change the switches of vPC domain '{name}': {'; '.join(found)}. "
                        "Unbind those static paths first."
                    )
        with _nautobot_errors(f"vPC domain '{name}'"):
            return self._update_named(location, "vpc_domains", name, "vPC domain",
                                      {"domain_id": domain_id, "node1": node1, "node2": node2}, _check)

    # ------------------------------------------------------------------
    # PC / vPC interface policy group
    # ------------------------------------------------------------------

    def _check_bundle_group(self, fabric: dict, candidate: dict) -> None:
        if candidate.get("aep") and self._named(fabric, "aeps", candidate["aep"]) is None:
            raise NautobotError(f"AEP '{candidate['aep']}' does not exist -- create it with create_aep first")
        if candidate.get("lacp_policy") and self._named(fabric, "lacp_policies", candidate["lacp_policy"]) is None:
            raise NautobotError(
                f"LACP policy '{candidate['lacp_policy']}' does not exist -- create it with create_lacp_policy first"
            )

    def create_pc_vpc_policy_group(self, location, name, bundle_type, aep=None, lacp_policy=None, description="") -> dict:
        entry = {"name": name, "bundle_type": bundle_type}
        for k, v in (("aep", aep), ("lacp_policy", lacp_policy), ("description", description)):
            if v:
                entry[k] = v
        with _nautobot_errors(f"PC/vPC policy group '{name}'"):
            location_obj, _, fabric = self._fabric(location)
            if self._named(fabric, "leaf_interface_policy_groups", name) is not None:
                raise NautobotError(
                    f"'{name}' is already an access-port policy group on Location '{location_obj.name}'. "
                    "Interface selectors refer to policy groups by name, so the two must not share one."
                )
            self._check_bundle_group(fabric, entry)
            result = self._add_named(location, "pc_vpc_policy_groups", entry, "PC/vPC policy group")
        if not lacp_policy:
            result["warning"] = (
                "No LACP policy: APIC uses its default, which is mode 'off' (a static channel). "
                "Set lacp_policy for an LACP active/passive bundle."
            )
        return result

    def update_pc_vpc_policy_group(self, location, name, aep=None, lacp_policy=None, description=None) -> dict:
        with _nautobot_errors(f"PC/vPC policy group '{name}'"):
            return self._update_named(
                location, "pc_vpc_policy_groups", name, "PC/vPC policy group",
                {"aep": aep, "lacp_policy": lacp_policy, "description": description},
                lambda fabric, candidate, _old: self._check_bundle_group(fabric, candidate),
            )

    # ------------------------------------------------------------------
    # In-band management EPG (in tenant mgmt)
    # ------------------------------------------------------------------

    def create_inband_mgmt_epg(self, location, name, encap_vlan, bridge_domain="inb") -> dict:
        entry = {"name": name, "encap_vlan": encap_vlan, "bridge_domain": bridge_domain}
        with _nautobot_errors(f"in-band management EPG '{name}'"):
            return self._add_named(location, "inband_mgmt_epgs", entry, "In-band management EPG")

    def update_inband_mgmt_epg(self, location, name, encap_vlan=None, bridge_domain=None) -> dict:
        with _nautobot_errors(f"in-band management EPG '{name}'"):
            return self._update_named(location, "inband_mgmt_epgs", name, "In-band management EPG",
                                      {"encap_vlan": encap_vlan, "bridge_domain": bridge_domain})

    # ------------------------------------------------------------------
    # Node management addresses -- native IP Addresses
    # ------------------------------------------------------------------

    def _resolve_fabric_device(self, node: str | int):
        """A switch by device name or by ACI node ID."""
        device = None
        if isinstance(node, int) or str(node).isdigit():
            found = list(self.api.dcim.devices.filter(cf_aci_node_id=int(node)))
            device = found[0] if found else None
        if device is None:
            device = self.api.dcim.devices.get(name=str(node))
        if device is None or (device.custom_fields or {}).get("aci_node_id") is None:
            roster = ", ".join(f"{n} ({d})" for n, d in sorted(self._fabric_node_ids().items())) or "none"
            raise NautobotError(f"No fabric switch '{node}' in Nautobot (known nodes: {roster})")
        return device

    def _mgmt_ips(self, device) -> list:
        return [ip for ip in self.api.ipam.ip_addresses.filter(device_id=device.id)
                if (ip.custom_fields or {}).get("aci_mgmt_type")]

    def _mgmt_ip_of_type(self, device, mgmt_type: str):
        return next((ip for ip in self._mgmt_ips(device) if ip.custom_fields.get("aci_mgmt_type") == mgmt_type), None)

    def _get_or_create_mgmt_interface(self, device, mgmt_type: str):
        name = MGMT_INTERFACE[mgmt_type]
        iface = self.api.dcim.interfaces.get(device_id=device.id, name=name)
        if iface is None:
            iface = self.api.dcim.interfaces.create(
                device=device.id, name=name, status=self._get_status("dcim.interface").id,
                type="1000base-t" if mgmt_type == "out_of_band" else "virtual",
                mgmt_only=mgmt_type == "out_of_band",
                description="ACI node management (created by the MCP Server)",
            )
            return iface, True
        return iface, False

    def _check_inband_epg(self, location, mgmt_type: str, epg: str | None) -> None:
        if mgmt_type != "in_band":
            return
        _, _, fabric = self._fabric(location)
        if self._named(fabric, "inband_mgmt_epgs", epg) is None:
            known = ", ".join(sorted(e.get("name", "") for e in fabric.get("inband_mgmt_epgs") or [])) or "none"
            raise NautobotError(
                f"In-band management EPG '{epg}' is not declared (known: {known}) -- create it with "
                "create_inband_mgmt_epg first"
            )

    def create_node_mgmt_address(self, node, mgmt_type, address, gateway, epg=None, location=None) -> dict:
        epg = "default" if mgmt_type == "out_of_band" else epg
        with _nautobot_errors(f"management address {address}"):
            device = self._resolve_fabric_device(node)
            if self._mgmt_ip_of_type(device, mgmt_type) is not None:
                raise NautobotError(
                    f"Node '{device.name}' already has an {mgmt_type} management address -- "
                    "use update_node_mgmt_address to change it"
                )
            self._check_inband_epg(location, mgmt_type, epg)
            iface, created_iface = self._get_or_create_mgmt_interface(device, mgmt_type)
            fields = {"aci_mgmt_type": mgmt_type, "aci_mgmt_gateway": gateway, "aci_mgmt_epg": epg}
            ip, created_prefix = self._create_ip_with_parent(address, fields)
            try:
                self.api.ipam.ip_address_to_interface.create(ip_address=ip.id, interface=iface.id)
            except Exception:
                ip.delete()  # an unassigned management IP is intent nothing reads
                raise
        result = {
            "node": device.name, "node_id": device.custom_fields.get("aci_node_id"), "type": mgmt_type,
            "address": address, "gateway": gateway, "epg": epg, "interface": iface.name,
            "deploy": _DEPLOY_IP,
        }
        if created_iface:
            result["created_interface"] = iface.name
        if created_prefix:
            result["created_parent_prefix"] = created_prefix
        return result

    def _create_ip_with_parent(self, address: str, fields: dict):
        """Create the IP in the Global namespace; if Nautobot has no prefix
        that can hold it, create the address's own subnet and retry. Reported
        back so the caller knows IPAM gained a prefix.

        The namespace must be passed: over REST, Nautobot refuses an IP with
        neither namespace nor parent ("One of parent or namespace must be
        provided") rather than defaulting to Global. A missing parent is a
        different error, "No suitable parent Prefix for <ip> exists in
        Namespace Global" -- both confirmed against Nautobot 2026-10-12.
        """
        status = self._get_status("ipam.ipaddress").id
        namespace = self.api.ipam.namespaces.get(name="Global")
        if namespace is None:
            raise NautobotError("Nautobot has no 'Global' IPAM namespace to hold management addresses")
        kwargs = dict(address=address, status=status, namespace=namespace.id, custom_fields=fields)
        try:
            return self.api.ipam.ip_addresses.create(**kwargs), None
        except pynautobot.RequestError as exc:
            if "no suitable parent prefix" not in str(exc).lower():
                raise
        network = str(ipaddress.ip_interface(address).network)
        self.api.ipam.prefixes.create(
            prefix=network, namespace=namespace.id, status=self._get_status("ipam.prefix").id,
            description="ACI node management subnet (created by the MCP Server)",
        )
        return self.api.ipam.ip_addresses.create(**kwargs), network

    def update_node_mgmt_address(self, node, mgmt_type, address=None, gateway=None, epg=None, location=None) -> dict:
        with _nautobot_errors(f"{mgmt_type} management address of '{node}'"):
            device = self._resolve_fabric_device(node)
            ip = self._mgmt_ip_of_type(device, mgmt_type)
            if ip is None:
                raise NautobotError(f"Node '{device.name}' has no {mgmt_type} management address to update")
            if epg is not None:
                self._check_inband_epg(location, mgmt_type, epg)
            fields = copy.deepcopy(dict(ip.custom_fields or {}))
            changed: dict = {}
            if gateway is not None:
                fields["aci_mgmt_gateway"] = changed["gateway"] = gateway
            if epg is not None and mgmt_type == "in_band":
                fields["aci_mgmt_epg"] = changed["epg"] = epg
            payload: dict = {"custom_fields": fields}
            if address is not None and address != str(ip.address):
                # Nautobot does not allow changing an IP Address's host in
                # place, so a new address replaces the old one on the same
                # interface.
                iface, _ = self._get_or_create_mgmt_interface(device, mgmt_type)
                new_ip, created_prefix = self._create_ip_with_parent(address, fields)
                self.api.ipam.ip_address_to_interface.create(ip_address=new_ip.id, interface=iface.id)
                ip.delete()
                changed["address"] = address
                if created_prefix:
                    changed["created_parent_prefix"] = created_prefix
            else:
                ip.update(payload)
        return {"node": device.name, "type": mgmt_type, "changed": changed, "deploy": _DEPLOY_IP}

    def delete_node_mgmt_address(self, node, mgmt_type) -> dict:
        with _nautobot_errors(f"{mgmt_type} management address of '{node}'"):
            device = self._resolve_fabric_device(node)
            ip = self._mgmt_ip_of_type(device, mgmt_type)
            if ip is None:
                raise NautobotError(f"Node '{device.name}' has no {mgmt_type} management address")
            address = str(ip.address)
            ip.delete()
        return {
            "node": device.name, "type": mgmt_type, "deleted_address": address,
            "note": f"The {MGMT_INTERFACE[mgmt_type]} interface is kept; it is part of the switch's inventory.",
            "deploy": _DEPLOY_IP,
        }

    def node_mgmt_addresses(self) -> list[dict]:
        """Every ACI management address, for reads and reference checks."""
        result = []
        roster = {d.id: d for d in self.api.dcim.devices.all() if (d.custom_fields or {}).get("aci_node_id") is not None}
        for device in roster.values():
            for ip in self._mgmt_ips(device):
                cf = ip.custom_fields
                result.append({
                    "node": device.name, "node_id": device.custom_fields.get("aci_node_id"),
                    "type": cf.get("aci_mgmt_type"), "address": str(ip.address),
                    "gateway": cf.get("aci_mgmt_gateway"), "epg": cf.get("aci_mgmt_epg"),
                })
        return result

    # ------------------------------------------------------------------
    # EPG static paths: unbind (bind is create_static_path_binding)
    # ------------------------------------------------------------------

    def unbind_epg_static_path(self, tenant, application_profile, epg, path: dict) -> dict:
        with _nautobot_errors(f"static path on EPG '{epg}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            vlan = self._get_epg_vlan(tenant_obj, tenant, application_profile, epg)
            fields = copy.deepcopy(dict(vlan.custom_fields or {}))
            paths = list(fields.get("aci_static_paths") or [])
            target = refs.static_path_identity(path)
            kept = [p for p in paths if refs.static_path_identity(p) != target]
            if len(kept) == len(paths):
                have = "; ".join(refs.describe_static_path(p) for p in paths) or "none"
                raise NautobotError(f"EPG '{epg}' has no binding to {refs.describe_static_path(path)} (bindings: {have})")
            fields["aci_static_paths"] = kept
            vlan.update({"custom_fields": fields})
        return {"tenant": tenant, "epg": epg, "static_paths": kept,
                "deploy": DEPLOY_NOT_TRIGGERED.format(what="VLAN (EPG)")}
