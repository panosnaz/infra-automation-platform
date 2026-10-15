"""In-memory fake of the pynautobot API, shared by the client-level tests.

It is deliberately strict where Nautobot is strict, because a permissive fake
is how real bugs got through: it rejects filter names Nautobot rejects (the
`location_id` 400, 2026-10-12), refuses an IP Address with no namespace or no
parent prefix with Nautobot's own error text, and fails if a record's Custom
Fields were mutated in place before update() (the pynautobot shallow-copy
failure, 2026-09-16).
"""
from __future__ import annotations

import copy
import ipaddress
import itertools
from types import SimpleNamespace

import pynautobot

_ids = itertools.count(1)

# Keys that hold a related object; create() receives them as ids.
_FK_FIELDS = {"device", "interface", "ip_address", "tenant", "namespace", "location", "vrf", "status"}


def nautobot_error(message: str) -> pynautobot.RequestError:
    """A RequestError carrying a Nautobot 400 body, as pynautobot builds it."""
    resp = SimpleNamespace(
        status_code=400, reason="Bad Request", url="http://nautobot/api/",
        text=str({"namespace": [message]}), request=SimpleNamespace(body=b""),
        json=lambda: {"namespace": [message]},
    )
    return pynautobot.RequestError(resp)


class Rec:
    def __init__(self, store, **attrs):
        self._store = store
        self.custom_fields = attrs.pop("custom_fields", {}) or {}
        self.description = attrs.pop("description", "")
        for k, v in attrs.items():
            setattr(self, k, v)
        self.updates: list[dict] = []
        self.deleted = False
        # What pynautobot would diff against: a snapshot of the state it last
        # saw. If code mutates self.custom_fields in place before update(),
        # this snapshot is what proves it.
        self.snapshot = copy.deepcopy(self.custom_fields)

    def update(self, payload):
        assert self.custom_fields == self.snapshot, "custom_fields mutated in place before update()"
        self.updates.append(copy.deepcopy(payload))
        if "custom_fields" in payload:
            self.custom_fields = payload["custom_fields"]
        if "description" in payload:
            self.description = payload["description"]
        self.snapshot = copy.deepcopy(self.custom_fields)
        return True

    def delete(self):
        self.deleted = True
        self._store.remove(self)
        return True


class Endpoint:
    # Filters Nautobot 2.x actually accepts here. An unknown one is a 400 in
    # Nautobot, so it must fail here too -- the first version of this fake
    # accepted `location_id` on devices, and get_fabric_intent shipped with
    # it and failed on its first live call (2026-10-12).
    ACCEPTED = {"tenant_id", "location", "vrf", "name", "namespace", "device_id", "address", "prefix"}

    def __init__(self, api=None, kind=None):
        self.items: list[Rec] = []
        self._api = api
        self._kind = kind

    def add(self, **attrs):
        rec = Rec(self.items, **attrs)
        self.items.append(rec)
        return rec

    def create(self, **attrs):
        """Like add(), but the way client code calls it: related objects as
        ids, a fresh id assigned, and Nautobot's own validation for IPs."""
        if self._kind == "ip_addresses":
            self._api._validate_ip(attrs)
        for key in list(attrs):
            if key in _FK_FIELDS and isinstance(attrs[key], (str, int)):
                attrs[key] = SimpleNamespace(id=attrs[key])
        attrs.setdefault("id", f"{self._kind or 'rec'}-{next(_ids)}")
        rec = self.add(**attrs)
        if self._kind == "ip_address_to_interface":
            self._api._assign(rec)
        return rec

    @classmethod
    def _matches(cls, rec, kw):
        for key, want in kw.items():
            if key not in cls.ACCEPTED and not key.startswith("cf_"):
                raise AssertionError(f"Nautobot would reject filter '{key}' (400 Unknown filter field)")
            if key in ("tenant_id", "device_id"):
                got = getattr(getattr(rec, key[:-3], None), "id", None)
            elif key in ("location", "namespace"):
                got = getattr(getattr(rec, key, None), "id", None)
            elif key == "vrf":
                got = rec.vrf.id
            elif key.startswith("cf_"):
                got = rec.custom_fields.get(key[3:])
            else:
                got = getattr(rec, key, None)
            if got != want:
                return False
        return True

    def filter(self, **kw):
        return [r for r in list(self.items) if self._matches(r, kw)]

    def all(self):
        return list(self.items)

    def get(self, **kw):
        found = self.filter(**kw)
        return found[0] if found else None


class FakeApi:
    def __init__(self):
        e = lambda kind=None: Endpoint(self, kind)  # noqa: E731
        self.tenancy = SimpleNamespace(tenants=e())
        self.ipam = SimpleNamespace(
            vrfs=e(), prefixes=e("prefixes"), vlans=e(), vrf_prefix_assignments=e(),
            ip_addresses=e("ip_addresses"), namespaces=e(), ip_address_to_interface=e("ip_address_to_interface"),
        )
        self.dcim = SimpleNamespace(devices=e(), locations=e(), interfaces=e("interfaces"))
        self.extras = SimpleNamespace(statuses=SimpleNamespace(get=lambda **kw: SimpleNamespace(id="status-active")))
        self.ipam.namespaces.add(id="ns-global", name="Global")

    def _validate_ip(self, attrs):
        if attrs.get("namespace") is None and attrs.get("parent") is None:
            raise nautobot_error("One of parent or namespace must be provided")
        host = ipaddress.ip_interface(attrs["address"]).ip
        if not any(host in ipaddress.ip_network(str(p.prefix)) for p in self.ipam.prefixes.items):
            raise nautobot_error(f"No suitable parent Prefix for {host} exists in Namespace Global")

    def _assign(self, assignment):
        ip = next(i for i in self.ipam.ip_addresses.items if i.id == assignment.ip_address.id)
        iface = next(i for i in self.dcim.interfaces.items if i.id == assignment.interface.id)
        ip.device = iface.device
