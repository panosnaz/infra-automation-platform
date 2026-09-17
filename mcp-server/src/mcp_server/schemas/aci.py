"""ACI-specific per-tool request schemas -- thin argument validation only,
never a cross-domain intent envelope (ADR-018)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

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
    gateway_ip: str | None = Field(
        default=None,
        description="Gateway IP/prefix for the BD subnet, or omit for a BD whose subnet is defined under an EPG.",
    )
    subnet_scope: str = Field(default="private", description="BD subnet scope, typically 'private' or 'shared'.")
    description: str = Field(default="", description="Optional free-text description")
    l3outs: list[str] = Field(
        default_factory=list,
        description=(
            "L3Out names this bridge domain may advertise its subnets through "
            "(fvRsBDToOut). A subnet needs BOTH subnet_scope='public' AND an "
            "L3Out association to be advertised -- neither alone does anything."
        ),
    )

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
    subnet: str | None = Field(default=None, description="Optional EPG subnet gateway, e.g. '10.0.4.254/24'.")
    subnet_scope: str = Field(default="private", description="EPG subnet scope, typically 'private' or 'shared'.")
    provided_contracts: list[str] = Field(default_factory=list)
    consumed_contracts: list[str] = Field(default_factory=list)
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
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the single Location is used automatically -- a Location name is an environment fact and does not belong in a default (this lab's is 'Isolated Lab Site', the upstream lab's is 'ACI-Lab', and a hardcoded default can only ever be right for one of them). Supply it explicitly only when more than one Location exists."
        ),
    )
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
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the single Location is used automatically -- a Location name is an environment fact and does not belong in a default (this lab's is 'Isolated Lab Site', the upstream lab's is 'ACI-Lab', and a hardcoded default can only ever be right for one of them). Supply it explicitly only when more than one Location exists."
        ),
    )
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


class FilterEntrySpec(BaseModel):
    """One vzEntry inside a Filter."""

    name: str = Field(description="Filter entry name.")
    ether_type: str = Field(default="ip", description="Ether type, e.g. 'ip', 'arp', 'unspecified'.")
    ip_protocol: str = Field(default="unspecified", description="IP protocol, e.g. 'tcp', 'udp', 'icmp', 'unspecified'.")
    source_from_port: str | None = Field(default=None, description="Source port range start, e.g. '1024' or 'unspecified'.")
    source_to_port: str | None = Field(default=None, description="Source port range end.")
    dest_from_port: str | None = Field(default=None, description="Destination port range start, e.g. '443' or 'https'.")
    dest_to_port: str | None = Field(default=None, description="Destination port range end.")
    tcp_rules: list[str] | None = Field(default=None, description="TCP flags to match, e.g. ['est'], ['syn','ack'].")
    stateful: bool = Field(default=False, description="Mark the entry stateful (APIC 'stateful=yes').")
    apply_to_fragments: bool = Field(default=False, description="Match IP fragments only (APIC 'applyToFrag=yes').")
    arp_opcode: str | None = Field(default=None, description="ARP opcode when ether_type is 'arp': 'req' or 'reply'.")
    icmpv4_type: str | None = Field(default=None, description="ICMPv4 type, e.g. 'echo', 'echo-rep', 'unspecified'.")
    icmpv6_type: str | None = Field(default=None, description="ICMPv6 type.")
    match_dscp: str | None = Field(default=None, description="DSCP value to match.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateFilterRequest(BaseModel):
    """Standalone Filter creation with full vzEntry attribute depth --
    `create_contract` only ever emits a single 'default' entry."""

    tenant: str = Field(description="Name of the existing Tenant this Filter belongs to.")
    name: str = Field(description="Filter name.")
    entries: list[FilterEntrySpec] = Field(min_length=1, description="One or more filter entries (vzEntry).")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateFilterEntryRequest(BaseModel):
    """Append one vzEntry to a Filter that already exists in the tenant."""

    tenant: str = Field(description="Name of the existing Tenant.")
    filter_name: str = Field(description="Name of the existing Filter to append the entry to.")
    entry: FilterEntrySpec = Field(description="The filter entry to add.")

    @field_validator("filter_name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateContractSubjectRequest(BaseModel):
    """Append a Subject to an existing Contract, binding one or more Filters
    -- `create_contract` only ever creates a single single-filter subject."""

    tenant: str = Field(description="Name of the existing Tenant.")
    contract: str = Field(description="Name of the existing Contract to append the subject to.")
    name: str = Field(description="Subject name.")
    filters: list[str] = Field(min_length=1, description="Names of Filters (in the same tenant) this subject binds.")
    apply_both_directions: bool = Field(default=True, description="Apply the filter chain in both directions.")
    reverse_filter_ports: bool = Field(default=True, description="Reverse source/destination ports on the return direction. Only meaningful when apply_both_directions is true.")
    priority: str | None = Field(default=None, description="QoS priority: 'unspecified', 'level1', 'level2', 'level3'.")
    target_dscp: str | None = Field(default=None, description="Target DSCP marking.")
    description: str = Field(default="", description="Optional free-text description")

    @field_validator("name", "contract")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @field_validator("filters")
    @classmethod
    def _validate_filters(cls, v: list[str]) -> list[str]:
        return [_validate_aci_name(f) for f in v]


class BindEpgContractRequest(BaseModel):
    """Bind an existing Contract to an existing EPG as provider or consumer.
    `create_contract` deliberately does not do this -- the binding lives on
    the EPG's own `aci_epg_contracts` Custom Field, not the Tenant's."""

    tenant: str = Field(description="Name of the existing Tenant.")
    application_profile: str = Field(description="Application Profile the EPG belongs to.")
    epg: str = Field(description="EPG name.")
    contract: str = Field(description="Name of the existing Contract to bind.")
    relation: str = Field(description="Binding direction: 'provided' or 'consumed'.")

    @field_validator("epg", "application_profile", "contract")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @field_validator("relation")
    @classmethod
    def _validate_relation(cls, v: str) -> str:
        if v not in ("provided", "consumed"):
            raise ValueError("relation must be 'provided' or 'consumed'")
        return v


class CreatePodPolicyGroupRequest(BaseModel):
    """ADR-020 Phase E coverage. Pod Policy Groups (fabricPodPGrp) are
    fabric-wide, so they live in the Location's `aci_fabric_policies` JSON
    Custom Field alongside VLAN Pools/AEPs, not on a Tenant."""

    location: str = Field(description="Name of the existing Nautobot Location representing the ACI fabric.")
    name: str = Field(description="Pod Policy Group name, e.g. 'Pod_PG'.")
    bgp_route_reflector_policy: str | None = Field(
        default="default",
        description="Name of the BGP Route Reflector Policy (bgpInstPol) this group resolves. ACI ships exactly one, named 'default'. Pass null to leave it unresolved.",
    )

    @field_validator("name")
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
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the single Location is used automatically -- a Location name is an environment fact and does not belong in a default (this lab's is 'Isolated Lab Site', the upstream lab's is 'ACI-Lab', and a hardcoded default can only ever be right for one of them). Supply it explicitly only when more than one Location exists."
        ),
    )
    alloc_mode: str = Field(default="static", description="Pool allocation mode. Allowed: 'static', 'dynamic'.")
    range_alloc_mode: str | None = Field(default=None, description="Range-level allocation mode override. Allowed: 'static', 'dynamic', 'inherit' (default).")
    role: str = Field(default="external", description="Range role. Allowed: 'external' (used by Physical/L3 Domains), 'internal' (used by VMM Domains).")
    description: str = Field(default="", description="Optional free-text description, only applied when the pool is newly created.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


# Ported from copilot/aci-platform-comparison (2026-09-08) -- genuinely new,
# non-overlapping capability (VRF route leaking has no equivalent on this
# side). FabricPolicyRequest is their shared base class, kept only for the
# subclasses below that still use it (CreateLeafInterfaceProfileRequest,
# CreateInterfaceSelectorRequest) -- their own duplicate CreateVlanPoolRequest/
# CreatePhysicalDomainRequest/CreateAaepRequest/
# CreateLeafInterfacePolicyGroupRequest subclasses were NOT ported: this
# side's own versions of those four are already live-verified (including
# over the real MCP protocol) and are the canonical implementation.
class CreateVrfRouteLeakRequest(BaseModel):
    """Create a route-leak intent entry from one existing Tenant VRF to
    another. The provider applies the leaked subnet under destination_vrf."""

    tenant: str = Field(description="Name of the existing Tenant owning both VRFs.")
    name: str = Field(description="Unique route-leak intent name.")
    source_vrf: str = Field(description="Existing source VRF name.")
    destination_vrf: str = Field(description="Existing destination VRF name.")
    subnet: str = Field(description="Subnet to leak, for example 10.10.10.0/24.")
    allow_l3out_advertisement: bool = Field(default=False, description="Allow the leaked route to be advertised through an L3Out.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name", "source_vrf", "destination_vrf")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _validate_distinct_vrfs(self):
        if self.source_vrf == self.destination_vrf:
            raise ValueError("source_vrf and destination_vrf must be different")
        return self


class FabricPolicyRequest(BaseModel):
    location: str = Field(description="ACI fabric Location whose JSON custom field is updated.")
    name: str = Field(description="Object name.")

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
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the single Location is used automatically -- a Location name is an environment fact and does not belong in a default (this lab's is 'Isolated Lab Site', the upstream lab's is 'ACI-Lab', and a hardcoded default can only ever be right for one of them). Supply it explicitly only when more than one Location exists."
        ),
    )
    vlan_pool: str | None = Field(default=None, description="Name of an existing VLAN Pool (in this same Location) to bind this domain to. Omit to leave unbound.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


# Ported from copilot/aci-platform-comparison (2026-09-08). Not ported:
# BindEpgToPhysicalDomainRequest/BindEpgToVmmDomainRequest -- superseded by
# this side's own consolidated bind_epg_domain (aci_epg_domains Custom
# Field), which the generator/Terraform actually support (see
# transformer.py's _build_application_profiles() comment).
class CreateLeafInterfaceProfileRequest(FabricPolicyRequest):
    node_id: int = Field(ge=1)
    pod_id: int = Field(default=1, ge=1)
    description: str = Field(default="", description="Optional description.")


class CreateFabricDeviceRequest(BaseModel):
    """A leaf or spine switch in the ACI fabric, modeled as a Nautobot DCIM
    Device. This is the authoritative inventory the generator resolves every
    `topology/pod-<pod_id>/paths-<node_id>/...` DN against -- see
    ADR-020's fabric-inventory section.

    `pod_id` is a real part of every path DN, so it belongs here rather than
    being assumed: the `aci_pod_id` Custom Field existed in Nautobot from the
    start but no tool could write it until 2026-09-14, which meant a
    multi-pod fabric could not be modeled at all. Defaulted to 1 because
    this lab has a single pod and every existing device is in it.
    """

    name: str
    node_id: int = Field(ge=1, le=4000, description="ACI fabric node ID. Leaves and spines share one 1-4000 range.")
    serial: str = Field(default="", description="Switch serial number -- the key APIC fabric membership is registered against.")
    role: str = Field(default="leaf", description="Fabric role: 'leaf' or 'spine'.")
    pod_id: int = Field(default=1, ge=1, description="ACI pod ID; part of every topology/pod-N/... DN.")
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the "
            "single Location is used automatically. This field carried a third, "
            "different hardcoded default until 2026-09-17."
        ),
    )
    model: str = "Nexus 9000v"
    description: str = ""

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: str) -> str:
        if v not in ("leaf", "spine"):
            raise ValueError("role must be 'leaf' or 'spine'")
        return v


class CreateFabricInterfaceRequest(BaseModel):
    device: str
    name: str
    description: str = ""
    enabled: bool = True


class CreateInterfaceSelectorRequest(FabricPolicyRequest):
    leaf_interface_profile: str
    policy_group: str
    module: int = Field(ge=1)
    port: int = Field(ge=1)


class CreateAccessPortProfileRequest(FabricPolicyRequest):
    description: str = ""


class CreateAccessPortSelectorRequest(FabricPolicyRequest):
    access_port_profile: str
    policy_group: str
    selector_type: str = "range"


class CreateAccessPortBlockRequest(BaseModel):
    location: str
    access_port_profile: str
    selector: str
    name: str
    from_card: int = Field(ge=1)
    from_port: int = Field(ge=1)
    to_card: int | None = Field(default=None, ge=1)
    to_port: int | None = Field(default=None, ge=1)


class CreateLeafProfileRequest(FabricPolicyRequest):
    access_port_profiles: list[str] = Field(default_factory=list)
    description: str = ""


class CreateLeafSelectorRequest(BaseModel):
    location: str
    leaf_profile: str
    name: str
    selector_type: str = "range"


class CreateLeafNodeBlockRequest(BaseModel):
    location: str
    leaf_profile: str
    selector: str
    name: str
    from_node: int = Field(ge=1)
    to_node: int | None = Field(default=None, ge=1)


class CreateStaticPathBindingRequest(BaseModel):
    tenant: str
    application_profile: str
    epg: str
    node_id: int = Field(ge=1)
    module: int = Field(ge=1)
    port: int = Field(ge=1)
    encap: str
    pod_id: int = Field(default=1, ge=1)
    mode: str = Field(default="regular")


class CreateProtocolL3OutRequest(BaseModel):
    tenant: str
    name: str
    vrf: str
    domain: str
    description: str = ""
    external_epgs: list[dict] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateL3OutNodeProfileRequest(BaseModel):
    tenant: str
    l3out: str
    name: str
    nodes: list[dict] = Field(default_factory=list)


class CreateL3OutInterfaceProfileRequest(BaseModel):
    tenant: str
    l3out: str
    node_profile: str
    name: str
    interfaces: list[dict] = Field(default_factory=list)


class CreateNdInterfacePolicyRequest(BaseModel):
    """Create an IPv6 Neighbour Discovery interface policy (``ndIfPol``) in a
    tenant, ready to be bound to an L3Out Logical Interface Profile.

    Every attribute is optional apart from the name: APIC supplies its own
    default for each, and this schema deliberately does not re-declare those
    defaults -- an omitted field means "leave it to APIC", not "set it to
    what we think APIC uses".
    """

    tenant: str = Field(description="Name of the existing Tenant that owns this policy.")
    name: str = Field(description="ND interface policy name.")
    hop_limit: int | None = Field(default=None, ge=0, le=255, description="IPv6 hop limit advertised in router advertisements.")
    mtu: int | None = Field(default=None, ge=1280, le=9216, description="MTU advertised in router advertisements. IPv6 minimum is 1280.")
    retransmit_timer: int | None = Field(default=None, ge=0, description="Neighbour-solicitation retransmit timer, milliseconds.")
    reachable_time: int | None = Field(default=None, ge=0, description="How long a neighbour stays reachable after a reachability confirmation, milliseconds.")
    neighbor_solicitation_interval: int | None = Field(default=None, ge=0, description="Interval between neighbour solicitations, milliseconds.")
    neighbor_solicitation_retries: int | None = Field(default=None, ge=0, description="How many neighbour solicitations before declaring unreachable.")
    nud_retry_base: int | None = Field(default=None, ge=0, description="Neighbour Unreachability Detection retry base.")
    nud_retry_interval: int | None = Field(default=None, ge=0, description="Neighbour Unreachability Detection retry interval.")
    nud_retry_max_attempts: int | None = Field(default=None, ge=0, description="Neighbour Unreachability Detection maximum retry attempts.")
    router_advertisement_interval: int | None = Field(default=None, ge=0, description="Interval between router advertisements, seconds.")
    router_advertisement_lifetime: int | None = Field(default=None, ge=0, description="Router lifetime advertised in router advertisements, seconds.")
    controller_state: str | None = Field(default=None, description="ND controller state flags, for example 'managed-cfg' or 'other-cfg'.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateDppPolicyRequest(BaseModel):
    """Create a Data Plane Policing policy (``qosDppPol``) in a tenant.

    One policy object serves both directions -- ACI has no separate ingress
    and egress policer type. Direction is decided by WHICH relation an
    interface profile binds it to (`ingress_dpp_policy` vs
    `egress_dpp_policy`), so the same policy can legitimately be used for
    both.

    `rate` and `burst` carry their units in SEPARATE fields in this provider
    (`rate_unit`/`burst_unit`), not as a suffix on the value.
    """

    tenant: str = Field(description="Name of the existing Tenant that owns this policy.")
    name: str = Field(description="Data plane policing policy name.")
    rate: int | None = Field(default=None, ge=0, description="Committed information rate, in rate_unit.")
    rate_unit: str | None = Field(default=None, description="Unit for rate, for example 'kilo', 'mega', 'giga', or 'pps' when mode is packet.")
    burst: int | None = Field(default=None, ge=0, description="Committed burst size, in burst_unit.")
    burst_unit: str | None = Field(default=None, description="Unit for burst, for example 'kilo', 'mega', 'giga'.")
    peak_rate: int | None = Field(default=None, ge=0, description="Peak information rate, used by two-rate (2R3C) policers.")
    peak_rate_unit: str | None = Field(default=None, description="Unit for peak_rate.")
    excessive_burst: int | None = Field(default=None, ge=0, description="Excessive burst size, used by two-rate (2R3C) policers.")
    excessive_burst_unit: str | None = Field(default=None, description="Unit for excessive_burst.")
    admin_state: str | None = Field(default=None, description="'enabled' or 'disabled'.")
    type: str | None = Field(default=None, description="Policer type: '1R2C' (single rate, two colour) or '2R3C' (two rate, three colour).")
    mode: str | None = Field(default=None, description="Policing mode: 'bit' (bandwidth) or 'packet' (packets per second).")
    sharing_mode: str | None = Field(default=None, description="How the policer is shared across interfaces, for example 'dedicated' or 'shared'.")
    conform_action: str | None = Field(default=None, description="Action for conforming traffic: 'transmit', 'drop', or 'mark'.")
    conform_mark_cos: str | None = Field(default=None, description="CoS value to mark conforming traffic with, when conform_action is 'mark'.")
    conform_mark_dscp: str | None = Field(default=None, description="DSCP value to mark conforming traffic with, when conform_action is 'mark'.")
    exceed_action: str | None = Field(default=None, description="Action for traffic exceeding the committed rate.")
    exceed_mark_cos: str | None = Field(default=None, description="CoS value to mark exceeding traffic with.")
    exceed_mark_dscp: str | None = Field(default=None, description="DSCP value to mark exceeding traffic with.")
    violate_action: str | None = Field(default=None, description="Action for traffic violating the peak rate.")
    violate_mark_cos: str | None = Field(default=None, description="CoS value to mark violating traffic with.")
    violate_mark_dscp: str | None = Field(default=None, description="DSCP value to mark violating traffic with.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _rate_and_unit_travel_together(self):
        """A bare number is meaningless -- `rate: 100` could be 100 bps or
        100 Gbps. APIC silently applies its own default unit, which is not
        what a caller specifying a rate intends."""
        for value_field, unit_field in (
            ("rate", "rate_unit"),
            ("burst", "burst_unit"),
            ("peak_rate", "peak_rate_unit"),
            ("excessive_burst", "excessive_burst_unit"),
        ):
            if getattr(self, value_field) is not None and not getattr(self, unit_field):
                raise ValueError(
                    f"{unit_field} is required when {value_field} is set -- a rate "
                    "without a unit is ambiguous and APIC would silently apply its "
                    "own default"
                )
        return self


class CreatePimInterfacePolicyRequest(BaseModel):
    """Create a PIM interface policy (``pimIfPol``) in a tenant.

    The same policy object serves IPv4 and IPv6; which one it configures is
    decided by the relation an interface profile binds it to
    (`pim_interface_policy` vs `pim_v6_interface_policy`).

    **No authentication key field, deliberately.** `pimIfPol` supports an
    auth key, but a shared secret must never be persisted in Nautobot or in
    the committed NetAsCode YAML -- the same rule that keeps OSPF MD5 keys
    out of CreateOspfInterfacePolicyRequest. Set `auth_type` here and supply
    the key itself as a sensitive Terraform variable.
    """

    tenant: str = Field(description="Name of the existing Tenant that owns this policy.")
    name: str = Field(description="PIM interface policy name.")
    designated_router_priority: int | None = Field(default=None, ge=0, description="DR priority; the highest priority on a segment becomes the designated router.")
    designated_router_delay: int | None = Field(default=None, ge=0, description="DR election delay, seconds.")
    hello_interval: int | None = Field(default=None, ge=0, description="PIM hello interval, milliseconds.")
    join_prune_interval: int | None = Field(default=None, ge=0, description="Join/prune interval, seconds.")
    control_state: str | None = Field(default=None, description="PIM control flags, for example 'border' or 'passive'.")
    auth_type: str | None = Field(default=None, description="Neighbour authentication type, for example 'none' or 'ah-md5'. The key itself is supplied as a sensitive Terraform variable, never here.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateIgmpInterfacePolicyRequest(BaseModel):
    """Create an IGMP interface policy (``igmpIfPol``) in a tenant."""

    tenant: str = Field(description="Name of the existing Tenant that owns this policy.")
    name: str = Field(description="IGMP interface policy name.")
    version: str | None = Field(default=None, description="IGMP version, 'v2' or 'v3'.")
    query_interval: int | None = Field(default=None, ge=0, description="General query interval, seconds.")
    response_interval: int | None = Field(default=None, ge=0, description="Maximum query response interval, seconds.")
    group_timeout: int | None = Field(default=None, ge=0, description="Group membership timeout, seconds.")
    querier_timeout: int | None = Field(default=None, ge=0, description="Other-querier-present timeout, seconds.")
    last_member_count: int | None = Field(default=None, ge=0, description="Last member query count.")
    last_member_response_time: int | None = Field(default=None, ge=0, description="Last member query response time, seconds.")
    robustness_variable: int | None = Field(default=None, ge=0, description="IGMP robustness variable; raise it on lossy links.")
    startup_query_count: int | None = Field(default=None, ge=0, description="Number of queries sent at startup.")
    startup_query_interval: int | None = Field(default=None, ge=0, description="Interval between startup queries, seconds.")
    control: str | None = Field(default=None, description="IGMP control flags, for example 'allow-v3-asm' or 'fast-leave'.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateCustomQosPolicyRequest(BaseModel):
    """Create a Custom QoS policy (``qosCustomPol``) in a tenant.

    Both map lists are passed through to the provider unchanged. Each entry
    maps an incoming range to an ACI QoS level: DSCP maps carry
    from/to/priority/target/target_cos, dot1p maps the same over CoS values.
    """

    tenant: str = Field(description="Name of the existing Tenant that owns this policy.")
    name: str = Field(description="Custom QoS policy name.")
    dscp_to_priority_maps: list[dict] = Field(
        default_factory=list,
        description="DSCP-to-priority mappings, each with from/to/priority and optionally target/target_cos.",
    )
    dot1p_classifiers: list[dict] = Field(
        default_factory=list,
        description="Dot1p-to-priority mappings, same shape as dscp_to_priority_maps but over CoS values.",
    )
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _at_least_one_mapping(self):
        if not self.dscp_to_priority_maps and not self.dot1p_classifiers:
            raise ValueError(
                "a custom QoS policy with no dscp_to_priority_maps and no "
                "dot1p_classifiers classifies nothing -- supply at least one"
            )
        return self


class BindL3OutInterfaceProfilePoliciesRequest(BaseModel):
    """Bind policies to an EXISTING L3Out Logical Interface Profile, and/or
    set its QoS priority.

    Separate from create_l3out_interface_profile because attaching policy to
    an already-deployed profile is a normal day-2 operation, the same reason
    bind_epg_domain is separate from create_epg.

    **Omitting a field leaves it untouched; it does not clear it.** To
    inherit APIC's built-in default you must never have set the field --
    passing the literal string 'default' is NOT valid and fails at apply time
    with "Relation target dn default not found" (measured 2026-09-16).

    Every policy named here must already exist in the same tenant, or be a
    full ``uni/...`` DN for a policy this platform does not manage. The
    generator re-checks this and fails the pipeline on a dangling reference,
    because the provider only validates it at apply time.
    """

    tenant: str = Field(description="Name of the existing Tenant.")
    l3out: str = Field(description="Name of the existing L3Out.")
    node_profile: str = Field(description="Name of the existing Logical Node Profile.")
    interface_profile: str = Field(description="Name of the existing Logical Interface Profile to bind policies to.")
    qos_priority: str | None = Field(default=None, description="QoS class for traffic on this profile, for example 'level1'..'level6' or 'unspecified'.")
    nd_interface_policy: str | None = Field(default=None, description="Name of an ND interface policy in this tenant.")
    ingress_dpp_policy: str | None = Field(default=None, description="Name of a Data Plane Policing policy in this tenant, applied to ingress traffic.")
    egress_dpp_policy: str | None = Field(default=None, description="Name of a Data Plane Policing policy in this tenant, applied to egress traffic.")
    pim_interface_policy: str | None = Field(default=None, description="Name of a PIM interface policy in this tenant, for IPv4.")
    pim_v6_interface_policy: str | None = Field(default=None, description="Name of a PIM interface policy in this tenant, for IPv6.")
    igmp_interface_policy: str | None = Field(default=None, description="Name of an IGMP interface policy in this tenant.")
    custom_qos_policy: str | None = Field(default=None, description="Name of a Custom QoS policy in this tenant.")

    @model_validator(mode="after")
    def _something_to_bind(self):
        bindings = {
            k: v for k, v in self.model_dump().items()
            if k not in ("tenant", "l3out", "node_profile", "interface_profile") and v
        }
        if not bindings:
            raise ValueError(
                "nothing to bind -- supply at least one policy or qos_priority. "
                "Note that omitting a field leaves it unchanged rather than "
                "clearing it."
            )
        return self

    @model_validator(mode="after")
    def _reject_the_default_literal(self):
        """`default` looks like it should select APIC's built-in policy and
        does not: the provider resolves the name inside the owning tenant and
        fails the apply with "Relation target dn default not found". The
        correct way to get the default is to omit the field."""
        offenders = sorted(
            field for field in (
                "nd_interface_policy", "ingress_dpp_policy", "egress_dpp_policy",
                "pim_interface_policy", "pim_v6_interface_policy",
                "igmp_interface_policy", "custom_qos_policy",
            )
            if getattr(self, field) == "default"
        )
        if offenders:
            raise ValueError(
                f"{', '.join(offenders)} set to the literal 'default', which APIC "
                "rejects at apply time ('Relation target dn default not found'). "
                "To inherit the built-in default, omit the field entirely."
            )
        return self


class MatchPrefixSpec(BaseModel):
    """One prefix inside a route-map match rule (``rtctrlMatchRtDest``)."""

    ip: str = Field(description="Prefix to match, e.g. '172.16.200.200/32' or '10.0.3.0/24'.")
    aggregate: bool = Field(
        default=False,
        description=(
            "APIC's Aggregate checkbox. Matches the prefix AND anything more "
            "specific within it. Leave off to match the exact prefix only."
        ),
    )
    greater_than_mask: int = Field(
        default=0, ge=0, le=128,
        description="Prefix-list 'ge' bound. 0 means unset, matching the exact prefix length.",
    )
    less_than_mask: int = Field(
        default=0, ge=0, le=128,
        description="Prefix-list 'le' bound. 0 means unset.",
    )
    description: str = Field(default="", description="Optional free-text description.")

    @model_validator(mode="after")
    def _mask_bounds_are_ordered(self):
        if self.greater_than_mask and self.less_than_mask and self.greater_than_mask > self.less_than_mask:
            raise ValueError(
                f"greater_than_mask ({self.greater_than_mask}) is above less_than_mask "
                f"({self.less_than_mask}) for {self.ip} -- that range can never match"
            )
        return self


class SetExternalEpgSubnetScopeRequest(BaseModel):
    """Replace the route-control/security scope flags on an EXISTING external
    EPG subnet.

    Exists because scope is the switch between the two ways ACI can control
    what an L3Out advertises: per-subnet ``export-rtctrl`` flags, or a route
    map. Moving from one to the other means rewriting an existing subnet's
    scope, not creating anything.

    The scope list REPLACES what is there -- it is not merged. An empty list
    is refused: ACI rejects a subnet with no scope at all.
    """

    tenant: str = Field(description="Name of the existing Tenant.")
    l3out: str = Field(description="Name of the existing L3Out.")
    external_epg: str = Field(description="Name of the existing external EPG.")
    ip: str = Field(description="The existing subnet to modify, e.g. '172.16.200.200/32'.")
    scope: list[str] = Field(
        description=(
            "Replacement scope flags. Valid values: import-security "
            "(External Subnets for the External EPG), export-rtctrl, "
            "import-rtctrl, shared-rtctrl, shared-security."
        )
    )

    _VALID = {"import-security", "export-rtctrl", "import-rtctrl",
              "shared-rtctrl", "shared-security"}

    @model_validator(mode="after")
    def _scope_is_present_and_valid(self):
        if not self.scope:
            raise ValueError(
                "scope cannot be empty -- ACI rejects an external EPG subnet with "
                "no scope flags. To remove a subnet entirely, delete it rather "
                "than clearing its scope."
            )
        unknown = sorted(set(self.scope) - self._VALID)
        if unknown:
            raise ValueError(
                f"unknown scope value(s): {', '.join(unknown)}. Valid: "
                f"{', '.join(sorted(self._VALID))}"
            )
        return self


class BindExternalEpgContractRequest(BaseModel):
    """Provide or consume a Contract on an L3Out's external EPG.

    Separate from bind_epg_contract because an external EPG (``l3extInstP``)
    is a different object from an application EPG and lives inside the
    L3Out's own intent, not on a VLAN.
    """

    tenant: str = Field(description="Name of the existing Tenant.")
    l3out: str = Field(description="Name of the existing L3Out.")
    external_epg: str = Field(description="Name of the existing external EPG.")
    provided_contracts: list[str] = Field(
        default_factory=list, description="Contract names this external EPG provides."
    )
    consumed_contracts: list[str] = Field(
        default_factory=list, description="Contract names this external EPG consumes."
    )

    @model_validator(mode="after")
    def _something_to_bind(self):
        if not self.provided_contracts and not self.consumed_contracts:
            raise ValueError(
                "supply at least one provided or consumed contract -- binding "
                "neither does nothing"
            )
        return self


class AddExternalEpgSubnetRequest(BaseModel):
    """Add a subnet to an EXISTING external EPG.

    Distinct from set_external_epg_subnet_scope, which edits one already
    present. Scope decides what the subnet is FOR: ``import-security``
    classifies traffic into this EPG for contracts, the ``rtctrl`` flags
    control routing.
    """

    tenant: str = Field(description="Name of the existing Tenant.")
    l3out: str = Field(description="Name of the existing L3Out.")
    external_epg: str = Field(description="Name of the existing external EPG.")
    ip: str = Field(description="Subnet to add, e.g. '172.16.199.199/32'.")
    scope: list[str] = Field(
        default_factory=lambda: ["import-security"],
        description=(
            "Scope flags. Default ['import-security'] = External Subnets for "
            "the External EPG, the classification used by contracts."
        ),
    )
    aggregate: list[str] = Field(default_factory=list, description="Optional aggregate flags, e.g. ['shared-rtctrl'].")

    _VALID = {"import-security", "export-rtctrl", "import-rtctrl",
              "shared-rtctrl", "shared-security"}

    @model_validator(mode="after")
    def _scope_is_valid(self):
        if not self.scope:
            raise ValueError("scope cannot be empty -- ACI rejects a subnet with no scope flags")
        unknown = sorted(set(self.scope) - self._VALID)
        if unknown:
            raise ValueError(f"unknown scope value(s): {', '.join(unknown)}")
        return self


class AddMatchRulePrefixRequest(BaseModel):
    """Add a prefix to an EXISTING route-map match rule.

    Route maps are edited far more often than created -- adding a prefix to
    a deny rule is the normal way to extend a filter.
    """

    tenant: str = Field(description="Name of the existing Tenant.")
    match_rule: str = Field(description="Name of the existing match rule.")
    ip: str = Field(description="Prefix to add, e.g. '172.16.199.199/32'.")
    aggregate: bool = Field(default=False, description="APIC's Aggregate checkbox.")
    greater_than_mask: int = Field(default=0, ge=0, le=128, description="Prefix-list 'ge' bound; 0 = unset.")
    less_than_mask: int = Field(default=0, ge=0, le=128, description="Prefix-list 'le' bound; 0 = unset.")
    description: str = Field(default="", description="Optional free-text description.")


class CreateL3DomainRequest(BaseModel):
    """Create an external routed (L3) domain, optionally bound to a VLAN pool.

    An L3Out's encap VLAN must come from the pool bound to its L3 domain. A
    domain with no pool leaves every L3Out encap outside any pool, which is
    invalid on real hardware even though this simulator accepts it.
    """

    name: str = Field(description="L3 domain name, e.g. 'ExtL3Dom'.")
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the single Location is used automatically -- a Location name is an environment fact and does not belong in a default (this lab's is 'Isolated Lab Site', the upstream lab's is 'ACI-Lab', and a hardcoded default can only ever be right for one of them). Supply it explicitly only when more than one Location exists."
        ),
    )
    vlan_pool: str | None = Field(default=None, description="Name of an existing VLAN pool covering the L3Out encap VLANs.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateMatchRuleRequest(BaseModel):
    """Create a route-map match rule (``rtctrlSubjP``) in a tenant.

    Tenant-scoped, not L3Out-scoped, so one rule can be referenced by several
    route maps. A route-map context then names it.
    """

    tenant: str = Field(description="Name of the existing Tenant that owns this match rule.")
    name: str = Field(description="Match rule name, e.g. 'match-permit-prefix-out'.")
    prefixes: list[MatchPrefixSpec] = Field(description="Prefixes this rule matches.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _at_least_one_prefix(self):
        if not self.prefixes:
            raise ValueError(
                "a match rule with no prefixes matches nothing. In a route map, "
                "whose last word is an implicit deny, that silently drops every "
                "route instead of failing"
            )
        return self


class RouteControlContextSpec(BaseModel):
    """One ordered permit/deny entry inside a route map (``rtctrlCtxP``)."""

    name: str = Field(description="Context name, e.g. 'permit-explicit'.")
    order: int = Field(default=0, ge=0, le=9, description="Evaluation order, lowest first. ACI allows 0-9.")
    action: str = Field(default="permit", description="'permit' or 'deny'.")
    match_rule: str | None = Field(
        default=None,
        description=(
            "Name of a match rule in the same tenant. Omit for a context that "
            "matches everything -- which as a final 'deny' is how you make the "
            "implicit deny explicit."
        ),
    )
    set_rule: str | None = Field(default=None, description="Optional action/set rule profile name to apply to matched routes.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @field_validator("action")
    @classmethod
    def _validate_action(cls, v: str) -> str:
        if v.lower() not in ("permit", "deny"):
            raise ValueError(f"action must be 'permit' or 'deny', got '{v}'")
        return v.lower()


class CreateRouteControlProfileRequest(BaseModel):
    """Create a route map (``rtctrlProfile``) under an existing L3Out, with
    its ordered permit/deny contexts.

    **An ACI route map ends in an implicit deny.** Anything no context
    permits is dropped. That is what makes a route map a complete replacement
    for per-subnet "Export Route Control Subnet" flags: permit what should be
    advertised and everything else stops, without listing it.

    **A custom-named profile does nothing until something references it.**
    Only the reserved names `default-export` and `default-import` apply to an
    L3Out automatically. For any other name, bind it to an external EPG with
    bind_external_epg_route_control_profile, or the map is inert.
    """

    tenant: str = Field(description="Name of the existing Tenant.")
    l3out: str = Field(description="Name of the existing L3Out this route map belongs to.")
    name: str = Field(description="Route map name, e.g. 'Uni-Route-Profile-OUT', or the reserved 'default-export'.")
    contexts: list[RouteControlContextSpec] = Field(description="Ordered permit/deny entries.")
    type: str = Field(
        default="global",
        description=(
            "'global' = Match Routing Policy Only (the map alone decides). "
            "'combinable' = Match Prefix AND Routing Policy (the map is ANDed "
            "with the external EPG's subnet flags)."
        ),
    )
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name", "l3out")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in ("global", "combinable"):
            raise ValueError(f"type must be 'global' or 'combinable', got '{v}'")
        return v

    @model_validator(mode="after")
    def _contexts_are_present_ordered_and_unique(self):
        if not self.contexts:
            raise ValueError(
                "a route map with no contexts permits nothing, and ACI's implicit "
                "deny then drops every route -- supply at least one context"
            )
        names = [c.name for c in self.contexts]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"duplicate context name(s): {', '.join(duplicates)}")
        orders = [c.order for c in self.contexts]
        repeated = sorted({o for o in orders if orders.count(o) > 1})
        if repeated:
            raise ValueError(
                f"context order value(s) {repeated} used more than once -- evaluation "
                "order would be undefined, and in a permit/deny list order is the "
                "whole meaning"
            )
        return self


class BindExternalEpgRouteControlProfileRequest(BaseModel):
    """Bind an existing route map to an external EPG for one direction
    (``l3extRsInstPToProfile``).

    Needed because a custom-named route map is inert on its own -- only
    `default-export`/`default-import` apply to an L3Out without a reference.
    """

    tenant: str = Field(description="Name of the existing Tenant.")
    l3out: str = Field(description="Name of the existing L3Out.")
    external_epg: str = Field(description="Name of the existing external EPG to bind the route map to.")
    route_control_profile: str = Field(description="Name of a route map declared in the same L3Out.")
    direction: str = Field(default="export", description="'export' (advertised out of the fabric) or 'import'.")

    @field_validator("direction")
    @classmethod
    def _validate_direction(cls, v: str) -> str:
        if v not in ("export", "import"):
            raise ValueError(f"direction must be 'export' or 'import', got '{v}'")
        return v


class CreateL3OutInterfaceRequest(BaseModel):
    tenant: str
    l3out: str
    node_profile: str
    interface_profile: str
    node_id: int = Field(ge=1)
    module: int = Field(ge=1)
    port: int = Field(ge=1)
    pod_id: int = Field(default=1, ge=1)
    ip: str | None = None
    svi: bool = False
    vlan: int | None = Field(default=None, ge=1, le=4094)
    mode: str = "regular"
    mtu: str = "inherit"


class CreateBgpPeerRequest(BaseModel):
    tenant: str
    l3out: str
    node_profile: str
    interface_profile: str
    interface_key: str
    ip: str
    remote_as: int = Field(ge=1)
    local_as: int = Field(ge=1)
    admin_state: bool = True
    ttl: int = Field(default=1, ge=1)
    weight: int = Field(default=0, ge=0)
    allowed_self_as_count: int = Field(default=0, ge=0)


class CreateOspfInterfaceRequest(BaseModel):
    tenant: str
    l3out: str
    interface_key: str
    name: str = "ospf"
    policy: str | None = None
    area: str = "0.0.0.0"
    area_type: str = "regular"


class CreateOspfInterfacePolicyRequest(BaseModel):
    tenant: str
    name: str
    network_type: str = Field(default="broadcast", description="OSPF network type: broadcast or point-to-point.")
    hello_interval: int = Field(default=10, ge=1)
    dead_interval: int = Field(default=40, ge=1)
    passive: bool = False
    authentication_type: str | None = Field(default=None, description="Authentication type: md5, simple, keychain, or unset.")
    authentication_secret_ref: str | None = Field(default=None, description="Non-secret Vault/secret reference name for the authentication value.")
    authentication_key_id: int | None = Field(default=None, ge=0)
    cost: int | None = Field(default=None, ge=1)
    priority: int | None = Field(default=None, ge=0)
    description: str = ""


class AepDomainSpec(BaseModel):
    """One domain fronted by an AAEP. `type` decides which APIC object the
    relation resolves against -- a physical domain and an L3 domain can share
    a name, so it cannot be inferred."""

    name: str = Field(description="Domain name.")
    type: str = Field(default="physical", description="'physical' or 'l3'.")

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in ("physical", "l3"):
            raise ValueError(f"domain type must be 'physical' or 'l3', got '{v}'")
        return v


class CreateAepRequest(BaseModel):
    """ADR-020 Phase B coverage: an Attachable Access Entity Profile (AEP),
    bound to zero or more existing Physical Domains."""

    name: str = Field(description="AEP name.")
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the single Location is used automatically -- a Location name is an environment fact and does not belong in a default (this lab's is 'Isolated Lab Site', the upstream lab's is 'ACI-Lab', and a hardcoded default can only ever be right for one of them). Supply it explicitly only when more than one Location exists."
        ),
    )
    domains: list[str | AepDomainSpec] = Field(
        default_factory=list,
        description=(
            "Domains this AAEP fronts. A bare string is a PHYSICAL domain "
            "(kept for backwards compatibility); use {'name': ..., 'type': "
            "'l3'} for an external routed domain, which is what an L3Out's "
            "interface attaches through."
        ),
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateLeafInterfacePolicyGroupRequest(BaseModel):
    """ADR-020 Phase B coverage. Logical-only: models the policy group
    object and its AEP relation, no physical leaf/port selector binding
    (same simulator limitation as CreatePhysicalDomainRequest)."""

    name: str = Field(description="Leaf Interface Policy Group name.")
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the single Location is used automatically -- a Location name is an environment fact and does not belong in a default (this lab's is 'Isolated Lab Site', the upstream lab's is 'ACI-Lab', and a hardcoded default can only ever be right for one of them). Supply it explicitly only when more than one Location exists."
        ),
    )
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
    controller_name: str | None = Field(default=None, description="VMM Controller name (the ACI-side object name, not the vCenter hostname). Omit -- along with host_or_ip and root_cont_name -- to create a domain with NO controller, which never contacts vCenter at all.")
    host_or_ip: str | None = Field(default=None, description="vCenter hostname or IP address. Required only when creating a controller.")
    root_cont_name: str | None = Field(default=None, description="vCenter Datacenter name (ACI's 'top level container name'). Required only when creating a controller.")
    location: str | None = Field(
        default=None,
        description=(
            "Nautobot Location holding this fabric's intent. Omit it and the single Location is used automatically -- a Location name is an environment fact and does not belong in a default (this lab's is 'Isolated Lab Site', the upstream lab's is 'ACI-Lab', and a hardcoded default can only ever be right for one of them). Supply it explicitly only when more than one Location exists."
        ),
    )
    vendor: str = Field(default="VMware", description="VMM provider vendor. This lab only exercises 'VMware'.")
    vlan_pool: str | None = Field(default=None, description="Name of an existing VLAN Pool (in this same Location) to bind this domain to. Omit to leave unbound.")
    credential_name: str | None = Field(default=None, description="Name to give the ACI Credential object for this domain. Omit to leave the domain without a credential relation (no vCenter login will be attempted).")
    dvs_version: str = Field(default="unmanaged", description="Distributed Virtual Switch version. Default 'unmanaged' lets vCenter manage DVS versioning.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _controller_is_all_or_nothing(self):
        """A VMM Domain may legitimately exist with no Controller.

        The Controller is the only object in this chain that actually
        reaches out to vCenter -- APIC connects, authenticates, and builds a
        Distributed Virtual Switch there. A domain on its own is inert: it
        gives EPGs and L4-L7 devices something to bind to without touching
        the virtualisation environment at all. That is the right shape when
        modelling a VMM-backed service device on a fabric whose vCenter is
        unreachable, or when you deliberately do not want a DVS created yet.

        A PARTIAL controller is always a mistake, though -- ACI needs the
        name, host and datacenter together -- so require all three or none.
        """
        controller_fields = {
            "controller_name": self.controller_name,
            "host_or_ip": self.host_or_ip,
            "root_cont_name": self.root_cont_name,
        }
        supplied = {k: v for k, v in controller_fields.items() if v}
        if supplied and len(supplied) != len(controller_fields):
            missing = sorted(set(controller_fields) - set(supplied))
            raise ValueError(
                "a VMM Controller needs controller_name, host_or_ip and root_cont_name "
                f"together -- missing {missing}. Omit all three to create a domain with "
                "no controller (nothing will contact vCenter)."
            )
        if self.credential_name and not supplied:
            raise ValueError(
                "credential_name is meaningless without a controller -- the credential "
                "exists to authenticate the controller's vCenter connection"
            )
        return self


# Ported from copilot/aci-platform-comparison (2026-09-08) -- genuinely new,
# non-overlapping L4-L7/PBR/Service Graph capability.
class CreateL4L7DeviceRequest(BaseModel):
    """Create a logical ACI L4-L7 device. Concrete vCenter VM discovery
    and credentials are deliberately out of scope for this intent model."""

    tenant: str = Field(description="Name of the existing Tenant that owns this L4-L7 device.")
    name: str = Field(description="Logical L4-L7 device name.")
    consumer_interface: str = Field(description="Logical interface name on the consumer side.")
    provider_interface: str | None = Field(default=None, description="Optional provider-side logical interface. Omit for a one-arm device.")
    service_type: str = Field(default="FW", description="ACI service type, for example FW or ADC.")
    device_type: str = Field(default="VIRTUAL", description="ACI device type, for example VIRTUAL or PHYSICAL.")
    function_type: str = Field(default="GoTo", description="ACI device function type, for example GoTo or GoThrough.")
    managed: bool = Field(default=False, description="Whether APIC manages the service device.")
    context_aware: str = Field(default="single-Context", description="ACI context-awareness mode.")
    vmm_domain: str | None = Field(default=None, description="Existing VMM Domain name. Required when device_type is VIRTUAL.")
    physical_domain: str | None = Field(default=None, description="Existing Physical Domain name. Required when device_type is PHYSICAL -- the provider makes the physDomP relation mandatory for a physical service device.")
    trunking: bool = Field(default=False, description="Trunking port mode on the service device interfaces (vnsLDevVip.trunking).")
    promiscuous_mode: bool = Field(default=False, description="Promiscuous mode -- normally required for a virtual firewall/ADC on a VMM domain to see traffic not addressed to its own MAC (vnsLDevVip.promMode).")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name", "consumer_interface", "provider_interface")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        return _validate_aci_name(v) if v is not None else v

    @model_validator(mode="after")
    def _trunking_is_virtual_only(self):
        """Trunking is a VMM port-group option and is invalid on a PHYSICAL
        device.

        APIC accepts the combination and then marks the device invalid, so
        nothing downstream fails -- proven 2026-09-15 by an A/B probe of two
        identical PHYSICAL devices differing only in `trunking`, which
        isolated three faults caused solely by trunking=yes, led by
        "Configuration is invalid due to trunked port group option specified
        for physical device". Refusing it here turns a silent invalid object
        into an immediate, explainable error -- same rationale as
        CreateTenantRequest mirroring the OPA naming rule.
        """
        if self.trunking and self.device_type.upper() == "PHYSICAL":
            raise ValueError(
                "trunking is a VMM port-group option and is invalid on a PHYSICAL "
                "device -- APIC accepts it and then flags the L4-L7 device as "
                "invalid. Set trunking=False, or use device_type='VIRTUAL' with a "
                "vmm_domain."
            )
        return self

    @model_validator(mode="after")
    def _validate_device_domain_binding(self):
        """Each device type binds to a different domain through a different
        provider attribute, and both are mandatory.

        VIRTUAL -> relation_vns_rs_al_dev_to_dom_p (a VMM domain).
        PHYSICAL -> relation_vns_rs_al_dev_to_phys_dom_p, which the provider
        rejects at PLAN time when absent ("is required when device_type is
        PHYSICAL"). Catching both here means the failure names the missing
        field instead of surfacing as a provider error twenty minutes later.
        """
        device_type = self.device_type.upper()
        if device_type == "VIRTUAL" and not self.vmm_domain:
            raise ValueError("vmm_domain is required when device_type is VIRTUAL")
        if device_type == "PHYSICAL" and not self.physical_domain:
            raise ValueError(
                "physical_domain is required when device_type is PHYSICAL -- the "
                "provider makes relation_vns_rs_al_dev_to_phys_dom_p mandatory and "
                "fails at plan time without it"
            )
        return self


class ConcreteInterfaceSpec(BaseModel):
    """One port on the service appliance (``vnsCIf``), and the logical
    interface it backs.

    A concrete interface is identified in exactly one of two ways, never
    both, and which one is correct follows from the parent device's type:

    * VIRTUAL -- ``vnic_name``, the vCenter-discovered adapter name (e.g.
      "Network adapter 2"). Resolves through the VMM controller's inventory,
      so it needs no leaf port and works on a fabric with no switches.
    * PHYSICAL -- ``node_id``/``module``/``port``, which build a
      ``topology/pod-N/paths-M/pathep-[ethX/Y]`` DN.
    """

    name: str = Field(description="Concrete interface name, unique within the concrete device.")
    logical_interface: str = Field(
        description=(
            "Name of an existing logical interface (vnsLIf) on the parent L4-L7 "
            "device that this concrete interface backs. Binding the two is what "
            "clears APIC's 'LIf has no relation to CIf' fault -- a concrete "
            "device that is not wired to a logical interface leaves the device "
            "invalid just the same."
        )
    )
    vnic_name: str | None = Field(
        default=None,
        description=(
            "vCenter vNIC adapter name, e.g. 'Network adapter 2'. VIRTUAL "
            "devices only. Must match the adapter as vCenter reports it, because "
            "APIC resolves it against the VMM controller's inventory."
        ),
    )
    node_id: int | None = Field(default=None, description="Leaf node ID the appliance port is cabled to. PHYSICAL devices only.")
    pod_id: int = Field(default=1, description="APIC pod ID for the path DN. PHYSICAL devices only.")
    module: int = Field(default=1, description="Line-card/module number in the path DN. PHYSICAL devices only.")
    port: int | None = Field(default=None, description="Port number in the path DN. PHYSICAL devices only.")
    encap: str | None = Field(
        default=None,
        description=(
            "Optional VLAN encapsulation, e.g. 'vlan-101'. Normally omitted: for "
            "an unmanaged device APIC allocates it from the domain's VLAN pool, "
            "and pinning a VLAN outside that pool makes the interface invalid."
        ),
    )

    @field_validator("name", "logical_interface")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _exactly_one_identification_method(self):
        has_vnic = self.vnic_name is not None
        has_path = self.node_id is not None or self.port is not None
        if has_vnic and has_path:
            raise ValueError(
                f"concrete interface '{self.name}': set either vnic_name (VIRTUAL) "
                "or node_id/port (PHYSICAL), not both -- they are two different "
                "ways of identifying the same port and APIC accepts only one"
            )
        if not has_vnic and not has_path:
            raise ValueError(
                f"concrete interface '{self.name}': needs either vnic_name (for a "
                "VIRTUAL device) or node_id and port (for a PHYSICAL one). Without "
                "one of them APIC flags the concrete device invalid with "
                "'Virtual Object like vnic name is missing in CIf'"
            )
        if has_path and (self.node_id is None or self.port is None):
            raise ValueError(
                f"concrete interface '{self.name}': a physical path needs BOTH "
                "node_id and port"
            )
        return self


class CreateConcreteDeviceRequest(BaseModel):
    """Create a concrete device (``vnsCDev``) behind an existing logical L4-L7
    device, and wire its interfaces to that device's logical interfaces.

    **Why this exists.** A logical device with no concrete device behind it is
    not deployable. APIC accepts it, then marks it invalid --
    ``vnsConfIssue-missing-cdev`` -- and every fault on the service graph above
    it cascades from that. Measured live on 2026-09-15: a VIRTUAL logical
    device alone raised 10 faults, all rooted there.

    **A VIRTUAL concrete device requires a VMM controller.** The same
    measurement showed that adding a concrete device to a controller-less VMM
    domain does not reduce the fault count -- it holds at 10 and simply trades
    the faults for ``F1778`` (cannot form the relation to the controller DN)
    and "Virtual Object like vnic name is missing in CIf". A virtual
    appliance's ports are identified by vCenter-discovered vNIC names, so with
    no vCenter there is nothing for them to resolve against. This schema
    therefore requires the controller rather than letting a caller build the
    strictly worse configuration.
    """

    tenant: str = Field(description="Name of the existing Tenant that owns the L4-L7 device.")
    device: str = Field(description="Name of the existing logical L4-L7 device (vnsLDevVip) this concrete device sits behind.")
    name: str = Field(description="Concrete device name (vnsCDev).")
    interfaces: list[ConcreteInterfaceSpec] = Field(
        description="Concrete interfaces on this appliance, each bound to a logical interface of the parent device."
    )
    device_type: str = Field(
        default="VIRTUAL",
        description="Must match the parent logical device: VIRTUAL or PHYSICAL. Decides how interfaces are identified.",
    )
    vm_name: str | None = Field(
        default=None,
        description=(
            "vCenter VM name of the appliance, e.g. 'ASAv-1'. Required for VIRTUAL. "
            "Must name a VM that actually exists in the controller's inventory -- "
            "APIC resolves it, it is not free text."
        ),
    )
    vmm_domain: str | None = Field(default=None, description="Existing VMM Domain name. Required for VIRTUAL.")
    vmm_controller: str | None = Field(
        default=None,
        description=(
            "Controller name inside that VMM Domain. Required for VIRTUAL -- see "
            "this schema's note on why a controller-less domain is refused."
        ),
    )
    vendor: str = Field(default="VMware", description="VMM vendor, used to build the controller DN.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name", "device")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _interfaces_are_present_and_unique(self):
        if not self.interfaces:
            raise ValueError(
                "at least one concrete interface is required -- a concrete device "
                "with no interfaces leaves the logical interfaces unbound and the "
                "device invalid"
            )
        names = [i.name for i in self.interfaces]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"duplicate concrete interface name(s): {', '.join(duplicates)}")
        return self

    @model_validator(mode="after")
    def _identification_matches_device_type(self):
        """The parent device's type decides how its ports are identified, so a
        mismatch is caught here rather than accepted and silently marked
        invalid by APIC."""
        device_type = self.device_type.upper()
        if device_type == "VIRTUAL":
            missing = [
                field
                for field, value in (
                    ("vm_name", self.vm_name),
                    ("vmm_domain", self.vmm_domain),
                    ("vmm_controller", self.vmm_controller),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} required when device_type is VIRTUAL. A "
                    "virtual concrete device is resolved through vCenter inventory; "
                    "without a controller APIC cannot resolve the VM or its vNICs "
                    "and flags the device invalid (measured: F1778 + F0765)"
                )
            wrong = [i.name for i in self.interfaces if i.vnic_name is None]
            if wrong:
                raise ValueError(
                    f"VIRTUAL concrete device: interface(s) {', '.join(wrong)} need "
                    "vnic_name, not a leaf path"
                )
        elif device_type == "PHYSICAL":
            for field, value in (("vm_name", self.vm_name), ("vmm_controller", self.vmm_controller)):
                if value:
                    raise ValueError(
                        f"{field} is a VIRTUAL-only field and is meaningless on a "
                        "PHYSICAL concrete device, which is identified by its "
                        "interfaces' leaf paths"
                    )
            wrong = [i.name for i in self.interfaces if i.node_id is None]
            if wrong:
                raise ValueError(
                    f"PHYSICAL concrete device: interface(s) {', '.join(wrong)} need "
                    "node_id and port, not a vnic_name"
                )
        else:
            raise ValueError(f"device_type must be VIRTUAL or PHYSICAL, got '{self.device_type}'")
        return self


class CreateServiceGraphRequest(BaseModel):
    """Create a two-arm service graph that binds an existing Contract to a
    logical L4-L7 device, interfaces, and PBR redirect policies."""

    tenant: str = Field(description="Name of the existing Tenant that owns the graph.")
    name: str = Field(description="Service graph template name.")
    contract: str = Field(description="Existing Contract name to attach to this graph.")
    device: str = Field(description="Existing logical L4-L7 device name.")
    consumer_logical_interface: str = Field(description="Existing logical interface used on the consumer arm.")
    consumer_redirect_policy: str = Field(description="Existing PBR redirect policy used on the consumer arm.")
    provider_logical_interface: str = Field(description="Existing logical interface used on the provider arm.")
    provider_redirect_policy: str = Field(description="Existing PBR redirect policy used on the provider arm.")
    node_name: str = Field(default="node-1", description="Logical graph node name.")
    template_type: str = Field(default="FW_ROUTED", description="ACI service graph template type.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator(
        "name",
        "contract",
        "device",
        "consumer_logical_interface",
        "consumer_redirect_policy",
        "provider_logical_interface",
        "provider_redirect_policy",
        "node_name",
    )
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class PbrDestinationSpec(BaseModel):
    """One redirect destination (vnsRedirectDest) inside a PBR policy."""

    ip: str = Field(description="Redirect destination IPv4 or IPv6 address.")
    mac: str | None = Field(default=None, description="Optional destination MAC address.")
    second_ip: str | None = Field(default=None, description="Optional second IP for a dual-IP destination.")
    dest_name: str | None = Field(default=None, description="Optional destination name.")
    pod_id: int | None = Field(default=None, ge=1, description="Optional pod ID for a multi-pod destination.")
    health_group: str | None = Field(
        default=None,
        description="Name of an existing redirect health group that tracks this destination. Without one the destination is never health-checked and keeps receiving traffic after it dies.",
    )
    description: str = Field(default="", description="Optional free-text description.")


class CreatePbrHealthGroupRequest(BaseModel):
    """A redirect health group (vnsRedirectHealthGroup) -- the object a PBR
    destination is bound to in order to be tracked at all."""

    tenant: str = Field(description="Name of the existing Tenant that owns the health group.")
    name: str = Field(description="Redirect health group name.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateIpSlaPolicyRequest(BaseModel):
    """An IP SLA monitoring policy (fvIPSLAMonitoringPol) -- the probe that
    determines whether a tracked PBR destination is actually alive."""

    tenant: str = Field(description="Name of the existing Tenant that owns the policy.")
    name: str = Field(description="IP SLA monitoring policy name.")
    sla_type: str = Field(default="icmp", description="Probe type: 'icmp', 'tcp', 'l2ping' or 'http'.")
    frequency: int | None = Field(default=None, ge=1, description="Probe interval in seconds.")
    port: int | None = Field(default=None, ge=1, le=65535, description="Destination port -- required when sla_type is 'tcp'.")
    detect_multiplier: int | None = Field(default=None, ge=1, description="Consecutive missed probes before the destination is declared down.")
    timeout: int | None = Field(default=None, ge=1, description="Per-probe timeout in milliseconds.")
    threshold: int | None = Field(default=None, ge=0, description="Rising threshold in milliseconds.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _tcp_probe_needs_a_port(self):
        if self.sla_type.lower() == "tcp" and self.port is None:
            raise ValueError("port is required when sla_type is 'tcp'")
        return self


class CreatePbrPolicyRequest(BaseModel):
    """Create a policy-based redirect policy.

    Accepts either a single destination via the original
    `destination_ip`/`destination_mac` shorthand, or a full `destinations`
    list. Real PBR policies are routinely multi-destination -- the
    single-destination-only shape was a limit of this tool, never of ACI or
    of the Terraform beneath it, which has always flattened a
    `destinations[]` list.
    """

    tenant: str = Field(description="Name of the existing Tenant that owns the redirect policy.")
    name: str = Field(description="PBR redirect policy name.")
    destination_ip: str | None = Field(default=None, description="Shorthand for a single destination IP. Use `destinations` for more than one.")
    destination_mac: str | None = Field(default=None, description="Optional MAC accompanying the `destination_ip` shorthand.")
    destinations: list[PbrDestinationSpec] = Field(default_factory=list, description="Full destination list. Mutually exclusive with `destination_ip`.")
    destination_type: str = Field(default="L3", description="ACI redirect destination type.")
    anycast: bool = Field(default=False, description="Enable anycast on the redirect policy.")
    pod_aware: bool = Field(default=False, description="Restrict programming to the local POD.")
    resilient_hashing: bool = Field(default=False, description="Enable resilient hashing.")
    hashing_algorithm: str | None = Field(default=None, description="Load-balancing hash: 'sip', 'dip' or 'sip-dip-prototype'.")
    ip_sla_policy: str | None = Field(default=None, description="Name of an existing IP SLA monitoring policy to attach.")
    threshold_enable: bool = Field(default=False, description="Enable the min/max threshold behaviour.")
    min_threshold_percent: int | None = Field(default=None, ge=0, le=100, description="Percentage of live destinations below which threshold_down_action fires.")
    max_threshold_percent: int | None = Field(default=None, ge=0, le=100, description="Percentage at which the group is considered healthy again.")
    threshold_down_action: str | None = Field(default=None, description="Action when below threshold: 'permit', 'deny' or 'bypass'.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)

    @model_validator(mode="after")
    def _normalise_destinations(self):
        if self.destination_ip and self.destinations:
            raise ValueError("provide either destination_ip or destinations, not both")
        if self.destination_ip:
            self.destinations = [PbrDestinationSpec(ip=self.destination_ip, mac=self.destination_mac)]
        if not self.destinations:
            raise ValueError("at least one destination is required (destination_ip or destinations)")
        return self

    @model_validator(mode="after")
    def _thresholds_are_ordered(self):
        if (
            self.min_threshold_percent is not None
            and self.max_threshold_percent is not None
            and self.min_threshold_percent > self.max_threshold_percent
        ):
            raise ValueError("min_threshold_percent cannot exceed max_threshold_percent")
        return self

class CreateOneArmServiceGraphRequest(BaseModel):
    """Create a one-arm ADC/load-balancer Service Graph with one logical
    interface and one consumer-side redirect policy."""

    tenant: str = Field(description="Name of the existing Tenant that owns the graph.")
    name: str = Field(description="One-arm Service Graph template name.")
    contract: str = Field(description="Existing Contract name to attach to this graph.")
    device: str = Field(description="Existing one-arm logical L4-L7 device name.")
    logical_interface: str = Field(description="Existing logical interface used by the one arm.")
    redirect_policy: str = Field(description="Existing PBR redirect policy used by the one arm.")
    node_name: str = Field(default="node-1", description="Logical graph node name.")
    template_type: str = Field(default="ONE_NODE_ADC_ONE_ARM", description="One-arm ACI service graph UI template type.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name", "contract", "device", "logical_interface", "redirect_policy", "node_name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreatePbrContractRequest(BaseModel):
    """Create a Contract bound to a Service Graph and attach it to existing
    consumer and provider VLAN-backed EPGs."""

    tenant: str = Field(description="Name of the existing Tenant that owns the Contract and EPGs.")
    name: str = Field(description="Contract name.")
    filter_name: str = Field(description="Filter name, created with one default entry when new.")
    service_graph: str = Field(description="Existing Service Graph name to attach to the Contract subject.")
    consumer_epg: str = Field(description="Existing VLAN-backed consumer EPG name.")
    provider_epg: str = Field(description="Existing VLAN-backed provider EPG name.")
    ether_type: str = Field(default="ip", description="Filter entry ether type when the filter is newly created.")
    ip_protocol: str = Field(default="unspecified", description="Filter entry IP protocol when the filter is newly created.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name", "filter_name", "service_graph", "consumer_epg", "provider_epg")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)
