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


class CreateVlanPoolRequest(FabricPolicyRequest):
    alloc_mode: str = Field(default="static")
    ranges: list[dict] = Field(default_factory=list)
    description: str = Field(default="", description="Optional description.")


class CreatePhysicalDomainRequest(FabricPolicyRequest):
    vlan_pool: str
    description: str = Field(default="", description="Optional description.")


class CreateAaepRequest(FabricPolicyRequest):
    domains: list[str] = Field(default_factory=list)
    description: str = Field(default="", description="Optional description.")


class CreateLeafInterfacePolicyGroupRequest(FabricPolicyRequest):
    aep: str
    description: str = Field(default="", description="Optional description.")


class CreateLeafInterfaceProfileRequest(FabricPolicyRequest):
    node_id: int = Field(ge=1)
    pod_id: int = Field(default=1, ge=1)
    description: str = Field(default="", description="Optional description.")


class CreateInterfaceSelectorRequest(FabricPolicyRequest):
    leaf_interface_profile: str
    policy_group: str
    module: int = Field(ge=1)
    port: int = Field(ge=1)


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


class BindEpgToPhysicalDomainRequest(BaseModel):
    tenant: str
    application_profile: str
    epg: str
    physical_domain: str


class BindEpgToVmmDomainRequest(BaseModel):
    tenant: str
    application_profile: str
    epg: str
    vmm_domain: str
    encap: str | None = None
    mode: str = "regular"


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

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


class CreateVmmDomainRequest(BaseModel):
    """VMware VMM Domain coverage. vCenter credentials are deliberately
    not part of this request; Terraform receives them at runtime via
    sensitive variables or Vault/CI variables."""

    location: str = Field(description="Name of the ACI Location whose aci_fabric_policies custom field is updated.")
    name: str = Field(description="ACI VMM Domain name.")
    controller_name: str = Field(description="ACI VMM Controller name.")
    host_or_ip: str = Field(description="vCenter hostname or IP address.")
    root_cont_name: str = Field(description="vCenter datacenter/root container name.")
    vendor: str = Field(default="VMware", description="VMM vendor. Defaults to VMware.")
    vlan_pool: str | None = Field(default=None, description="Optional existing VLAN Pool name to bind to the VMM Domain.")
    credential_name: str | None = Field(default=None, description="Optional ACI VMM Credential object name; not a password.")
    dvs_version: str = Field(default="unmanaged", description="VMM DVS version. Defaults to unmanaged.")

    @field_validator("name", "controller_name", "credential_name")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        return _validate_aci_name(v) if v is not None else v


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
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name", "consumer_interface", "provider_interface")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        return _validate_aci_name(v) if v is not None else v

    @model_validator(mode="after")
    def _validate_virtual_device_vmm_domain(self):
        if self.device_type.upper() == "VIRTUAL" and not self.vmm_domain:
            raise ValueError("vmm_domain is required when device_type is VIRTUAL")
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


class CreatePbrPolicyRequest(BaseModel):
    """Create a policy-based redirect policy with one L3 destination."""

    tenant: str = Field(description="Name of the existing Tenant that owns the redirect policy.")
    name: str = Field(description="PBR redirect policy name.")
    destination_ip: str = Field(description="Redirect destination IPv4 or IPv6 address.")
    destination_mac: str | None = Field(default=None, description="Optional destination MAC address.")
    destination_type: str = Field(default="L3", description="ACI redirect destination type.")
    anycast: bool = Field(default=False, description="Enable anycast on the redirect policy.")
    pod_aware: bool = Field(default=False, description="Restrict programming to the local POD.")
    resilient_hashing: bool = Field(default=False, description="Enable resilient hashing.")
    description: str = Field(default="", description="Optional free-text description.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _validate_aci_name(v)


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
