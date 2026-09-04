"""ACI-specific per-tool request schemas -- thin argument validation only,
never a cross-domain intent envelope (ADR-018)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Same naming convention the live OPA policy_check job already enforces
# (Execution-Framework.md Milestone 3, docker/platform-api/policy/cisco_aci/tenant_naming.rego)
# -- validating it here too gives a fast, clear MCP-side error instead of a
# slower round trip that only fails once the pipeline's policy_check job runs.
_TENANT_NAME_RE = re.compile(r"^[a-z0-9-]+$")

# ACI's own object-naming rule is looser than the Tenant policy above (real
# ACI allows letters/digits/underscore/period/colon/hyphen for most object
# names) -- used for every non-Tenant name below (VRF, BD, EPG, AP, Contract,
# Filter, L3Out, External EPG).
_ACI_NAME_RE = re.compile(r"^[a-zA-Z0-9_.:-]+$")


def _validate_aci_name(v: str) -> str:
    if not _ACI_NAME_RE.match(v):
        raise ValueError(
            f"'{v}' is not a valid ACI object name (allowed: letters, digits, '_', '.', ':', '-')"
        )
    return v


class CreateTenantRequest(BaseModel):
    name: str = Field(description="Tenant name, e.g. 'finance'. Must match ^[a-z0-9-]+$ (lowercase, digits, hyphens only) -- the same rule the pipeline's OPA policy_check job enforces.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _TENANT_NAME_RE.match(v):
            raise ValueError(
                f"tenant name '{v}' does not match required pattern ^[a-z0-9-]+$ "
                "(this mirrors the pipeline's own policy_check job -- fixing it "
                "here avoids a guaranteed pipeline denial later)"
            )
        return v


class CreateVrfRequest(BaseModel):
    """ADR-020 Phase A item 1 coverage: a first-class Nautobot ipam.vrf
    object, tenant-scoped."""

    tenant: str = Field(description="Name of the existing Tenant this VRF belongs to.")
    name: str = Field(description="VRF name.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateBridgeDomainRequest(BaseModel):
    """ADR-020 Phase A item 1 coverage. BD identity is derived from a
    Prefix's description (`"ACI Bridge Domain: <bd>:<tenant>"`, see
    transformer.py's module docstring) -- this tool creates that Prefix and
    its VRF assignment, it does not create a separate first-class BD
    object (Nautobot has none)."""

    tenant: str = Field(description="Name of the existing Tenant this Bridge Domain belongs to.")
    vrf: str = Field(description="Name of the existing VRF (in the same tenant) this Bridge Domain is associated with.")
    name: str = Field(description="Bridge Domain name.")
    gateway_ip: str = Field(description="Gateway IP and prefix length for the BD's subnet, e.g. '10.10.10.1/24'.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateEpgRequest(BaseModel):
    """ADR-020 Phase A item 2 coverage. EPGs are modeled as Nautobot VLAN
    objects with two Custom Fields set (aci_application_profile,
    aci_epg_bridge_domain) -- see transformer.py's `_build_application_profiles()`."""

    tenant: str = Field(description="Name of the existing Tenant this EPG belongs to.")
    application_profile: str = Field(description="Application Profile name this EPG belongs to (created implicitly if new).")
    bridge_domain: str = Field(description="Bridge Domain name this EPG binds to (must already exist in this tenant).")
    name: str = Field(description="EPG name.")
    vid: int = Field(description="VLAN ID backing this EPG in Nautobot's IPAM (EPGs are modeled as VLANs).", ge=1, le=4094)
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class BindEpgDomainRequest(BaseModel):
    """ADR-020 Phase D follow-on coverage. Binds an existing EPG to a
    Physical or VMM Domain -- appends/updates one entry in the `domains`
    list of the EPG's own `aci_epg_domains` Custom Field (see
    transformer.py's `_build_application_profiles()`). domain_type must be
    "physical" or "vmm" so Terraform can resolve target_dn against the
    correct resource map (aci_physical_domain vs. aci_vmm_domain) -- a
    Physical Domain and a VMM Domain could share the same name."""

    tenant: str = Field(description="Name of the existing Tenant the EPG belongs to.")
    application_profile: str = Field(description="Application Profile name the EPG belongs to.")
    epg: str = Field(description="Name of the existing EPG to bind.")
    domain: str = Field(description="Name of the existing Physical or VMM Domain to bind to.")
    domain_type: str = Field(description="Either 'physical' or 'vmm'.")
    resolution_immediacy: str | None = Field(default=None, description="Optional: 'immediate' or 'lazy' (ACI default applies if omitted).")
    deployment_immediacy: str | None = Field(default=None, description="Optional: 'immediate' or 'lazy' (ACI default applies if omitted).")

    @field_validator("domain_type")
    @classmethod
    def _validate_domain_type(cls, v: str) -> str:
        if v not in ("physical", "vmm"):
            raise ValueError("domain_type must be 'physical' or 'vmm'")
        return v


class CreateSecurityDomainRequest(BaseModel):
    """ADR-020 Phase F coverage. Security Domains are fabric-wide, purely
    additive named objects (no default instance), modeled the same way as
    Phase B/E's fabric-wide objects: a JSON Custom Field on Location
    (`aci_aaa_policies`)."""

    name: str = Field(description="Security Domain name.")
    location: str = Field(default="ACI-Lab", description="Nautobot Location representing the ACI fabric/site.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateLocalUserRequest(BaseModel):
    """ADR-020 Phase F coverage. Local Users are fabric-wide, purely
    additive named objects, modeled the same way as CreateSecurityDomain-
    Request above. The password is deliberately NOT a field on this
    schema -- same boundary as VMM Domain's Controller credential
    (ADR-020 Phase D): it is never written to Nautobot or seen by the AI
    layer, only supplied at `terraform apply` time via the sensitive
    `local_user_passwords` Terraform variable. This tool optionally binds
    one Security Domain + one Role at creation time (a further increment
    would be needed for multiple bindings in one call)."""

    name: str = Field(description="Local User name.")
    location: str = Field(default="ACI-Lab", description="Nautobot Location representing the ACI fabric/site.")
    email: str = Field(default="", description="Optional email address")
    first_name: str = Field(default="", description="Optional first name")
    last_name: str = Field(default="", description="Optional last name")
    phone: str = Field(default="", description="Optional phone number")
    account_status: str = Field(default="active", description="'active' or 'inactive'.")
    security_domain: str | None = Field(default=None, description="Optional: name of an existing Security Domain to bind this user to.")
    role: str | None = Field(default=None, description="Optional: RBAC role name (e.g. 'read-all', 'admin') within security_domain. Ignored if security_domain is not set.")
    priv_type: str | None = Field(default=None, description="Optional: 'readPriv' or 'writePriv' for the role above.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateContractRequest(BaseModel):
    """ADR-020 Phase A item 3 coverage. Contracts/Filters are modeled as a
    single structured JSON Custom Field on Tenant (`aci_contracts`) -- this
    tool appends one Contract (with a single Subject binding one Filter,
    created if it doesn't already exist for this tenant) rather than
    creating a first-class Nautobot object."""

    tenant: str = Field(description="Name of the existing Tenant this Contract belongs to.")
    name: str = Field(description="Contract name.")
    filter_name: str = Field(description="Name of the Filter this contract's subject binds. Created (with one 'default' entry) if it doesn't already exist in this tenant.")
    scope: str = Field(default="context", description="Contract scope. Allowed: 'context', 'tenant', 'application-profile', 'global'.")
    ether_type: str = Field(default="ip", description="Filter entry ether type, only used when the filter is newly created.")
    ip_protocol: str = Field(default="unspecified", description="Filter entry IP protocol, only used when the filter is newly created.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name", "filter_name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateL3OutRequest(BaseModel):
    """ADR-020 Phase A item 4 coverage, logical-only scope (no physical
    interface/OSPF/BGP attachment -- see ADR-020's Phase A item 4 writeup
    for why). L3Outs are modeled as a structured JSON Custom Field on
    Tenant (`aci_l3outs`)."""

    tenant: str = Field(description="Name of the existing Tenant this L3Out belongs to.")
    vrf: str = Field(description="Name of the existing VRF (in the same tenant) this L3Out is associated with.")
    name: str = Field(description="L3Out name.")
    external_epg_name: str = Field(description="External EPG name for this L3Out.")
    subnet: str = Field(default="0.0.0.0/0", description="External subnet (CIDR) for the External EPG, e.g. '0.0.0.0/0'.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name", "external_epg_name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateVlanPoolRequest(BaseModel):
    """ADR-020 Phase B coverage. VLAN Pools/Physical Domains/AEPs/Leaf
    Interface Policy Groups are fabric-wide, not Tenant-scoped, so they're
    modeled as a structured JSON Custom Field (`aci_fabric_policies`) on
    the Location representing the ACI fabric/site, not on Tenant (see
    transformer.py's `_build_fabric_and_access_policies()`).

    Appends one encap range into the named pool -- creates the pool first
    if it doesn't already exist for this Location, matching create_contract's
    create-filter-if-missing/append-entry convention.
    """

    name: str = Field(description="VLAN Pool name.")
    range_from: int = Field(description="First VLAN ID in this range.", ge=1, le=4094)
    range_to: int = Field(description="Last VLAN ID in this range.", ge=1, le=4094)
    location: str = Field(default="ACI-Lab", description="Name of the existing Nautobot Location representing the ACI fabric/site (this lab has one: 'ACI-Lab').")
    alloc_mode: str = Field(default="static", description="Pool allocation mode. Allowed: 'static', 'dynamic'.")
    range_alloc_mode: str | None = Field(default=None, description="Range-level allocation mode override. Allowed: 'static', 'dynamic', 'inherit' (default).")
    role: str = Field(default="external", description="Range role. Allowed: 'external' (used by Physical/L3 Domains), 'internal' (used by VMM Domains).")
    description: str = Field(default="", description="Optional free-text description, only applied when the pool is newly created.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreatePhysicalDomainRequest(BaseModel):
    """ADR-020 Phase B coverage. Logical-only: models the Physical Domain
    object and its VLAN Pool relation, no physical port/interface binding
    (this lab's simulator has zero real leaf/spine interface data -- see
    ADR-020 Phase B writeup)."""

    name: str = Field(description="Physical Domain name.")
    location: str = Field(default="ACI-Lab", description="Name of the existing Nautobot Location representing the ACI fabric/site.")
    vlan_pool: str | None = Field(default=None, description="Name of an existing VLAN Pool (in this same Location) to bind this domain to. Omit to leave unbound.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateAepRequest(BaseModel):
    """ADR-020 Phase B coverage: an Attachable Access Entity Profile (AEP),
    bound to zero or more existing Physical Domains."""

    name: str = Field(description="AEP name.")
    location: str = Field(default="ACI-Lab", description="Name of the existing Nautobot Location representing the ACI fabric/site.")
    domains: list[str] = Field(default_factory=list, description="Names of existing Physical Domains (in this same Location) to bind this AEP to. Domains are merged with any already bound on repeated calls, not replaced.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateLeafInterfacePolicyGroupRequest(BaseModel):
    """ADR-020 Phase B coverage. Logical-only: models the policy group
    object and its AEP relation, no physical leaf/port selector binding
    (same simulator limitation as CreatePhysicalDomainRequest)."""

    name: str = Field(description="Leaf Interface Policy Group name.")
    location: str = Field(default="ACI-Lab", description="Name of the existing Nautobot Location representing the ACI fabric/site.")
    aep: str | None = Field(default=None, description="Name of an existing AEP (in this same Location) to bind this policy group to. Omit to leave unbound.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateVmmDomainRequest(BaseModel):
    """ADR-020 Phase D coverage: a VMM Domain and its Controller (vCenter
    host/datacenter association), optionally bound to an existing VLAN
    Pool. The Controller's actual vCenter username/password are
    deliberately NOT part of this request -- they are supplied at
    `terraform apply` time via sensitive Terraform variables
    (`vmm_vcenter_username`/`vmm_vcenter_password`), never persisted in
    Nautobot, matching the APIC's own `aci_username`/`aci_password`
    handling. `credential_name` only reserves the ACI Credential object's
    own name; it is not a secret."""

    name: str = Field(description="VMM Domain name.")
    controller_name: str = Field(description="VMM Controller name (the ACI-side object name, not the vCenter hostname).")
    host_or_ip: str = Field(description="vCenter hostname or IP address.")
    root_cont_name: str = Field(description="vCenter Datacenter name (ACI's 'top level container name').")
    location: str = Field(default="ACI-Lab", description="Name of the existing Nautobot Location representing the ACI fabric/site.")
    vendor: str = Field(default="VMware", description="VMM provider vendor. This lab only exercises 'VMware'.")
    vlan_pool: str | None = Field(default=None, description="Name of an existing VLAN Pool (in this same Location) to bind this domain to. Omit to leave unbound.")
    credential_name: str | None = Field(default=None, description="Name to give the ACI Credential object for this domain. Omit to leave the domain without a credential relation (no vCenter login will be attempted).")
    dvs_version: str = Field(default="unmanaged", description="Distributed Virtual Switch version. Default 'unmanaged' lets vCenter manage DVS versioning.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)
