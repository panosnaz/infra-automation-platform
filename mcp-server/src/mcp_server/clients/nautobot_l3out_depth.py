"""L3Out depth (2026-10-16): static routes, loopbacks, vPC SVIs, BFD, and the
BGP / OSPF / route-tag protocol policies.

Storage:
  * BFD interface policies join the other L3Out interface policies in the
    Tenant's `aci_interface_policies` (`bfd_interface_policies`).
  * BGP timers / best path / route summarization, OSPF timers and route tag
    policies live in the Tenant's `aci_protocol_policies`, one list per kind.
  * Static routes and loopbacks are per node inside the node profile, a vPC
    SVI is an interface of an interface profile, BGP policy references sit on
    the L3Out and summarization on an external EPG subnet -- all inside
    `aci_l3outs`. The VRF's references are in `aci_vrf_protocol_policies` on
    the Nautobot VRF (see LifecycleMixin.update_vrf).

An empty string clears a reference. That is offered only where clearing was
proven to reach the APIC (2026-10-16): Terraform removes the relation or puts
it back to tn-common's default.
"""
from __future__ import annotations

from mcp_server.clients.nautobot_lifecycle import DEPLOY_VIA_TENANT, _cf, _nautobot_errors, _set_or_drop
from mcp_server.errors import NautobotError

PROTOCOL_FIELD = "aci_protocol_policies"
# tool kind -> (list key in aci_protocol_policies, label)
PROTOCOL_KINDS = {
    "bgp_timers_policy": ("bgp_timers_policies", "BGP timers policy"),
    "bgp_best_path_policy": ("bgp_best_path_policies", "BGP best path policy"),
    "bgp_route_summarization_policy": ("bgp_route_summarization_policies", "BGP route summarization policy"),
    "ospf_timers_policy": ("ospf_timers_policies", "OSPF timers policy"),
    "route_tag_policy": ("route_tag_policies", "Route tag policy"),
}


def _known(items, key="name") -> str:
    return ", ".join(sorted(str(i.get(key)) for i in items)) or "none"


def _compact(values: dict) -> dict:
    return {k: v for k, v in values.items() if v is not None}


def check_bgp_timers(keepalive, hold) -> None:
    """APIC 6.2 answers HTTP 400 for both (probed 2026-10-16). 60/90 is
    accepted: there is no 3x rule. An unset timer is APIC's default
    (keepalive 60, hold 180), and the rule applies against it -- hold=30
    alone is rejected because the default keepalive is 60."""
    if keepalive is None and hold is None:
        return
    keepalive = 60 if keepalive is None else keepalive
    hold = 180 if hold is None else hold
    if hold == 0 and keepalive != 0:
        raise NautobotError("a hold interval of 0 needs a keepalive of 0 (APIC: 'If HoldIntvl is 0, KeepAlive must be 0')")
    if hold != 0 and hold <= keepalive:
        raise NautobotError(
            f"hold interval ({hold}) must be greater than the keepalive interval ({keepalive}) -- APIC rejects it"
        )


class L3OutDepthMixin:
    """Requires `_get_tenant_or_raise`, `_add_interface_policy` and `_fabric`
    on the host class (NautobotClient has them)."""

    # --- tenant policies ---------------------------------------------------------------

    def _add_protocol_policy(self, tenant: str, kind: str, entry: dict) -> dict:
        list_key, label = PROTOCOL_KINDS[kind]
        with _nautobot_errors(f"{label} '{entry['name']}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            fields = _cf(tenant_obj)
            data = fields.get(PROTOCOL_FIELD) if isinstance(fields.get(PROTOCOL_FIELD), dict) else {}
            entries = list(data.get(list_key) or [])
            if any(e.get("name") == entry["name"] for e in entries):
                raise NautobotError(f"{label} '{entry['name']}' already exists in tenant '{tenant}'")
            data[list_key] = entries + [entry]
            fields[PROTOCOL_FIELD] = data
            tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "policy": entry, "deploy": DEPLOY_VIA_TENANT}

    def create_bgp_timers_policy(self, tenant, name, keepalive_interval=None, hold_interval=None, stale_interval=None,
                                 graceful_restart_helper=None, max_as_limit=None, description=None) -> dict:
        check_bgp_timers(keepalive_interval, hold_interval)
        return self._add_protocol_policy(tenant, "bgp_timers_policy", _compact({
            "name": name, "keepalive_interval": keepalive_interval, "hold_interval": hold_interval,
            "stale_interval": stale_interval, "graceful_restart_helper": graceful_restart_helper,
            "max_as_limit": max_as_limit, "description": description}))

    def create_bgp_best_path_policy(self, tenant, name, as_path_multipath_relax=None, description=None) -> dict:
        return self._add_protocol_policy(tenant, "bgp_best_path_policy", _compact({
            "name": name, "as_path_multipath_relax": as_path_multipath_relax, "description": description}))

    def create_bgp_route_summarization_policy(self, tenant, name, as_set=None, description=None) -> dict:
        return self._add_protocol_policy(tenant, "bgp_route_summarization_policy", _compact({
            "name": name, "as_set": as_set, "description": description}))

    def create_ospf_timers_policy(self, tenant, name, reference_bandwidth=None, distance=None, max_ecmp=None,
                                  spf_initial_delay=None, spf_hold_interval=None, spf_max_interval=None,
                                  description=None) -> dict:
        return self._add_protocol_policy(tenant, "ospf_timers_policy", _compact({
            "name": name, "reference_bandwidth": reference_bandwidth, "distance": distance, "max_ecmp": max_ecmp,
            "spf_initial_delay": spf_initial_delay, "spf_hold_interval": spf_hold_interval,
            "spf_max_interval": spf_max_interval, "description": description}))

    def create_route_tag_policy(self, tenant, name, tag, description=None) -> dict:
        return self._add_protocol_policy(tenant, "route_tag_policy", _compact(
            {"name": name, "tag": tag, "description": description}))

    def create_bfd_interface_policy(self, tenant, name, admin_state=None, detect_multiplier=None, min_rx_interval=None,
                                    min_tx_interval=None, echo_admin_state=None, echo_rx_interval=None,
                                    description=None) -> dict:
        entry = _compact({"name": name, "admin_state": admin_state, "detect_multiplier": detect_multiplier,
                          "min_rx_interval": min_rx_interval, "min_tx_interval": min_tx_interval,
                          "echo_admin_state": echo_admin_state, "echo_rx_interval": echo_rx_interval,
                          "description": description})
        entries = self._add_interface_policy(tenant, "bfd_interface_policies", entry)
        return {"tenant": tenant, "policy": entry, "bfd_interface_policies": entries, "deploy": DEPLOY_VIA_TENANT}

    @staticmethod
    def require_protocol_policy(fields: dict, tenant: str, kind: str, name: str) -> None:
        list_key, label = PROTOCOL_KINDS[kind]
        entries = (fields.get(PROTOCOL_FIELD) or {}).get(list_key) or []
        if not any(e.get("name") == name for e in entries):
            raise NautobotError(f"{label} '{name}' not found in tenant '{tenant}' (known: {_known(entries)})")

    # --- L3Out navigation ------------------------------------------------------------------

    def _l3out_state(self, tenant: str, l3out: str):
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = _cf(tenant_obj)
        data = fields.get("aci_l3outs") if isinstance(fields.get("aci_l3outs"), dict) else {}
        fields["aci_l3outs"] = data
        l3outs = list(data.get("l3outs") or [])
        data["l3outs"] = l3outs
        out = next((o for o in l3outs if o.get("name") == l3out), None)
        if out is None:
            raise NautobotError(f"L3Out '{l3out}' not found in tenant '{tenant}' (known: {_known(l3outs)})")
        return tenant_obj, fields, out

    @staticmethod
    def _node_profile(out: dict, name: str) -> dict:
        profiles = list(out.get("node_profiles") or [])
        np_ = next((p for p in profiles if p.get("name") == name), None)
        if np_ is None:
            raise NautobotError(f"Node profile '{name}' not found in L3Out '{out.get('name')}' (known: {_known(profiles)})")
        return np_

    @staticmethod
    def _node(np_: dict, node_id: int) -> dict:
        nodes = list(np_.get("nodes") or [])
        node = next((n for n in nodes if int(n.get("node_id", -1)) == int(node_id)), None)
        if node is None:
            raise NautobotError(
                f"node {node_id} is not in node profile '{np_.get('name')}' (known: {_known(nodes, 'node_id')}) -- "
                "add it with create_l3out_node_profile first"
            )
        return node

    @staticmethod
    def _interface_profile(np_: dict, name: str) -> dict:
        profiles = list(np_.get("interface_profiles") or [])
        ip = next((p for p in profiles if p.get("name") == name), None)
        if ip is None:
            raise NautobotError(f"Interface profile '{name}' not found in node profile '{np_.get('name')}' (known: {_known(profiles)})")
        return ip

    def _save(self, tenant_obj, fields, tenant, result) -> dict:
        tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, **result, "deploy": DEPLOY_VIA_TENANT}

    # --- static routes / loopbacks -------------------------------------------------------------

    def create_l3out_static_route(self, tenant, l3out, node_profile, node_id, prefix, next_hops=None,
                                  preference=None, bfd=None, description=None) -> dict:
        with _nautobot_errors(f"static route {prefix}"):
            tenant_obj, fields, out = self._l3out_state(tenant, l3out)
            node = self._node(self._node_profile(out, node_profile), node_id)
            routes = list(node.get("static_routes") or [])
            if any(r.get("prefix") == prefix for r in routes):
                raise NautobotError(f"static route {prefix} already exists on node {node_id}")
            hops = [_compact(h) for h in (next_hops or [])]
            ips = [h.get("ip") for h in hops]
            if len(ips) != len(set(ips)):
                raise NautobotError(f"next hops of {prefix} repeat an address: {ips}")
            entry = _compact({"prefix": prefix, "preference": preference, "bfd": bfd, "description": description})
            if hops:
                entry["next_hops"] = hops
            node["static_routes"] = routes + [entry]
            return self._save(tenant_obj, fields, tenant, {"l3out": l3out, "node_id": node_id, "static_route": entry})

    def delete_l3out_static_route(self, tenant, l3out, node_profile, node_id, prefix) -> dict:
        with _nautobot_errors(f"static route {prefix}"):
            tenant_obj, fields, out = self._l3out_state(tenant, l3out)
            node = self._node(self._node_profile(out, node_profile), node_id)
            routes = list(node.get("static_routes") or [])
            kept = [r for r in routes if r.get("prefix") != prefix]
            if len(kept) == len(routes):
                raise NautobotError(f"no static route {prefix} on node {node_id} (known: {_known(routes, 'prefix')})")
            _set_or_drop(node, "static_routes", kept)
            return self._save(tenant_obj, fields, tenant, {"l3out": l3out, "node_id": node_id, "removed": prefix})

    def create_l3out_loopback(self, tenant, l3out, node_profile, node_id, ip) -> dict:
        with _nautobot_errors(f"loopback {ip}"):
            tenant_obj, fields, out = self._l3out_state(tenant, l3out)
            node = self._node(self._node_profile(out, node_profile), node_id)
            loopbacks = list(node.get("loopbacks") or [])
            if any(lb.get("ip") == ip for lb in loopbacks):
                raise NautobotError(f"loopback {ip} already exists on node {node_id}")
            node["loopbacks"] = loopbacks + [{"ip": ip}]
            return self._save(tenant_obj, fields, tenant, {"l3out": l3out, "node_id": node_id, "loopback": ip})

    def delete_l3out_loopback(self, tenant, l3out, node_profile, node_id, ip) -> dict:
        with _nautobot_errors(f"loopback {ip}"):
            tenant_obj, fields, out = self._l3out_state(tenant, l3out)
            node = self._node(self._node_profile(out, node_profile), node_id)
            loopbacks = list(node.get("loopbacks") or [])
            kept = [lb for lb in loopbacks if lb.get("ip") != ip]
            if len(kept) == len(loopbacks):
                raise NautobotError(f"no loopback {ip} on node {node_id} (known: {_known(loopbacks, 'ip')})")
            _set_or_drop(node, "loopbacks", kept)
            return self._save(tenant_obj, fields, tenant, {"l3out": l3out, "node_id": node_id, "removed": ip})

    # --- vPC SVI ----------------------------------------------------------------------------------

    @staticmethod
    def _is_vpc_svi(iface: dict, node_id, node_id2, policy_group) -> bool:
        return (iface.get("path_type") == "vpc" and iface.get("policy_group") == policy_group
                and {int(iface.get("node_id", -1)), int(iface.get("node_id2", -1))} == {int(node_id), int(node_id2)})

    def create_l3out_vpc_svi(self, tenant, l3out, node_profile, interface_profile, node_id, node_id2, policy_group,
                             vlan, side_a_ip, side_b_ip, pod_id=1, mtu=None, location=None) -> dict:
        with _nautobot_errors(f"vPC SVI on {node_id}-{node_id2}"):
            _, _, fabric = self._fabric(location)
            group = next((g for g in fabric.get("pc_vpc_policy_groups") or [] if g.get("name") == policy_group), None)
            if group is None:
                raise NautobotError(f"PC/vPC policy group '{policy_group}' not found (known: {_known(fabric.get('pc_vpc_policy_groups') or [])})")
            if group.get("bundle_type") != "vpc":
                raise NautobotError(f"'{policy_group}' is a {group.get('bundle_type')} policy group, not vpc")
            pair = {int(node_id), int(node_id2)}
            if not any({int(d.get("node1", -1)), int(d.get("node2", -1))} == pair for d in fabric.get("vpc_domains") or []):
                raise NautobotError(f"no vPC domain pairs nodes {node_id} and {node_id2} -- create_vpc_domain first")
            tenant_obj, fields, out = self._l3out_state(tenant, l3out)
            ip = self._interface_profile(self._node_profile(out, node_profile), interface_profile)
            interfaces = list(ip.get("interfaces") or [])
            if any(self._is_vpc_svi(i, node_id, node_id2, policy_group) for i in interfaces):
                raise NautobotError(
                    f"interface profile '{interface_profile}' already has a vPC SVI on nodes {node_id}-{node_id2} / "
                    f"'{policy_group}' -- APIC allows one per path per profile; use another interface profile"
                )
            entry = _compact({"path_type": "vpc", "node_id": node_id, "node_id2": node_id2, "pod_id": pod_id,
                              "policy_group": policy_group, "svi": True, "vlan": vlan,
                              "side_a_ip": side_a_ip, "side_b_ip": side_b_ip, "mtu": mtu})
            ip["interfaces"] = interfaces + [entry]
            return self._save(tenant_obj, fields, tenant, {"l3out": l3out, "interface": entry})

    def delete_l3out_vpc_svi(self, tenant, l3out, node_profile, interface_profile, node_id, node_id2, policy_group) -> dict:
        with _nautobot_errors(f"vPC SVI on {node_id}-{node_id2}"):
            tenant_obj, fields, out = self._l3out_state(tenant, l3out)
            ip = self._interface_profile(self._node_profile(out, node_profile), interface_profile)
            interfaces = list(ip.get("interfaces") or [])
            kept = [i for i in interfaces if not self._is_vpc_svi(i, node_id, node_id2, policy_group)]
            if len(kept) == len(interfaces):
                raise NautobotError(f"no vPC SVI on nodes {node_id}-{node_id2} / '{policy_group}' in '{interface_profile}'")
            if any(i.get("bgp_peers") for i in interfaces if self._is_vpc_svi(i, node_id, node_id2, policy_group)):
                raise NautobotError("Refusing: BGP peers are configured on this SVI -- they would be removed with it")
            ip["interfaces"] = kept
            return self._save(tenant_obj, fields, tenant, {"l3out": l3out, "removed": f"{node_id}-{node_id2}/{policy_group}"})

    # --- policy references ---------------------------------------------------------------------------

    def set_l3out_bgp_policies(self, tenant, l3out, bgp_timers_policy=None, bgp_best_path_policy=None) -> dict:
        with _nautobot_errors(f"BGP policies of L3Out '{l3out}'"):
            tenant_obj, fields, out = self._l3out_state(tenant, l3out)
            if out.get("protocol") != "bgp":
                raise NautobotError(f"L3Out '{l3out}' is not a BGP L3Out (protocol '{out.get('protocol')}') -- nothing would carry these")
            for kind, value in (("bgp_timers_policy", bgp_timers_policy), ("bgp_best_path_policy", bgp_best_path_policy)):
                if value is None:
                    continue
                if value == "":
                    out.pop(kind, None)
                else:
                    self.require_protocol_policy(fields, tenant, kind, value)
                    out[kind] = value
            return self._save(tenant_obj, fields, tenant, {
                "l3out": l3out, **{k: out.get(k) for k in ("bgp_timers_policy", "bgp_best_path_policy")}})

    def set_external_subnet_route_summarization(self, tenant, l3out, external_epg, ip, policy) -> dict:
        with _nautobot_errors(f"summarization of {ip}"):
            tenant_obj, fields, out = self._l3out_state(tenant, l3out)
            epgs = list(out.get("external_epgs") or [])
            epg = next((e for e in epgs if e.get("name") == external_epg), None)
            if epg is None:
                raise NautobotError(f"external EPG '{external_epg}' not found in L3Out '{l3out}' (known: {_known(epgs)})")
            subnets = list(epg.get("subnets") or [])
            subnet = next((s for s in subnets if s.get("ip") == ip), None)
            if subnet is None:
                raise NautobotError(f"subnet {ip} not found on external EPG '{external_epg}' (known: {_known(subnets, 'ip')})")
            if policy == "":
                subnet.pop("bgp_route_summarization_policy", None)
            else:
                self.require_protocol_policy(fields, tenant, "bgp_route_summarization_policy", policy)
                subnet["bgp_route_summarization_policy"] = policy
            return self._save(tenant_obj, fields, tenant, {"l3out": l3out, "external_epg": external_epg, "subnet": subnet})
