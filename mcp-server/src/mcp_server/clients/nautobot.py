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
