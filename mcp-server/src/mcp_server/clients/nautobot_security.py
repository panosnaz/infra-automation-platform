"""Endpoint Security Groups and vzAny (2026-10-15).

ESGs are stored on the Tenant, in the JSON Custom Field
`aci_endpoint_security_groups` ({"esgs": [...]}) -- like contracts and L3Outs,
they have no natural Nautobot object. vzAny belongs to a VRF, so its
contracts are a Custom Field on the Nautobot VRF (`aci_vzany_contracts`,
{"provided": [...], "consumed": [...]}, the same shape as an EPG's
`aci_epg_contracts`); the VRF's preferred-group switch is `update_vrf`'s
`preferred_group`.

Several rules here are APIC rules. APIC 6.2 REJECTS each with HTTP 400 --
an EPG selected by two ESGs, an EPG from another VRF, one IP subnet or one
tag selector (key, value) in two ESGs of a VRF (probed 2026-10-15). At apply
time that fails the pipeline part-way through, so they are refused here,
naming the conflicting object, and again by the generator.
"""
from __future__ import annotations

from mcp_server.clients.nautobot_lifecycle import (
    DEPLOY_NOT_TRIGGERED,
    DEPLOY_VIA_TENANT,
    _cf,
    _nautobot_errors,
    _set_or_drop,
)
from mcp_server.errors import NautobotError

ESG_FIELD = "aci_endpoint_security_groups"
VZANY_FIELD = "aci_vzany_contracts"
_VERB = {"provided": "provides", "consumed": "consumes"}
_SELECTOR_KEYS = {"epg": "epg_selectors", "ip_subnet": "ip_subnet_selectors", "tag": "tag_selectors"}


class SecurityGroupMixin:
    """Requires `api`, `_get_tenant_or_raise`, `_get_epg_vlan` and
    `_tenant_bridge_domains` on the host class (NautobotClient has them)."""

    # --- helpers -------------------------------------------------------------------

    def _esg_state(self, tenant: str):
        tenant_obj = self._get_tenant_or_raise(tenant)
        fields = _cf(tenant_obj)
        data = fields.get(ESG_FIELD) if isinstance(fields.get(ESG_FIELD), dict) else {}
        fields[ESG_FIELD] = data
        return tenant_obj, fields, list(data.get("esgs") or [])

    @staticmethod
    def _save_esgs(tenant_obj, fields: dict, esgs: list) -> None:
        _set_or_drop(fields[ESG_FIELD], "esgs", esgs)
        tenant_obj.update({"custom_fields": fields})

    @staticmethod
    def _require_esg(esgs: list, name: str, tenant: str) -> dict:
        esg = next((e for e in esgs if e.get("name") == name), None)
        if esg is None:
            known = ", ".join(sorted(e.get("name", "") for e in esgs)) or "none"
            raise NautobotError(f"ESG '{name}' not found in tenant '{tenant}' (known: {known})")
        return esg

    def _require_vrf(self, tenant_obj, tenant: str, vrf: str):
        record = self.api.ipam.vrfs.get(name=vrf, tenant_id=tenant_obj.id)
        if record is None:
            known = ", ".join(sorted(v.name for v in self.api.ipam.vrfs.filter(tenant_id=tenant_obj.id))) or "none"
            raise NautobotError(f"VRF '{vrf}' not found in tenant '{tenant}' (known: {known})")
        return record

    @staticmethod
    def _require_contract(fields: dict, tenant: str, contract: str) -> None:
        names = {c.get("name") for c in ((fields.get("aci_contracts") or {}).get("contracts") or [])}
        if contract not in names:
            known = ", ".join(sorted(n for n in names if n)) or "none"
            raise NautobotError(
                f"Contract '{contract}' not found in tenant '{tenant}' (known: {known}) -- create it with create_contract first"
            )

    def _result(self, tenant: str, esg: dict) -> dict:
        return {"tenant": tenant, "esg": esg, "deploy": DEPLOY_VIA_TENANT}

    # --- ESG ---------------------------------------------------------------------------

    def create_esg(self, tenant, application_profile, name, vrf, description=None,
                   preferred_group_member=None, intra_esg_isolation=None, shutdown=None) -> dict:
        with _nautobot_errors(f"ESG '{name}'"):
            tenant_obj, fields, esgs = self._esg_state(tenant)
            clash = next((e for e in esgs if e.get("name") == name), None)
            if clash is not None:
                raise NautobotError(
                    f"ESG '{name}' already exists in tenant '{tenant}' (application profile "
                    f"'{clash.get('application_profile')}') -- use update_esg to change it"
                )
            self._require_vrf(tenant_obj, tenant, vrf)
            entry = {"name": name, "application_profile": application_profile, "vrf": vrf}
            entry.update({k: v for k, v in (("description", description),
                                            ("preferred_group_member", preferred_group_member),
                                            ("intra_esg_isolation", intra_esg_isolation),
                                            ("shutdown", shutdown)) if v is not None})
            esgs.append(entry)
            self._save_esgs(tenant_obj, fields, esgs)
        return self._result(tenant, entry)

    def update_esg(self, tenant, name, description=None, preferred_group_member=None,
                   intra_esg_isolation=None, shutdown=None) -> dict:
        with _nautobot_errors(f"ESG '{name}'"):
            tenant_obj, fields, esgs = self._esg_state(tenant)
            esg = self._require_esg(esgs, name, tenant)
            esg.update({k: v for k, v in (("description", description),
                                          ("preferred_group_member", preferred_group_member),
                                          ("intra_esg_isolation", intra_esg_isolation),
                                          ("shutdown", shutdown)) if v is not None})
            self._save_esgs(tenant_obj, fields, esgs)
        return self._result(tenant, esg)

    # --- selectors -----------------------------------------------------------------------

    def _add_selector(self, tenant_obj, fields, esgs, esg, kind, entry) -> None:
        key = _SELECTOR_KEYS[kind]
        esg[key] = list(esg.get(key) or []) + [entry]
        self._save_esgs(tenant_obj, fields, esgs)

    def create_esg_epg_selector(self, tenant, esg, application_profile, epg, description=None) -> dict:
        with _nautobot_errors(f"EPG selector on ESG '{esg}'"):
            tenant_obj, fields, esgs = self._esg_state(tenant)
            target = self._require_esg(esgs, esg, tenant)
            vlan = self._get_epg_vlan(tenant_obj, tenant, application_profile, epg)
            bd = (vlan.custom_fields or {}).get("aci_epg_bridge_domain")
            bd_vrfs = sorted({v for b in self._tenant_bridge_domains(tenant_obj) if b["name"] == bd for v in b["vrfs"]})
            if bd_vrfs and target["vrf"] not in bd_vrfs:
                raise NautobotError(
                    f"EPG '{epg}' is in VRF '{', '.join(bd_vrfs)}' (bridge domain '{bd}'), but ESG '{esg}' is in VRF "
                    f"'{target['vrf']}' -- an ESG can only select endpoints in its own VRF"
                )
            for other in esgs:
                for sel in other.get("epg_selectors") or []:
                    if sel.get("application_profile") == application_profile and sel.get("endpoint_group") == epg:
                        raise NautobotError(
                            f"EPG '{epg}' is already selected by ESG '{other.get('name')}' -- an EPG can be "
                            "selected by only one ESG"
                        )
            entry = {"application_profile": application_profile, "endpoint_group": epg}
            if description:
                entry["description"] = description
            self._add_selector(tenant_obj, fields, esgs, target, "epg", entry)
        return self._result(tenant, target)

    def create_esg_ip_subnet_selector(self, tenant, esg, subnet, description=None) -> dict:
        with _nautobot_errors(f"IP subnet selector on ESG '{esg}'"):
            tenant_obj, fields, esgs = self._esg_state(tenant)
            target = self._require_esg(esgs, esg, tenant)
            for other in esgs:
                if other.get("vrf") != target["vrf"]:
                    continue
                if any(s.get("value") == subnet for s in other.get("ip_subnet_selectors") or []):
                    raise NautobotError(
                        f"IP subnet {subnet} is already selected by ESG '{other.get('name')}' in VRF "
                        f"'{target['vrf']}' -- a subnet can be in only one ESG per VRF"
                    )
            entry = {"value": subnet}
            if description:
                entry["description"] = description
            self._add_selector(tenant_obj, fields, esgs, target, "ip_subnet", entry)
        return self._result(tenant, target)

    def create_esg_tag_selector(self, tenant, esg, key, value, operator="equals", description=None) -> dict:
        with _nautobot_errors(f"tag selector on ESG '{esg}'"):
            tenant_obj, fields, esgs = self._esg_state(tenant)
            target = self._require_esg(esgs, esg, tenant)
            if any(s.get("key") == key and s.get("value") == value for s in target.get("tag_selectors") or []):
                raise NautobotError(f"ESG '{esg}' already has a tag selector {key}={value}")
            for other in esgs:
                if other.get("vrf") == target["vrf"] and any(
                        s.get("key") == key and s.get("value") == value for s in other.get("tag_selectors") or []):
                    raise NautobotError(
                        f"tag selector {key}={value} is already in ESG '{other.get('name')}' in VRF "
                        f"'{target['vrf']}' -- a tag selector can be in only one ESG per VRF"
                    )
            entry = {"key": key, "value": value, "operator": operator}
            if description:
                entry["description"] = description
            self._add_selector(tenant_obj, fields, esgs, target, "tag", entry)
        return self._result(tenant, target)

    def delete_esg_selector(self, tenant, esg, selector_type, application_profile=None, epg=None,
                            subnet=None, key=None, value=None) -> dict:
        match = {
            "epg": lambda s: s.get("application_profile") == application_profile and s.get("endpoint_group") == epg,
            "ip_subnet": lambda s: s.get("value") == subnet,
            "tag": lambda s: s.get("key") == key and s.get("value") == value,
        }[selector_type]
        label = {"epg": f"{application_profile}/{epg}", "ip_subnet": subnet, "tag": f"{key}={value}"}[selector_type]
        with _nautobot_errors(f"{selector_type} selector on ESG '{esg}'"):
            tenant_obj, fields, esgs = self._esg_state(tenant)
            target = self._require_esg(esgs, esg, tenant)
            list_key = _SELECTOR_KEYS[selector_type]
            current = list(target.get(list_key) or [])
            kept = [s for s in current if not match(s)]
            if len(kept) == len(current):
                raise NautobotError(f"ESG '{esg}' has no {selector_type} selector {label}")
            _set_or_drop(target, list_key, kept)
            self._save_esgs(tenant_obj, fields, esgs)
        return self._result(tenant, target)

    # --- contracts -------------------------------------------------------------------------

    def bind_esg_contract(self, tenant, esg, contract, relation) -> dict:
        with _nautobot_errors(f"contract on ESG '{esg}'"):
            tenant_obj, fields, esgs = self._esg_state(tenant)
            target = self._require_esg(esgs, esg, tenant)
            self._require_contract(fields, tenant, contract)
            key = f"{relation}_contracts"
            current = list(target.get(key) or [])
            if contract in current:
                raise NautobotError(f"ESG '{esg}' already {_VERB[relation]} '{contract}'")
            target[key] = current + [contract]
            self._save_esgs(tenant_obj, fields, esgs)
        return self._result(tenant, target)

    def unbind_esg_contract(self, tenant, esg, contract, relation) -> dict:
        with _nautobot_errors(f"contract on ESG '{esg}'"):
            tenant_obj, fields, esgs = self._esg_state(tenant)
            target = self._require_esg(esgs, esg, tenant)
            key = f"{relation}_contracts"
            current = list(target.get(key) or [])
            if contract not in current:
                raise NautobotError(
                    f"ESG '{esg}' does not {_VERB[relation][:-1]} '{contract}' (it {_VERB[relation]}: "
                    f"{', '.join(current) or 'none'})"
                )
            _set_or_drop(target, key, [c for c in current if c != contract])
            self._save_esgs(tenant_obj, fields, esgs)
        return self._result(tenant, target)

    # --- vzAny ---------------------------------------------------------------------------

    def _vzany_change(self, tenant, vrf, contract, relation, bind: bool) -> dict:
        with _nautobot_errors(f"vzAny of VRF '{vrf}'"):
            tenant_obj = self._get_tenant_or_raise(tenant)
            record = self._require_vrf(tenant_obj, tenant, vrf)
            fields = _cf(record)
            bound = dict(fields.get(VZANY_FIELD) or {})
            current = list(bound.get(relation) or [])
            if bind:
                tenant_cf = _cf(tenant_obj)
                self._require_contract(tenant_cf, tenant, contract)
                # APIC 6.2: HTTP 400 "vzAny cannot be used as provider for this
                # contract" unless its scope is context (probed 2026-10-15).
                # Consuming works for every scope. Unset = APIC default, context.
                scope = next((c.get("scope") for c in (tenant_cf.get("aci_contracts") or {}).get("contracts") or []
                              if c.get("name") == contract), None) or "context"
                if relation == "provided" and scope != "context":
                    raise NautobotError(
                        f"vzAny can only provide a contract whose scope is 'context' (VRF); '{contract}' is '{scope}'. "
                        "APIC rejects it. Consuming it is allowed, or use a VRF-scoped contract."
                    )
                if contract in current:
                    raise NautobotError(f"vzAny of VRF '{vrf}' already {_VERB[relation]} '{contract}'")
                current.append(contract)
            else:
                if contract not in current:
                    raise NautobotError(
                        f"vzAny of VRF '{vrf}' does not {_VERB[relation][:-1]} '{contract}' (it {_VERB[relation]}: "
                        f"{', '.join(current) or 'none'})"
                    )
                current = [c for c in current if c != contract]
            _set_or_drop(bound, relation, current)
            fields[VZANY_FIELD] = bound
            record.update({"custom_fields": fields})
        return {
            "tenant": tenant, "vrf": vrf, "vzany_contracts": bound,
            "note": "A vzAny contract applies to EVERY EPG and ESG in the VRF.",
            "deploy": DEPLOY_NOT_TRIGGERED.format(what="VRF"),
        }

    def bind_vzany_contract(self, tenant, vrf, contract, relation) -> dict:
        return self._vzany_change(tenant, vrf, contract, relation, bind=True)

    def unbind_vzany_contract(self, tenant, vrf, contract, relation) -> dict:
        return self._vzany_change(tenant, vrf, contract, relation, bind=False)
