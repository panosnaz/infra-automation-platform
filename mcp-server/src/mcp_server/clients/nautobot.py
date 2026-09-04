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
