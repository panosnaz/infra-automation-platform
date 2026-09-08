"""Thin pynautobot wrapper -- the only place tools touch the Nautobot SDK
directly, so client construction/error-mapping stays in one place.
"""
from __future__ import annotations

import pynautobot

from mcp_server.errors import NautobotError


class NautobotClient:
    def __init__(self, url: str, token: str) -> None:
        self._url = url
        self._token = token
        self._api: pynautobot.api | None = None

    @property
    def api(self) -> pynautobot.api:
        if self._api is None:
            self._api = pynautobot.api(self._url, token=self._token)
        return self._api

    def create_tenant(self, name: str, description: str = "") -> dict:
        """Create a Tenant object -- the same shape a human editing the
        Nautobot UI would produce (ADR-018: no intermediate intent schema).
        """
        try:
            tenant = self.api.tenancy.tenants.create(
                name=name,
                description=description,
            )
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected tenant '{name}': {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - network/auth failures, mapped uniformly
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return dict(tenant)

    def _get_tenant_or_raise(self, name: str):
        tenant = self.api.tenancy.tenants.get(name=name)
        if tenant is None:
            raise NautobotError(f"Tenant '{name}' not found in Nautobot")
        return tenant

    def _get_status(self, content_type: str):
        """Look up the 'Active' Status object for a given content type --
        every object-creation tool below needs one and Nautobot has no
        universal default."""
        status = self.api.extras.statuses.get(name="Active", content_types=content_type)
        if status is None:
            raise NautobotError(f"No 'Active' Status found for content type '{content_type}'")
        return status

    def _get_or_create_namespace(self, tenant_name: str):
        """Namespace-per-tenant convention already established by
        nautobot_ssot's ACI adapter (`load_vrfs()`: VRF namespace = the
        owning Tenant's own name, except `inb`/`oob` which use `Global`) --
        reuse the exact same convention here so VRFs/Prefixes created via
        MCP tools land in the same namespace nautobot_ssot itself would use.
        """
        namespace = self.api.ipam.namespaces.get(name=tenant_name)
        if namespace is None:
            namespace = self.api.ipam.namespaces.create(name=tenant_name)
        return namespace

    def create_vrf(self, tenant: str, name: str, description: str = "") -> dict:
        """Create a VRF (ADR-020 Phase A item 1 coverage) -- a first-class
        Nautobot ipam.vrf object, tenant-scoped. Namespace defaults to
        Nautobot's own "Global" if left unset, but the ACI SSoT convention
        (and this tool, to stay consistent) uses a per-tenant namespace --
        see `_get_or_create_namespace()`."""
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            namespace_obj = self._get_or_create_namespace(tenant_obj.name)
            vrf = self.api.ipam.vrfs.create(
                name=name,
                tenant=tenant_obj.id,
                namespace=namespace_obj.id,
                description=description,
            )
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected VRF '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return dict(vrf)

    def create_bridge_domain(self, tenant: str, vrf: str, name: str, gateway_ip: str, description: str = "") -> dict:
        """Create a Bridge Domain (ADR-020 Phase A item 1 coverage). BD
        identity is derived from a Prefix's description
        (`"ACI Bridge Domain: <bd>:<tenant>"`, see transformer.py's module
        docstring) -- Nautobot has no separate first-class BD object, so
        this creates that Prefix plus its VRF assignment
        (ipam.vrfprefixassignment, a separate M2M model -- Prefix's own API
        has no direct `vrfs` write field).
        """
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            vrf_obj = self.api.ipam.vrfs.get(name=vrf, tenant_id=tenant_obj.id)
            if vrf_obj is None:
                raise NautobotError(f"VRF '{vrf}' not found in tenant '{tenant}'")
            # Must match the VRF's own namespace (Nautobot rejects a Prefix
            # whose namespace differs from its assigned VRF's namespace) --
            # reuse the same per-tenant convention create_vrf() uses.
            namespace_obj = self._get_or_create_namespace(tenant_obj.name)
            status_obj = self._get_status("ipam.prefix")
            # transformer.py's _BD_DESCRIPTION_RE expects the tenant name
            # WITHOUT the "ACI:" namespace prefix nautobot-ssot adds to the
            # Tenant object's own .name (matches every BD nautobot-ssot
            # itself has ever written, e.g. "...:new-app-bd:new-app-tenant").
            bare_tenant_name = tenant_obj.name[4:] if tenant_obj.name.startswith("ACI:") else tenant_obj.name
            bd_description = f"ACI Bridge Domain: {name}:{bare_tenant_name}"
            if description:
                bd_description = f"{bd_description} -- {description}"
            prefix = self.api.ipam.prefixes.create(
                prefix=gateway_ip,
                tenant=tenant_obj.id,
                namespace=namespace_obj.id,
                status=status_obj.id,
                description=bd_description,
            )
            self.api.ipam.vrf_prefix_assignments.create(vrf=vrf_obj.id, prefix=prefix.id)
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected bridge domain '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return dict(prefix)

    # ------------------------------------------------------------------
    # VXLAN EVPN (ADR-021) -- separate methods, not a shared code path with
    # the ACI methods above, since the underlying Nautobot object shapes
    # differ: EVPN's Bridge Domain IS a VLAN directly (not a Prefix-
    # description encoding), and VNIs are plain-integer Custom Fields set
    # at creation time, not derived after the fact.
    # ------------------------------------------------------------------

    def create_evpn_vrf(self, tenant: str, name: str, l3_vni: int, description: str = "") -> dict:
        """Create a VRF for the EVPN domain, with its L3 VNI set directly
        via the `evpn_l3_vni` Custom Field (ADR-021 §2)."""
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            namespace_obj = self._get_or_create_namespace(tenant_obj.name)
            vrf = self.api.ipam.vrfs.create(
                name=name,
                tenant=tenant_obj.id,
                namespace=namespace_obj.id,
                description=description,
                custom_fields={"evpn_l3_vni": l3_vni},
            )
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected VRF '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return dict(vrf)

    def create_evpn_bridge_domain(
        self, tenant: str, vrf: str, name: str, vlan_id: int, l2_vni: int, description: str = ""
    ) -> dict:
        """Create a Bridge Domain for the EVPN domain -- a Nautobot VLAN
        object directly (ADR-021 §2), with its L2 VNI and VRF association
        set via Custom Fields (`evpn_l2_vni`, `evpn_vrf`)."""
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            vrf_obj = self.api.ipam.vrfs.get(name=vrf, tenant_id=tenant_obj.id)
            if vrf_obj is None:
                raise NautobotError(f"VRF '{vrf}' not found in tenant '{tenant}'")
            status_obj = self._get_status("ipam.vlan")
            vlan = self.api.ipam.vlans.create(
                name=name,
                vid=vlan_id,
                tenant=tenant_obj.id,
                status=status_obj.id,
                description=description,
                custom_fields={"evpn_l2_vni": l2_vni, "evpn_vrf": vrf},
            )
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected bridge domain '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return dict(vlan)

    def create_epg(
        self,
        tenant: str,
        application_profile: str,
        bridge_domain: str,
        name: str,
        vid: int,
        description: str = "",
    ) -> dict:
        """Create an EPG (ADR-020 Phase A item 2 coverage) -- modeled as a
        Nautobot VLAN with `aci_application_profile`/`aci_epg_bridge_domain`
        Custom Fields set (the opt-in pattern `_build_application_profiles()`
        reads)."""
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            status_obj = self._get_status("ipam.vlan")
            vlan = self.api.ipam.vlans.create(
                name=name,
                vid=vid,
                tenant=tenant_obj.id,
                status=status_obj.id,
                description=description,
                custom_fields={
                    "aci_application_profile": application_profile,
                    "aci_epg_bridge_domain": bridge_domain,
                },
            )
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected EPG '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return dict(vlan)

    def bind_epg_domain(
        self,
        tenant: str,
        application_profile: str,
        epg: str,
        domain: str,
        domain_type: str,
        resolution_immediacy: str | None = None,
        deployment_immediacy: str | None = None,
    ) -> dict:
        """Bind an existing EPG to a Physical or VMM Domain (ADR-020 Phase D
        follow-on coverage) -- appends/replaces one entry in the `domains`
        list of the EPG's own `aci_epg_domains` Custom Field (the EPG is
        modeled as a Nautobot VLAN, same as `create_epg`). Merge-not-replace,
        same convention as `create_aep`'s domains list: re-binding the same
        (domain, domain_type) pair updates immediacy settings in place
        instead of appending a duplicate."""
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            vlan = self.api.ipam.vlans.get(
                name=epg, tenant_id=tenant_obj.id, cf_aci_application_profile=application_profile
            )
            if vlan is None:
                raise NautobotError(f"EPG '{epg}' not found in tenant '{tenant}' / application profile '{application_profile}'")

            existing = dict(vlan.custom_fields or {}).get("aci_epg_domains") or {}
            domains = list(existing.get("domains") or [])

            entry = {"name": domain, "domain_type": domain_type}
            if resolution_immediacy:
                entry["resolution_immediacy"] = resolution_immediacy
            if deployment_immediacy:
                entry["deployment_immediacy"] = deployment_immediacy

            domains = [d for d in domains if not (d.get("name") == domain and d.get("domain_type") == domain_type)]
            domains.append(entry)

            vlan.update({"custom_fields": {"aci_epg_domains": {**existing, "domains": domains}}})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected domain binding for EPG '{epg}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "application_profile": application_profile, "epg": epg, "domains": domains}

    def create_contract(
        self,
        tenant: str,
        name: str,
        filter_name: str,
        scope: str = "context",
        ether_type: str = "ip",
        ip_protocol: str = "unspecified",
        description: str = "",
    ) -> dict:
        """Create a Contract (ADR-020 Phase A item 3 coverage) -- appends
        one Contract (with a single Subject binding `filter_name`) into the
        Tenant's `aci_contracts` JSON Custom Field. Creating the same Filter
        name twice is a no-op (reused, not duplicated); creating the same
        Contract name twice appends a second entry -- callers should check
        `get_tenant_status` first if idempotency across repeated calls
        matters.
        """
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            existing = dict(tenant_obj.custom_fields or {}).get("aci_contracts") or {}
            filters = list(existing.get("filters") or [])
            contracts = list(existing.get("contracts") or [])

            if not any(f.get("name") == filter_name for f in filters):
                filters.append(
                    {
                        "name": filter_name,
                        "entries": [{"name": "default", "ether_type": ether_type, "ip_protocol": ip_protocol}],
                    }
                )

            contract_entry: dict = {
                "name": name,
                "scope": scope,
                "subjects": [{"name": f"{name}-subj", "filters": [filter_name]}],
            }
            if description:
                contract_entry["description"] = description
            contracts.append(contract_entry)

            tenant_obj.update({"custom_fields": {"aci_contracts": {"filters": filters, "contracts": contracts}}})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected contract '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "contract": name, "filter": filter_name, "filters": filters, "contracts": contracts}

    def create_l3out(
        self,
        tenant: str,
        vrf: str,
        name: str,
        external_epg_name: str,
        subnet: str = "0.0.0.0/0",
        description: str = "",
    ) -> dict:
        """Create an L3Out (ADR-020 Phase A item 4 coverage, logical-only
        scope) -- appends one L3Out (with one External EPG + subnet) into
        the Tenant's `aci_l3outs` JSON Custom Field. Deliberately no
        physical interface/OSPF/BGP attachment -- see ADR-020's Phase A
        item 4 writeup for why (this simulator has zero real leaf/spine
        interface data available, confirmed via direct APIC API query)."""
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            existing = dict(tenant_obj.custom_fields or {}).get("aci_l3outs") or {}
            l3outs = list(existing.get("l3outs") or [])

            l3out_entry: dict = {
                "name": name,
                "vrf": vrf,
                "external_epgs": [
                    {"name": external_epg_name, "subnets": [{"ip": subnet, "scope": ["import-security"]}]}
                ],
            }
            if description:
                l3out_entry["description"] = description
            l3outs.append(l3out_entry)

            tenant_obj.update({"custom_fields": {"aci_l3outs": {"l3outs": l3outs}}})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected L3Out '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "l3out": name, "external_epg": external_epg_name, "l3outs": l3outs}

    # Ported from copilot/aci-platform-comparison (2026-09-08) -- physical/
    # protocol L3Out (node/interface profiles, BGP/OSPF peers) and VRF
    # route-leak intent. See Platform-Status-and-Pending-Items.md: the
    # L3Out/BGP/OSPF portion is plan-validated only on this simulator (no
    # real `pathep-[...]` interface data).
    def _update_l3out_entry(self, tenant: str, l3out: str, update: dict) -> dict:
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = dict(tenant_obj.custom_fields or {})
        data = dict(fields.get("aci_l3outs") or {})
        entries = list(data.get("l3outs") or [])
        target = next((item for item in entries if item.get("name") == l3out), None)
        if target is None:
            raise NautobotError(f"L3Out '{l3out}' not found in tenant '{tenant}'")
        target.update(update)
        fields["aci_l3outs"] = {"l3outs": entries}
        tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "l3out": l3out, **update}

    def create_protocol_l3out(self, tenant: str, name: str, vrf: str, domain: str, protocol: str, description: str = "", external_epgs: list[dict] | None = None) -> dict:
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = dict(tenant_obj.custom_fields or {})
        data = dict(fields.get("aci_l3outs") or {})
        entries = list(data.get("l3outs") or [])
        if any(item.get("name") == name for item in entries):
            raise NautobotError(f"L3Out '{name}' already exists in tenant '{tenant}'")
        entry = {"name": name, "vrf": vrf, "domain": domain, "protocol": protocol, "external_epgs": list(external_epgs or [])}
        if description: entry["description"] = description
        entries.append(entry)
        fields["aci_l3outs"] = {"l3outs": entries}
        tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "l3out": name, "protocol": protocol}

    def create_l3out_node_profile(self, tenant: str, l3out: str, name: str, nodes: list[dict]) -> dict:
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = dict(tenant_obj.custom_fields or {})
        entries = list((fields.get("aci_l3outs") or {}).get("l3outs") or [])
        target = next(item for item in entries if item.get("name") == l3out)
        profiles = list(target.get("node_profiles") or [])
        profile = next((item for item in profiles if item.get("name") == name), None)
        if profile is None:
            profiles.append({"name": name, "nodes": nodes})
        else:
            profile["nodes"] = nodes
        target["node_profiles"] = profiles
        fields["aci_l3outs"] = {"l3outs": entries}
        tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "l3out": l3out, "node_profile": name}

    def create_l3out_interface_profile(self, tenant: str, l3out: str, node_profile: str, name: str, interfaces: list[dict]) -> dict:
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = dict(tenant_obj.custom_fields or {})
        entries = list((fields.get("aci_l3outs") or {}).get("l3outs") or [])
        target = next(item for item in entries if item.get("name") == l3out)
        profile = next(item for item in target.get("node_profiles", []) if item.get("name") == node_profile)
        interface_profiles = list(profile.get("interface_profiles") or [])
        existing = next((item for item in interface_profiles if item.get("name") == name), None)
        if existing is None:
            interface_profiles.append({"name": name, "interfaces": interfaces})
        else:
            existing["interfaces"] = interfaces
        profile["interface_profiles"] = interface_profiles
        fields["aci_l3outs"] = {"l3outs": entries}
        tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "l3out": l3out, "interface_profile": name}

    def create_l3out_interface(self, tenant: str, l3out: str, node_profile: str, interface_profile: str, **interface) -> dict:
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = dict(tenant_obj.custom_fields or {})
        entries = list((fields.get("aci_l3outs") or {}).get("l3outs") or [])
        target = next(item for item in entries if item.get("name") == l3out)
        profile = next(item for item in target.get("node_profiles", []) if item.get("name") == node_profile)
        interface_profile_obj = next(item for item in profile.get("interface_profiles", []) if item.get("name") == interface_profile)
        interfaces = list(interface_profile_obj.get("interfaces") or [])
        identity = (interface.get("node_id"), interface.get("module"), interface.get("port"))
        interfaces = [item for item in interfaces if (item.get("node_id"), item.get("module"), item.get("port")) != identity]
        interfaces.append(interface)
        interface_profile_obj["interfaces"] = interfaces
        fields["aci_l3outs"] = {"l3outs": entries}
        tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "l3out": l3out, "interface": interface}

    def create_bgp_peer(self, tenant: str, l3out: str, node_profile: str, interface_profile: str, interface_key: str, **peer) -> dict:
        peer["interface_key"] = interface_key
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = dict(tenant_obj.custom_fields or {})
        entries = list((fields.get("aci_l3outs") or {}).get("l3outs") or [])
        target = next(item for item in entries if item.get("name") == l3out)
        profile = next(item for item in target.get("node_profiles", []) if item.get("name") == node_profile)
        interface_profile_obj = next(item for item in profile.get("interface_profiles", []) if item.get("name") == interface_profile)
        interface_obj = next(item for item in interface_profile_obj.get("interfaces", []) if item.get("interface_key") == interface_key)
        peers = list(interface_obj.get("bgp_peers") or [])
        peers.append(peer)
        interface_obj["bgp_peers"] = peers
        fields["aci_l3outs"] = {"l3outs": entries}
        tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "l3out": l3out, "bgp_peer": peer}

    def create_ospf_interface(self, tenant: str, l3out: str, interface_key: str, **ospf) -> dict:
        ospf["interface_key"] = interface_key
        return self._update_l3out_entry(tenant, l3out, {"ospf_interfaces": [ospf]})

    def create_ospf_interface_policy(self, tenant: str, name: str, network_type: str = "broadcast", hello_interval: int = 10, dead_interval: int = 40, passive: bool = False, authentication_type: str | None = None, authentication_secret_ref: str | None = None, authentication_key_id: int | None = None, cost: int | None = None, priority: int | None = None, description: str = "") -> dict:
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = dict(tenant_obj.custom_fields or {})
        data = dict(fields.get("aci_ospf_interface_policies") or {})
        policies = list(data.get("policies") or [])
        if any(p.get("name") == name for p in policies):
            raise NautobotError(f"OSPF interface policy '{name}' already exists in tenant '{tenant}'")
        entry = {"name": name, "network_type": network_type, "hello_interval": hello_interval, "dead_interval": dead_interval, "passive": passive}
        if authentication_type: entry["authentication_type"] = authentication_type
        if authentication_secret_ref: entry["authentication_secret_ref"] = authentication_secret_ref
        if authentication_key_id is not None: entry["authentication_key_id"] = authentication_key_id
        if cost is not None: entry["cost"] = cost
        if priority is not None: entry["priority"] = priority
        if description: entry["description"] = description
        policies.append(entry)
        fields["aci_ospf_interface_policies"] = {"policies": policies}
        tenant_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "ospf_interface_policy": entry}

    def create_vrf_route_leak(
        self,
        tenant: str,
        name: str,
        source_vrf: str,
        destination_vrf: str,
        subnet: str,
        allow_l3out_advertisement: bool = False,
        description: str = "",
    ) -> dict:
        """Create a shared-services/L3Out route-leak intent entry on the
        Tenant's aci_vrf_route_leaks JSON Custom Field."""
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            source_obj = self.api.ipam.vrfs.get(name=source_vrf, tenant_id=tenant_obj.id)
            destination_obj = self.api.ipam.vrfs.get(name=destination_vrf, tenant_id=tenant_obj.id)
            if source_obj is None:
                raise NautobotError(f"Source VRF '{source_vrf}' not found in tenant '{tenant}'")
            if destination_obj is None:
                raise NautobotError(f"Destination VRF '{destination_vrf}' not found in tenant '{tenant}'")

            custom_fields = dict(tenant_obj.custom_fields or {})
            existing = dict(custom_fields.get("aci_vrf_route_leaks") or {})
            route_leaks = list(existing.get("route_leaks") or [])
            if any(item.get("name") == name for item in route_leaks):
                raise NautobotError(f"VRF route leak '{name}' already exists in tenant '{tenant}'")

            entry: dict = {
                "name": name,
                "source_vrf": source_vrf,
                "destination_vrf": destination_vrf,
                "subnet": subnet,
                "allow_l3out_advertisement": allow_l3out_advertisement,
            }
            if description:
                entry["description"] = description
            route_leaks.append(entry)
            custom_fields["aci_vrf_route_leaks"] = {"route_leaks": route_leaks}
            tenant_obj.update({"custom_fields": custom_fields})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected VRF route leak '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "route_leak": name, "route_leaks": route_leaks}

    # ------------------------------------------------------------------
    # ACI Access/Fabric Policies (ADR-020 Phase B) -- fabric-wide, not
    # Tenant-scoped, so all four live in one JSON Custom Field
    # (`aci_fabric_policies`) on the Location representing the ACI
    # fabric/site, per transformer.py's `_build_fabric_and_access_
    # policies()`. Same read-merge-write pattern as create_contract/
    # create_l3out above, just keyed by Location instead of Tenant.
    # ------------------------------------------------------------------

    def _get_location_or_raise(self, name: str):
        location = self.api.dcim.locations.get(name=name)
        if location is None:
            raise NautobotError(f"Location '{name}' not found in Nautobot")
        return location

    def create_vlan_pool(
        self,
        location: str,
        name: str,
        alloc_mode: str,
        range_from: int,
        range_to: int,
        range_alloc_mode: str | None = None,
        role: str = "external",
        description: str = "",
    ) -> dict:
        """Create/extend a VLAN Pool (ADR-020 Phase B coverage). Appends one
        encap range into the named pool; creates the pool first if it
        doesn't already exist for this Location."""
        try:
            location_obj = self._get_location_or_raise(location)
            existing = dict(location_obj.custom_fields or {}).get("aci_fabric_policies") or {}
            vlan_pools = list(existing.get("vlan_pools") or [])

            pool = next((p for p in vlan_pools if p.get("name") == name), None)
            new_range: dict = {"from": range_from, "to": range_to}
            if range_alloc_mode:
                new_range["alloc_mode"] = range_alloc_mode
            if role:
                new_range["role"] = role

            if pool is None:
                pool = {"name": name, "alloc_mode": alloc_mode, "ranges": [new_range]}
                if description:
                    pool["description"] = description
                vlan_pools.append(pool)
            else:
                pool.setdefault("ranges", []).append(new_range)

            location_obj.update({"custom_fields": {"aci_fabric_policies": {**existing, "vlan_pools": vlan_pools}}})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected VLAN Pool '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"location": location, "vlan_pool": name, "vlan_pools": vlan_pools}

    def create_physical_domain(self, location: str, name: str, vlan_pool: str | None = None) -> dict:
        """Create a Physical Domain (ADR-020 Phase B coverage), optionally
        bound to an existing VLAN Pool. Creating the same name twice
        appends a second entry -- callers should check the existing
        `aci_fabric_policies` Custom Field first if idempotency matters."""
        try:
            location_obj = self._get_location_or_raise(location)
            existing = dict(location_obj.custom_fields or {}).get("aci_fabric_policies") or {}
            physical_domains = list(existing.get("physical_domains") or [])

            entry: dict = {"name": name}
            if vlan_pool:
                entry["vlan_pool"] = vlan_pool
            physical_domains.append(entry)

            location_obj.update(
                {"custom_fields": {"aci_fabric_policies": {**existing, "physical_domains": physical_domains}}}
            )
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected Physical Domain '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"location": location, "physical_domain": name, "physical_domains": physical_domains}

    def create_aep(self, location: str, name: str, domains: list[str] | None = None) -> dict:
        """Create/extend an Attachable Access Entity Profile (ADR-020 Phase
        B coverage). Domains are merged (not replaced) if the AEP already
        exists for this Location."""
        try:
            location_obj = self._get_location_or_raise(location)
            existing = dict(location_obj.custom_fields or {}).get("aci_fabric_policies") or {}
            aeps = list(existing.get("aeps") or [])
            domains = domains or []

            aep = next((a for a in aeps if a.get("name") == name), None)
            if aep is None:
                aeps.append({"name": name, "domains": list(domains)})
            else:
                merged = list(dict.fromkeys([*aep.get("domains", []), *domains]))
                aep["domains"] = merged

            location_obj.update({"custom_fields": {"aci_fabric_policies": {**existing, "aeps": aeps}}})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected AEP '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"location": location, "aep": name, "aeps": aeps}

    def create_leaf_interface_policy_group(self, location: str, name: str, aep: str | None = None) -> dict:
        """Create a Leaf Interface Policy Group (ADR-020 Phase B coverage),
        optionally bound to an existing AEP."""
        try:
            location_obj = self._get_location_or_raise(location)
            existing = dict(location_obj.custom_fields or {}).get("aci_fabric_policies") or {}
            groups = list(existing.get("leaf_interface_policy_groups") or [])

            entry: dict = {"name": name}
            if aep:
                entry["aep"] = aep
            groups.append(entry)

            location_obj.update(
                {"custom_fields": {"aci_fabric_policies": {**existing, "leaf_interface_policy_groups": groups}}}
            )
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected Leaf Interface Policy Group '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"location": location, "leaf_interface_policy_group": name, "leaf_interface_policy_groups": groups}

    # Ported from copilot/aci-platform-comparison (2026-09-08). Not ported:
    # create_aaep (superseded by create_aep above), bind_epg_to_physical_
    # domain/bind_epg_to_vmm_domain (superseded by bind_epg_domain below).
    def _append_location_fabric_policy(self, location: str, key: str, entry: dict) -> dict:
        location_obj = self._get_location_or_raise(location)
        custom_fields = dict(location_obj.custom_fields or {})
        policies = dict(custom_fields.get("aci_fabric_policies") or {})
        values = list(policies.get(key) or [])
        if any(item.get("name") == entry.get("name") for item in values):
            raise NautobotError(f"{key} object '{entry.get('name')}' already exists on Location '{location}'")
        values.append(entry)
        policies[key] = values
        custom_fields["aci_fabric_policies"] = policies
        location_obj.update({"custom_fields": custom_fields})
        return {"location": location, key: entry}

    def create_leaf_interface_profile(self, location: str, name: str, node_id: int, pod_id: int = 1, description: str = "") -> dict:
        entry = {"name": name, "node_id": node_id, "pod_id": pod_id}
        if description: entry["description"] = description
        return self._append_location_fabric_policy(location, "leaf_interface_profiles", entry)

    def create_interface_selector(self, location: str, name: str, leaf_interface_profile: str, policy_group: str, module: int, port: int) -> dict:
        entry = {"name": name, "leaf_interface_profile": leaf_interface_profile, "policy_group": policy_group, "module": module, "port": port}
        return self._append_location_fabric_policy(location, "interface_selectors", entry)

    def _update_epg_custom_fields(self, tenant: str, application_profile: str, epg: str, update: dict) -> dict:
        tenant_obj = self._get_tenant_or_raise(tenant)
        epg_obj = self.api.ipam.vlans.get(name=epg, tenant_id=tenant_obj.id)
        if epg_obj is None:
            raise NautobotError(f"EPG '{epg}' not found in tenant '{tenant}'")
        fields = dict(epg_obj.custom_fields or {})
        if fields.get("aci_application_profile") != application_profile:
            raise NautobotError(f"EPG '{epg}' is not associated with Application Profile '{application_profile}'")
        fields.update(update)
        epg_obj.update({"custom_fields": fields})
        return {"tenant": tenant, "application_profile": application_profile, "epg": epg, **update}

    def create_static_path_binding(self, tenant: str, application_profile: str, epg: str, pod_id: int, node_id: int, module: int, port: int, encap: str, mode: str = "regular") -> dict:
        paths = [{"pod_id": pod_id, "node_id": node_id, "module": module, "port": port, "encap": encap, "mode": mode}]
        return self._update_epg_custom_fields(tenant, application_profile, epg, {"aci_static_paths": paths})

    def create_vmm_domain(
        self,
        location: str,
        name: str,
        controller_name: str,
        host_or_ip: str,
        root_cont_name: str,
        vendor: str = "VMware",
        vlan_pool: str | None = None,
        credential_name: str | None = None,
        dvs_version: str = "unmanaged",
    ) -> dict:
        """Create a VMM Domain with its Controller (ADR-020 Phase D
        coverage), optionally bound to an existing VLAN Pool. The
        Controller's actual vCenter username/password are deliberately NOT
        accepted here -- they are supplied at `terraform apply` time via
        sensitive Terraform variables (`vmm_vcenter_username`/
        `vmm_vcenter_password`), never persisted in this Custom Field,
        matching the APIC's own `aci_username`/`aci_password` handling.
        `credential_name` only reserves the ACI Credential object's own
        name (e.g. for GUI display); it is not a secret."""
        try:
            location_obj = self._get_location_or_raise(location)
            existing = dict(location_obj.custom_fields or {}).get("aci_fabric_policies") or {}
            vmm_domains = list(existing.get("vmm_domains") or [])

            entry: dict = {
                "name": name,
                "vendor": vendor,
                "controller": {
                    "name": controller_name,
                    "host_or_ip": host_or_ip,
                    "root_cont_name": root_cont_name,
                    "dvs_version": dvs_version,
                },
            }
            if vlan_pool:
                entry["vlan_pool"] = vlan_pool
            if credential_name:
                entry["credential"] = {"name": credential_name}
            vmm_domains.append(entry)

            location_obj.update({"custom_fields": {"aci_fabric_policies": {**existing, "vmm_domains": vmm_domains}}})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected VMM Domain '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"location": location, "vmm_domain": name, "vmm_domains": vmm_domains}

    def create_security_domain(self, location: str, name: str, description: str = "") -> dict:
        """Create a Security Domain (ADR-020 Phase F coverage) -- a purely
        additive, fabric-wide named object in the aci_aaa_policies Custom
        Field on Location, same pattern as create_physical_domain."""
        try:
            location_obj = self._get_location_or_raise(location)
            existing = dict(location_obj.custom_fields or {}).get("aci_aaa_policies") or {}
            domains = list(existing.get("security_domains") or [])

            entry: dict = {"name": name}
            if description:
                entry["description"] = description
            domains.append(entry)

            location_obj.update({"custom_fields": {"aci_aaa_policies": {**existing, "security_domains": domains}}})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected Security Domain '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"location": location, "security_domain": name, "security_domains": domains}

    def create_local_user(
        self,
        location: str,
        name: str,
        email: str = "",
        first_name: str = "",
        last_name: str = "",
        phone: str = "",
        account_status: str = "active",
        security_domain: str | None = None,
        role: str | None = None,
        priv_type: str | None = None,
    ) -> dict:
        """Create a Local User (ADR-020 Phase F coverage), optionally bound
        to one Security Domain + Role. The password is deliberately NOT
        accepted here -- it is supplied at `terraform apply` time via the
        sensitive `local_user_passwords` Terraform variable, keyed by this
        user's name, matching create_vmm_domain's credential handling."""
        try:
            location_obj = self._get_location_or_raise(location)
            existing = dict(location_obj.custom_fields or {}).get("aci_aaa_policies") or {}
            local_users = list(existing.get("local_users") or [])

            entry: dict = {"name": name, "account_status": account_status}
            if email:
                entry["email"] = email
            if first_name:
                entry["first_name"] = first_name
            if last_name:
                entry["last_name"] = last_name
            if phone:
                entry["phone"] = phone
            if security_domain:
                domain_entry: dict = {"name": security_domain}
                if role:
                    role_entry: dict = {"name": role}
                    if priv_type:
                        role_entry["priv_type"] = priv_type
                    domain_entry["roles"] = [role_entry]
                entry["security_domains"] = [domain_entry]
            local_users.append(entry)

            location_obj.update({"custom_fields": {"aci_aaa_policies": {**existing, "local_users": local_users}}})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected Local User '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"location": location, "local_user": name, "local_users": local_users}

    # Ported from copilot/aci-platform-comparison (2026-09-08) -- L4-L7/
    # PBR/Service Graph client methods, genuinely new and non-overlapping.
    def _get_epg_or_raise(self, tenant_obj, name: str):
        epg = self.api.ipam.vlans.get(name=name, tenant_id=tenant_obj.id)
        if epg is None:
            raise NautobotError(f"EPG '{name}' not found in tenant '{tenant_obj.name}'")
        custom_fields = dict(epg.custom_fields or {})
        if not custom_fields.get("aci_application_profile") or not custom_fields.get("aci_epg_bridge_domain"):
            raise NautobotError(f"VLAN '{name}' in tenant '{tenant_obj.name}' is not an ACI EPG")
        return epg

    def _update_l4l7_services(self, tenant_obj, entry_type: str, entry: dict) -> list[dict]:
        custom_fields = dict(tenant_obj.custom_fields or {})
        services = dict(custom_fields.get("aci_l4l7_services") or {})
        entries = list(services.get(entry_type) or [])
        if any(item.get("name") == entry["name"] for item in entries):
            raise NautobotError(f"{entry_type[:-1].replace('_', ' ').title()} '{entry['name']}' already exists in tenant '{tenant_obj.name}'")
        entries.append(entry)
        services[entry_type] = entries
        custom_fields["aci_l4l7_services"] = services
        tenant_obj.update({"custom_fields": custom_fields})
        return entries

    def create_l4l7_device(
        self,
        tenant: str,
        name: str,
        consumer_interface: str,
        provider_interface: str | None = None,
        service_type: str = "FW",
        device_type: str = "Virtual",
        function_type: str = "GoTo",
        managed: bool = False,
        context_aware: str = "single-Context",
        vmm_domain: str | None = None,
        description: str = "",
    ) -> dict:
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            entry = {
                "name": name,
                "service_type": service_type,
                "device_type": device_type,
                "function_type": function_type,
                "managed": managed,
                "context_aware": context_aware,
                "logical_interfaces": [{"name": consumer_interface}],
            }
            if provider_interface:
                entry["logical_interfaces"].append({"name": provider_interface})
            if vmm_domain:
                entry["vmm_domain"] = vmm_domain
            if description:
                entry["description"] = description
            devices = self._update_l4l7_services(tenant_obj, "devices", entry)
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected L4-L7 device '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "device": name, "devices": devices}

    def create_service_graph(
        self,
        tenant: str,
        name: str,
        contract: str,
        device: str,
        consumer_logical_interface: str,
        consumer_redirect_policy: str,
        provider_logical_interface: str,
        provider_redirect_policy: str,
        node_name: str = "node-1",
        template_type: str = "FW_ROUTED",
        description: str = "",
    ) -> dict:
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            entry = {
                "name": name,
                "contract": contract,
                "device": device,
                "consumer": {
                    "logical_interface": consumer_logical_interface,
                    "redirect_policy": consumer_redirect_policy,
                    "l3_destination": False,
                },
                "provider": {
                    "logical_interface": provider_logical_interface,
                    "redirect_policy": provider_redirect_policy,
                    "l3_destination": False,
                },
                "node_name": node_name,
                "template_type": template_type,
            }
            if description:
                entry["description"] = description
            graphs = self._update_l4l7_services(tenant_obj, "service_graphs", entry)
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected service graph '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "service_graph": name, "service_graphs": graphs}

    def create_pbr_policy(
        self,
        tenant: str,
        name: str,
        destination_ip: str,
        destination_mac: str | None = None,
        destination_type: str = "L3",
        anycast: bool = False,
        pod_aware: bool = False,
        resilient_hashing: bool = False,
        description: str = "",
    ) -> dict:
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            destination = {"ip": destination_ip}
            if destination_mac:
                destination["mac"] = destination_mac
            entry = {
                "name": name,
                "destination_type": destination_type,
                "anycast": anycast,
                "pod_aware": pod_aware,
                "resilient_hashing": resilient_hashing,
                "destinations": [destination],
            }
            if description:
                entry["description"] = description
            policies = self._update_l4l7_services(tenant_obj, "redirect_policies", entry)
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected PBR policy '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "redirect_policy": name, "redirect_policies": policies}

    def create_one_arm_service_graph(
        self,
        tenant: str,
        name: str,
        contract: str,
        device: str,
        logical_interface: str,
        redirect_policy: str,
        node_name: str = "node-1",
        template_type: str = "ONE_NODE_ADC_ONE_ARM",
        description: str = "",
    ) -> dict:
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            entry = {
                "name": name,
                "contract": contract,
                "device": device,
                "consumer": {
                    "logical_interface": logical_interface,
                    "redirect_policy": redirect_policy,
                    "l3_destination": False,
                },
                "node_name": node_name,
                "template_type": template_type,
            }
            if description:
                entry["description"] = description
            graphs = self._update_l4l7_services(tenant_obj, "service_graphs", entry)
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected one-arm service graph '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "service_graph": name, "service_graphs": graphs}

    def create_pbr_contract(
        self,
        tenant: str,
        name: str,
        filter_name: str,
        service_graph: str,
        consumer_epg: str,
        provider_epg: str,
        ether_type: str = "ip",
        ip_protocol: str = "unspecified",
        description: str = "",
    ) -> dict:
        try:
            tenant_obj = self._get_tenant_or_raise(tenant)
            consumer = self._get_epg_or_raise(tenant_obj, consumer_epg)
            provider = self._get_epg_or_raise(tenant_obj, provider_epg)
            custom_fields = dict(tenant_obj.custom_fields or {})
            contracts_data = dict(custom_fields.get("aci_contracts") or {})
            filters = list(contracts_data.get("filters") or [])
            contracts = list(contracts_data.get("contracts") or [])
            if any(contract.get("name") == name for contract in contracts):
                raise NautobotError(f"Contract '{name}' already exists in tenant '{tenant}'")
            if not any(filter_item.get("name") == filter_name for filter_item in filters):
                filters.append({"name": filter_name, "entries": [{"name": "default", "ether_type": ether_type, "ip_protocol": ip_protocol}]})
            subject = {"name": f"{name}-subj", "filters": [filter_name], "service_graph": service_graph}
            contract = {"name": name, "scope": "context", "subjects": [subject]}
            if description:
                contract["description"] = description
            contracts.append(contract)
            custom_fields["aci_contracts"] = {"filters": filters, "contracts": contracts}
            tenant_obj.update({"custom_fields": custom_fields})

            for epg, direction in ((consumer, "consumed"), (provider, "provided")):
                epg_custom_fields = dict(epg.custom_fields or {})
                epg_contracts = dict(epg_custom_fields.get("aci_epg_contracts") or {})
                contract_names = list(epg_contracts.get(direction) or [])
                if name not in contract_names:
                    contract_names.append(name)
                epg_contracts[direction] = contract_names
                epg_custom_fields["aci_epg_contracts"] = epg_contracts
                epg.update({"custom_fields": epg_custom_fields})
        except pynautobot.RequestError as exc:
            raise NautobotError(f"Nautobot rejected PBR contract '{name}': {exc}") from exc
        except NautobotError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        return {"tenant": tenant, "contract": name, "consumer_epg": consumer_epg, "provider_epg": provider_epg}

    def get_tenant_status(self, name: str) -> dict | None:
        """Read back the custom_fields write_results.py (Milestone 4) writes
        after a pipeline run -- validation_status/last_pipeline_id/etc.
        """
        try:
            tenant = self.api.tenancy.tenants.get(name=name)
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
        if tenant is None:
            return None
        return dict(tenant)

    def ping(self) -> None:
        """Cheap reachability check for the /health endpoint (Ref-Arch §7.6)
        -- raises NautobotError on failure, returns None on success."""
        try:
            self.api.status()
        except Exception as exc:  # noqa: BLE001
            raise NautobotError(f"Nautobot unreachable or auth failed: {exc}") from exc
