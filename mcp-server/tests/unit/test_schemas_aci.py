"""Unit tests for ACI tool input validation -- no live Nautobot needed."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.schemas.aci import (
    BindEpgContractRequest,
    BindEpgDomainRequest,
    CreateAccessPortBlockRequest,
    CreateAccessPortProfileRequest,
    CreateAccessPortSelectorRequest,
    CreateAepRequest,
    CreateBridgeDomainRequest,
    CreateContractRequest,
    CreateContractSubjectRequest,
    CreateEpgRequest,
    CreateFabricDeviceRequest,
    CreateFabricInterfaceRequest,
    CreateFilterEntryRequest,
    CreateFilterRequest,
    CreateL3OutRequest,
    BindExternalEpgRouteControlProfileRequest,
    BindL3OutInterfaceProfilePoliciesRequest,
    AddExternalEpgSubnetRequest,
    AddMatchRulePrefixRequest,
    AepDomainSpec,
    BindExternalEpgContractRequest,
    CreateL3DomainRequest,
    CreateMatchRuleRequest,
    CreateRouteControlProfileRequest,
    SetExternalEpgSubnetScopeRequest,
    CreateConcreteDeviceRequest,
    CreateCustomQosPolicyRequest,
    CreateDppPolicyRequest,
    CreateIgmpInterfacePolicyRequest,
    CreateNdInterfacePolicyRequest,
    CreatePimInterfacePolicyRequest,
    CreateL4L7DeviceRequest,
    CreateLeafInterfacePolicyGroupRequest,
    CreateLeafNodeBlockRequest,
    CreateLeafProfileRequest,
    CreateLeafSelectorRequest,
    CreateLocalUserRequest,
    CreateOneArmServiceGraphRequest,
    CreatePbrContractRequest,
    CreatePbrPolicyRequest,
    CreatePhysicalDomainRequest,
    CreatePodPolicyGroupRequest,
    CreateSecurityDomainRequest,
    CreateServiceGraphRequest,
    CreateTenantRequest,
    CreateVlanPoolRequest,
    CreateVmmDomainRequest,
    CreateVrfRequest,
    CreateVrfRouteLeakRequest,
    CreateIpSlaPolicyRequest,
    CreatePbrHealthGroupRequest,
    PbrDestinationSpec,
    FilterEntrySpec,
)
from mcp_server.schemas.aci import (
    CreateBgpPeerRequest,
    CreateInterfaceSelectorRequest,
    CreateL3OutInterfaceProfileRequest,
    CreateL3OutInterfaceRequest,
    CreateL3OutNodeProfileRequest,
    CreateLeafInterfaceProfileRequest,
    CreateOspfInterfacePolicyRequest,
    CreateOspfInterfaceRequest,
    CreateProtocolL3OutRequest,
    CreateStaticPathBindingRequest,
)


def test_valid_tenant_name():
    req = CreateTenantRequest(name="finance", description="d")
    assert req.name == "finance"


def test_valid_tenant_name_with_hyphen_and_digits():
    CreateTenantRequest(name="finance-2")


@pytest.mark.parametrize(
    "bad_name",
    ["Finance", "finance_dept", "finance dept", "Finance_2", "UPPER"],
)
def test_invalid_tenant_name_rejected(bad_name):
    """Mirrors the live OPA policy_check job's naming rule
    (docker/platform-api/policy/cisco_aci/tenant_naming.rego) -- catching
    this at the MCP layer avoids a guaranteed pipeline denial later."""
    with pytest.raises(ValidationError):
        CreateTenantRequest(name=bad_name)


def test_description_defaults_to_empty_string():
    req = CreateTenantRequest(name="finance")
    assert req.description == ""


def test_valid_vrf_request():
    req = CreateVrfRequest(tenant="finance", name="finance-vrf")
    assert req.tenant == "finance"
    assert req.description == ""


@pytest.mark.parametrize("bad_name", ["bad name", "bad/name", "bad#name"])
def test_invalid_vrf_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateVrfRequest(tenant="finance", name=bad_name)


def test_vrf_name_allows_underscore_and_period():
    """ACI object names (unlike Tenant names) allow underscore/period/colon."""
    CreateVrfRequest(tenant="finance", name="finance_vrf.v1:prod")


def test_valid_bridge_domain_request():
    req = CreateBridgeDomainRequest(
        tenant="finance", vrf="finance-vrf", name="finance-bd", gateway_ip="10.10.10.1/24"
    )
    assert req.gateway_ip == "10.10.10.1/24"


def test_valid_epg_request():
    req = CreateEpgRequest(
        tenant="finance",
        application_profile="finance-ap",
        bridge_domain="finance-bd",
        name="finance-epg",
        vid=100,
    )
    assert req.vid == 100


@pytest.mark.parametrize("bad_vid", [0, 4095, -1])
def test_epg_vid_out_of_range_rejected(bad_vid):
    with pytest.raises(ValidationError):
        CreateEpgRequest(
            tenant="finance",
            application_profile="finance-ap",
            bridge_domain="finance-bd",
            name="finance-epg",
            vid=bad_vid,
        )


def test_valid_contract_request_defaults():
    req = CreateContractRequest(tenant="finance", name="web-to-db", filter_name="web-filter")
    assert req.scope == "context"
    assert req.ether_type == "ip"
    assert req.ip_protocol == "unspecified"


def test_valid_l3out_request_defaults():
    req = CreateL3OutRequest(
        tenant="finance", vrf="finance-vrf", name="l3out-internet", external_epg_name="ext-epg-internet"
    )
    assert req.subnet == "0.0.0.0/0"
    assert req.description == ""


def test_valid_vlan_pool_request_defaults():
    req = CreateVlanPoolRequest(name="pool1", range_from=100, range_to=200)
    assert req.location is None, "location must auto-resolve, not carry a hardcoded default"
    assert req.alloc_mode == "static"
    assert req.role == "external"
    assert req.range_alloc_mode is None


@pytest.mark.parametrize("bad_vid", [0, 4095])
def test_vlan_pool_range_out_of_bounds_rejected(bad_vid):
    with pytest.raises(ValidationError):
        CreateVlanPoolRequest(name="pool1", range_from=bad_vid, range_to=200)


def test_valid_physical_domain_request_defaults():
    req = CreatePhysicalDomainRequest(name="phys-dom1")
    assert req.location is None, "location must auto-resolve, not carry a hardcoded default"
    assert req.vlan_pool is None


def test_valid_aep_request_defaults():
    req = CreateAepRequest(name="aep1")
    assert req.domains == []


def test_aep_request_with_domains():
    req = CreateAepRequest(name="aep1", domains=["phys-dom1", "phys-dom2"])
    assert req.domains == ["phys-dom1", "phys-dom2"]


def test_valid_leaf_interface_policy_group_request_defaults():
    req = CreateLeafInterfacePolicyGroupRequest(name="leaf-pg1")
    assert req.aep is None


def test_valid_vmm_domain_request_defaults():
    req = CreateVmmDomainRequest(
        name="vmm1", controller_name="vc1", host_or_ip="vcenter.example.com", root_cont_name="Datacenter1"
    )
    assert req.location is None, "location must auto-resolve, not carry a hardcoded default"
    assert req.vendor == "VMware"
    assert req.vlan_pool is None
    assert req.credential_name is None
    assert req.dvs_version == "unmanaged"


def test_vmm_domain_request_with_optional_fields():
    req = CreateVmmDomainRequest(
        name="vmm1",
        controller_name="vc1",
        host_or_ip="vcenter.example.com",
        root_cont_name="Datacenter1",
        vlan_pool="pool1",
        credential_name="vc1-cred",
    )
    assert req.vlan_pool == "pool1"
    assert req.credential_name == "vc1-cred"


@pytest.mark.parametrize("bad_name", ["bad name", "bad/name", "bad#name"])
def test_invalid_vmm_domain_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateVmmDomainRequest(
            name=bad_name, controller_name="vc1", host_or_ip="vcenter.example.com", root_cont_name="Datacenter1"
        )


def test_valid_security_domain_request_defaults():
    req = CreateSecurityDomainRequest(name="phase-f-domain")
    assert req.location is None, "location must auto-resolve, not carry a hardcoded default"
    assert req.description == ""


def test_valid_local_user_request_defaults():
    req = CreateLocalUserRequest(name="phase-f-user")
    assert req.location is None, "location must auto-resolve, not carry a hardcoded default"
    assert req.account_status == "active"
    assert req.security_domain is None
    assert req.role is None
    assert req.priv_type is None


def test_local_user_request_with_security_domain_and_role():
    req = CreateLocalUserRequest(name="phase-f-user", security_domain="phase-f-domain", role="read-all", priv_type="readPriv")
    assert req.security_domain == "phase-f-domain"
    assert req.role == "read-all"
    assert req.priv_type == "readPriv"


@pytest.mark.parametrize("bad_name", ["bad name", "bad/name", "bad#name"])
def test_invalid_local_user_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateLocalUserRequest(name=bad_name)


def test_valid_bind_epg_domain_request_defaults():
    req = BindEpgDomainRequest(
        tenant="finance", application_profile="finance-ap", epg="finance-epg", domain="phys-dom1", domain_type="physical"
    )
    assert req.resolution_immediacy is None
    assert req.deployment_immediacy is None


def test_bind_epg_domain_request_with_immediacy():
    req = BindEpgDomainRequest(
        tenant="finance",
        application_profile="finance-ap",
        epg="finance-epg",
        domain="vmm-dom1",
        domain_type="vmm",
        resolution_immediacy="immediate",
        deployment_immediacy="lazy",
    )
    assert req.resolution_immediacy == "immediate"
    assert req.deployment_immediacy == "lazy"


@pytest.mark.parametrize("bad_type", ["Physical", "VMM", "physical-domain", ""])
def test_invalid_bind_epg_domain_type_rejected(bad_type):
    with pytest.raises(ValidationError):
        BindEpgDomainRequest(
            tenant="finance", application_profile="finance-ap", epg="finance-epg", domain="dom1", domain_type=bad_type
        )


# Ported from copilot/aci-platform-comparison (2026-09-08) -- L4-L7/PBR/
# Service Graph and VRF route-leak schema tests, genuinely new coverage.
def test_l4l7_and_pbr_request_defaults():
    device = CreateL4L7DeviceRequest(
        tenant="finance", name="fw", consumer_interface="inside", provider_interface="outside", vmm_domain="finance-vmm"
    )
    graph = CreateServiceGraphRequest(
        tenant="finance",
        name="fw-graph",
        contract="web-to-db",
        device="fw",
        consumer_logical_interface="inside",
        consumer_redirect_policy="inside-pbr",
        provider_logical_interface="outside",
        provider_redirect_policy="outside-pbr",
    )
    policy = CreatePbrPolicyRequest(tenant="finance", name="web-pbr", destination_ip="10.0.0.10")
    contract = CreatePbrContractRequest(
        tenant="finance",
        name="web-to-db",
        filter_name="tcp-filter",
        service_graph="fw-graph",
        consumer_epg="web",
        provider_epg="db",
    )

    assert device.service_type == "FW"
    assert graph.node_name == "node-1"
    assert policy.destination_type == "L3"
    assert contract.ip_protocol == "unspecified"


def test_invalid_service_graph_name_rejected():
    with pytest.raises(ValidationError):
        CreateServiceGraphRequest(
            tenant="finance",
            name="bad graph",
            contract="web-to-db",
            device="fw",
            consumer_logical_interface="inside",
            consumer_redirect_policy="inside-pbr",
            provider_logical_interface="outside",
            provider_redirect_policy="outside-pbr",
        )


def test_virtual_l4l7_device_requires_vmm_domain():
    with pytest.raises(ValidationError):
        CreateL4L7DeviceRequest(tenant="finance", name="fw", consumer_interface="inside", provider_interface="outside")


def test_one_arm_device_and_service_graph_request():
    device = CreateL4L7DeviceRequest(tenant="finance", name="adc", consumer_interface="client", vmm_domain="finance-vmm")
    graph = CreateOneArmServiceGraphRequest(
        tenant="finance", name="adc-graph", contract="client-to-app", device="adc", logical_interface="client", redirect_policy="adc-pbr"
    )

    assert device.provider_interface is None
    assert graph.template_type == "ONE_NODE_ADC_ONE_ARM"


def test_vrf_route_leak_request_defaults_and_distinct_vrfs():
    request = CreateVrfRouteLeakRequest(
        tenant="finance",
        name="shared-to-app",
        source_vrf="shared-vrf",
        destination_vrf="app-vrf",
        subnet="10.10.10.0/24",
    )

    assert request.allow_l3out_advertisement is False


def test_vrf_route_leak_rejects_same_source_and_destination():
    with pytest.raises(ValidationError):
        CreateVrfRouteLeakRequest(
            tenant="finance",
            name="invalid-leak",
            source_vrf="app-vrf",
            destination_vrf="app-vrf",
            subnet="10.10.10.0/24",
        )


# ---------------------------------------------------------------------------
# Contract/Filter decomposition tools (create_filter, create_filter_entry,
# create_contract_subject, bind_epg_contract) and Phase E's
# create_pod_policy_group.
#
# These five tools shipped with dispatch tests but no schema tests -- this
# section closes that gap. Every assertion below was checked against the
# real schema definitions in schemas/aci.py, not assumed: the shared name
# validator here is _ACI_NAME_RE = ^[a-zA-Z0-9_.:-]+$, which is
# deliberately WIDER than CreateTenantRequest's ^[a-z0-9-]+$ (ACI object
# names other than tenants legitimately carry uppercase, '_', '.' and ':').
# ---------------------------------------------------------------------------

def test_valid_filter_request_entry_defaults():
    """FilterEntrySpec's defaults are what `create_filter` emits when the
    caller supplies only an entry name -- ether_type 'ip', protocol
    'unspecified', and both boolean flags off."""
    req = CreateFilterRequest(tenant="finance", name="web-filter", entries=[FilterEntrySpec(name="https")])

    entry = req.entries[0]
    assert entry.ether_type == "ip"
    assert entry.ip_protocol == "unspecified"
    assert entry.stateful is False
    assert entry.apply_to_fragments is False
    assert req.description == ""


def test_filter_request_carries_full_entry_attribute_depth():
    """The whole point of create_filter over create_contract: create_contract
    only ever emits a single 'default' entry, so the deep vzEntry attributes
    must survive this schema intact."""
    req = CreateFilterRequest(
        tenant="finance",
        name="web-filter",
        entries=[
            FilterEntrySpec(
                name="https",
                ether_type="ip",
                ip_protocol="tcp",
                dest_from_port="443",
                dest_to_port="443",
                tcp_rules=["syn", "ack"],
                stateful=True,
            )
        ],
    )

    entry = req.entries[0]
    assert entry.ip_protocol == "tcp"
    assert entry.dest_from_port == "443"
    assert entry.tcp_rules == ["syn", "ack"]
    assert entry.stateful is True


def test_filter_request_rejects_empty_entry_list():
    """entries has min_length=1 -- a Filter with no vzEntry is meaningless
    in ACI and would produce an empty object."""
    with pytest.raises(ValidationError):
        CreateFilterRequest(tenant="finance", name="web-filter", entries=[])


@pytest.mark.parametrize("bad_name", ["web filter", "web/filter", "web,filter", ""])
def test_invalid_filter_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateFilterRequest(tenant="finance", name=bad_name, entries=[FilterEntrySpec(name="e1")])


def test_filter_name_allows_uppercase_underscore_and_colon():
    """Unlike tenant names, general ACI object names may carry uppercase,
    '_', '.' and ':' -- pinning the real, wider rule so a future tightening
    of _ACI_NAME_RE cannot silently break existing fabric object names."""
    CreateFilterRequest(tenant="finance", name="Web_Filter.v2:1", entries=[FilterEntrySpec(name="e1")])


def test_valid_filter_entry_request():
    req = CreateFilterEntryRequest(
        tenant="finance", filter_name="web-filter", entry=FilterEntrySpec(name="http", ip_protocol="tcp", dest_from_port="80")
    )
    assert req.filter_name == "web-filter"
    assert req.entry.dest_from_port == "80"


@pytest.mark.parametrize("bad_name", ["web filter", "web|filter", ""])
def test_invalid_filter_entry_target_filter_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateFilterEntryRequest(tenant="finance", filter_name=bad_name, entry=FilterEntrySpec(name="http"))


def test_contract_subject_defaults_are_bidirectional():
    """ACI's own default for a Subject is bidirectional with reversed return
    ports; these defaults mirror that so an unqualified call behaves the way
    an engineer expects from the APIC GUI."""
    req = CreateContractSubjectRequest(tenant="finance", contract="web-to-db", name="subj1", filters=["tcp-filter"])

    assert req.apply_both_directions is True
    assert req.reverse_filter_ports is True
    assert req.priority is None
    assert req.target_dscp is None


def test_contract_subject_rejects_empty_filter_chain():
    """filters has min_length=1 -- a Subject with no filter chain permits
    nothing and is a configuration error, not a valid default."""
    with pytest.raises(ValidationError):
        CreateContractSubjectRequest(tenant="finance", contract="web-to-db", name="subj1", filters=[])


@pytest.mark.parametrize("bad_filter", ["tcp filter", "tcp/filter", ""])
def test_contract_subject_validates_every_filter_name(bad_filter):
    """Each entry in the filter chain is validated individually -- a single
    bad name in an otherwise-valid list must still be rejected."""
    with pytest.raises(ValidationError):
        CreateContractSubjectRequest(
            tenant="finance", contract="web-to-db", name="subj1", filters=["good-filter", bad_filter]
        )


@pytest.mark.parametrize("relation", ["provided", "consumed"])
def test_bind_epg_contract_accepts_both_relations(relation):
    req = BindEpgContractRequest(
        tenant="finance", application_profile="finance-ap", epg="web-epg", contract="web-to-db", relation=relation
    )
    assert req.relation == relation


@pytest.mark.parametrize("bad_relation", ["provider", "consumer", "Provided", "both", ""])
def test_invalid_bind_epg_contract_relation_rejected(bad_relation):
    """'provider'/'consumer' are the APIC-side words and are a very easy
    mistake for an AI agent to make -- rejecting them here turns a
    guaranteed later failure into an immediate, explainable one."""
    with pytest.raises(ValidationError):
        BindEpgContractRequest(
            tenant="finance",
            application_profile="finance-ap",
            epg="web-epg",
            contract="web-to-db",
            relation=bad_relation,
        )


def test_pod_policy_group_defaults_to_the_shipped_route_reflector_policy():
    """ACI ships exactly one BGP Route Reflector Policy, named 'default'.
    Defaulting to it is what makes a bare create_pod_policy_group call
    produce a usable group rather than one with an unresolved relation."""
    req = CreatePodPolicyGroupRequest(location="Isolated Lab Site", name="Pod_PG")
    assert req.bgp_route_reflector_policy == "default"


def test_pod_policy_group_route_reflector_policy_can_be_left_unresolved():
    req = CreatePodPolicyGroupRequest(location="Isolated Lab Site", name="Pod_PG", bgp_route_reflector_policy=None)
    assert req.bgp_route_reflector_policy is None


@pytest.mark.parametrize("bad_name", ["Pod PG", "Pod/PG", ""])
def test_invalid_pod_policy_group_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreatePodPolicyGroupRequest(location="Isolated Lab Site", name=bad_name)


# ---------------------------------------------------------------------------
# XML-compatible access hierarchy (infraAccPortP / infraHPortS / infraPortBlk
# / infraNodeP / infraLeafS / infraNodeBlk) and the DCIM fabric-inventory
# tools. These eight shipped with no tests at all.
#
# IMPORTANT -- these schemas are deliberately documented here as they really
# are, not as they arguably should be: only the two that inherit
# FabricPolicyRequest (access-port profile, leaf profile) and the
# access-port SELECTOR validate their `name`. The block/selector/node-block
# and DCIM schemas use a bare `str`, so a name with a space is ACCEPTED
# today. That inconsistency is real and is recorded in the audit rather
# than silently asserted as correct -- see the tightening note below.
# ---------------------------------------------------------------------------

def test_access_port_profile_request_defaults():
    req = CreateAccessPortProfileRequest(location="Isolated Lab Site", name="LEAF101_IFP")
    assert req.name == "LEAF101_IFP"
    assert req.description == ""


@pytest.mark.parametrize("bad_name", ["LEAF101 IFP", "LEAF101/IFP", ""])
def test_invalid_access_port_profile_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateAccessPortProfileRequest(location="Isolated Lab Site", name=bad_name)


def test_access_port_selector_request_defaults_to_range_type():
    """'range' is APIC's own default selector type (infraHPortS.type)."""
    req = CreateAccessPortSelectorRequest(
        location="Isolated Lab Site", name="Ext_Nexus", access_port_profile="LEAF101_IFP", policy_group="ExtL3_IPG"
    )
    assert req.selector_type == "range"


@pytest.mark.parametrize("bad_name", ["Ext Nexus", "Ext/Nexus", ""])
def test_invalid_access_port_selector_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateAccessPortSelectorRequest(
            location="Isolated Lab Site", name=bad_name, access_port_profile="LEAF101_IFP", policy_group="ExtL3_IPG"
        )


def test_access_port_block_to_fields_default_to_none_not_the_from_value():
    """to_card/to_port default to None here; main.tf is what falls back to
    the from_* value (`lookup(each.value, "to_port", each.value.from_port)`).
    Pinning None means a future change that starts defaulting them in the
    schema instead would surface as a failing test, rather than silently
    producing two sources of the same default."""
    req = CreateAccessPortBlockRequest(
        location="Isolated Lab Site",
        access_port_profile="LEAF101_IFP",
        selector="Ext_Nexus",
        name="portblk_ext_nexus",
        from_card=1,
        from_port=4,
    )
    assert req.to_card is None
    assert req.to_port is None


@pytest.mark.parametrize("field,bad_value", [("from_card", 0), ("from_port", 0), ("to_card", 0), ("to_port", 0)])
def test_access_port_block_rejects_zero_card_or_port(field, bad_value):
    """Card and port numbers are 1-indexed on every Nexus platform; ge=1
    stops a 0 that would otherwise render an invalid pathep-[eth0/0] DN."""
    kwargs = dict(
        location="Isolated Lab Site",
        access_port_profile="LEAF101_IFP",
        selector="Ext_Nexus",
        name="portblk",
        from_card=1,
        from_port=4,
    )
    kwargs[field] = bad_value
    with pytest.raises(ValidationError):
        CreateAccessPortBlockRequest(**kwargs)


def test_access_port_block_accepts_an_explicit_port_range():
    req = CreateAccessPortBlockRequest(
        location="Isolated Lab Site",
        access_port_profile="LEAF101_IFP",
        selector="Ext_Nexus",
        name="portblk",
        from_card=1,
        to_card=1,
        from_port=4,
        to_port=8,
    )
    assert (req.from_port, req.to_port) == (4, 8)


def test_leaf_profile_request_defaults_to_no_attached_port_profiles():
    req = CreateLeafProfileRequest(location="Isolated Lab Site", name="LEAF101_SWP")
    assert req.access_port_profiles == []
    assert req.description == ""


def test_leaf_profile_carries_attached_access_port_profiles():
    req = CreateLeafProfileRequest(
        location="Isolated Lab Site", name="LEAF101_SWP", access_port_profiles=["LEAF101_IFP", "LEAF102_IFP"]
    )
    assert req.access_port_profiles == ["LEAF101_IFP", "LEAF102_IFP"]


@pytest.mark.parametrize("bad_name", ["LEAF101 SWP", "LEAF101/SWP", ""])
def test_invalid_leaf_profile_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateLeafProfileRequest(location="Isolated Lab Site", name=bad_name)


def test_leaf_selector_request_defaults_to_range_type():
    req = CreateLeafSelectorRequest(location="Isolated Lab Site", leaf_profile="LEAF101_SWP", name="LEAF101_Sel")
    assert req.selector_type == "range"


def test_leaf_node_block_to_node_defaults_to_none():
    req = CreateLeafNodeBlockRequest(
        location="Isolated Lab Site", leaf_profile="LEAF101_SWP", selector="LEAF101_Sel", name="nodeblk_101_101", from_node=101
    )
    assert req.to_node is None


@pytest.mark.parametrize("field,bad_value", [("from_node", 0), ("to_node", 0)])
def test_leaf_node_block_rejects_zero_node_id(field, bad_value):
    """ACI fabric node IDs start at 101 for leaves; 0 is never valid and
    would render topology/pod-1/node-0."""
    kwargs = dict(
        location="Isolated Lab Site",
        leaf_profile="LEAF101_SWP",
        selector="LEAF101_Sel",
        name="nodeblk",
        from_node=101,
    )
    kwargs[field] = bad_value
    with pytest.raises(ValidationError):
        CreateLeafNodeBlockRequest(**kwargs)


def test_fabric_device_request_defaults():
    """These defaults encode this lab's own conventions -- role 'leaf',
    the Nexus 9000v model, the single Location the fabric policies hang
    off, and pod 1."""
    req = CreateFabricDeviceRequest(name="Leaf101", node_id=101)

    assert req.role == "leaf"
    assert req.pod_id == 1
    assert req.model == "Nexus 9000v"
    assert req.location is None, "location must auto-resolve, not carry a hardcoded default"
    assert req.serial == ""


def test_fabric_device_accepts_a_spine():
    req = CreateFabricDeviceRequest(name="spine-1", node_id=1001, role="spine", serial="FDO2306FG77")
    assert req.role == "spine"
    assert req.node_id == 1001


@pytest.mark.parametrize("bad_role", ["Leaf", "SPINE", "border-leaf", "controller", "server", ""])
def test_fabric_device_rejects_a_non_fabric_role(bad_role):
    """Only leaf and spine are fabric switches. The generator filters
    inventory on exactly these two strings (transformer._build_fabric_
    inventory), so an unconstrained role here would produce a Device that
    is silently absent from inventory and then fails node validation with
    a confusing message."""
    with pytest.raises(ValidationError):
        CreateFabricDeviceRequest(name="dev", node_id=101, role=bad_role)


@pytest.mark.parametrize("bad_node_id", [0, -1, 4001])
def test_fabric_device_rejects_out_of_range_node_id(bad_node_id):
    """ACI fabric node IDs run 1-4000; leaves and spines share that range."""
    with pytest.raises(ValidationError):
        CreateFabricDeviceRequest(name="Leaf101", node_id=bad_node_id)


@pytest.mark.parametrize("bad_pod_id", [0, -1])
def test_fabric_device_rejects_non_positive_pod_id(bad_pod_id):
    """pod_id renders into every topology/pod-N/... DN, so 0 would produce
    topology/pod-0."""
    with pytest.raises(ValidationError):
        CreateFabricDeviceRequest(name="Leaf101", node_id=101, pod_id=bad_pod_id)


def test_fabric_device_requires_a_node_id():
    """node_id has no default -- a fabric device without one cannot be
    resolved to a topology/pod-N/node-M DN by the generator."""
    with pytest.raises(ValidationError):
        CreateFabricDeviceRequest(name="Leaf101")


def test_fabric_interface_request_defaults_to_enabled():
    req = CreateFabricInterfaceRequest(device="Leaf101", name="eth1/4")
    assert req.enabled is True
    assert req.description == ""


def test_fabric_interface_name_permits_the_slash_in_a_real_interface_name():
    """Documents why CreateFabricInterfaceRequest.name is deliberately NOT
    run through _validate_aci_name: real interface names contain '/', which
    that validator rejects. This is the one place the looser typing is
    correct rather than an oversight."""
    req = CreateFabricInterfaceRequest(device="Leaf101", name="Ethernet1/4")
    assert req.name == "Ethernet1/4"


# ---------------------------------------------------------------------------
# Physical/protocol L3Out cluster: leaf interface profile, interface selector,
# EPG static path, BGP/OSPF L3Out hierarchy, routed/SVI interfaces, BGP peers
# and OSPF interface policy.
#
# These eleven tools shipped with no tests of any kind. They are also the
# tools the roadmap's "complete L3Out services" goal depends on most
# directly, so the numeric bounds below matter for real reasons rather than
# as generic hygiene: every one of them feeds a
# topology/pod-N/paths-M/pathep-[ethX/Y] DN or a protocol timer, where an
# out-of-range value produces a malformed DN or an unformed relation rather
# than a clean error.
# ---------------------------------------------------------------------------

def test_leaf_interface_profile_defaults_to_pod_one():
    """Single-pod is this fabric's reality and ACI's own default; pod_id
    still has to be explicit in the emitted DN, so it is defaulted rather
    than omitted."""
    req = CreateLeafInterfaceProfileRequest(location="Isolated Lab Site", name="Leaf101_Profile", node_id=101)
    assert req.pod_id == 1


@pytest.mark.parametrize("field", ["node_id", "pod_id"])
def test_leaf_interface_profile_rejects_zero_ids(field):
    kwargs = dict(location="Isolated Lab Site", name="Leaf101_Profile", node_id=101)
    kwargs[field] = 0
    with pytest.raises(ValidationError):
        CreateLeafInterfaceProfileRequest(**kwargs)


def test_interface_selector_requires_module_and_port():
    req = CreateInterfaceSelectorRequest(
        location="Isolated Lab Site",
        name="eth1-5",
        leaf_interface_profile="Leaf101_Profile",
        policy_group="ExtL3_IPG",
        module=1,
        port=5,
    )
    assert (req.module, req.port) == (1, 5)


@pytest.mark.parametrize("field", ["module", "port"])
def test_interface_selector_rejects_zero_module_or_port(field):
    kwargs = dict(
        location="Isolated Lab Site",
        name="eth1-5",
        leaf_interface_profile="Leaf101_Profile",
        policy_group="ExtL3_IPG",
        module=1,
        port=5,
    )
    kwargs[field] = 0
    with pytest.raises(ValidationError):
        CreateInterfaceSelectorRequest(**kwargs)


def test_static_path_binding_defaults():
    req = CreateStaticPathBindingRequest(
        tenant="sales",
        application_profile="eCommerce_AP",
        epg="Web_EPG",
        node_id=101,
        module=1,
        port=10,
        encap="vlan-11",
    )
    assert req.pod_id == 1
    assert req.mode == "regular"


@pytest.mark.parametrize("field", ["node_id", "module", "port", "pod_id"])
def test_static_path_binding_rejects_zero_path_components(field):
    kwargs = dict(
        tenant="sales",
        application_profile="eCommerce_AP",
        epg="Web_EPG",
        node_id=101,
        module=1,
        port=10,
        encap="vlan-11",
    )
    kwargs[field] = 0
    with pytest.raises(ValidationError):
        CreateStaticPathBindingRequest(**kwargs)


def test_protocol_l3out_request_defaults_to_no_external_epgs():
    req = CreateProtocolL3OutRequest(tenant="sales", name="BGP_L3Out", vrf="Presales_VRF", domain="ExtL3Dom")
    assert req.external_epgs == []
    assert req.description == ""


@pytest.mark.parametrize("bad_name", ["BGP L3Out", "BGP/L3Out", ""])
def test_invalid_protocol_l3out_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateProtocolL3OutRequest(tenant="sales", name=bad_name, vrf="Presales_VRF", domain="ExtL3Dom")


def test_l3out_node_and_interface_profile_requests_default_to_empty_children():
    """Both are containers -- children are added by the dedicated
    create_l3out_interface / create_bgp_peer tools rather than inline, so an
    empty default is the correct shape, not a missing one."""
    node_profile = CreateL3OutNodeProfileRequest(tenant="sales", l3out="BGP_L3Out", name="L101")
    interface_profile = CreateL3OutInterfaceProfileRequest(
        tenant="sales", l3out="BGP_L3Out", node_profile="L101", name="BGP_L3Out_interfaceProfile"
    )

    assert node_profile.nodes == []
    assert interface_profile.interfaces == []


def test_l3out_interface_defaults_to_routed_not_svi():
    """svi=False means main.tf emits if_inst_t 'l3-port' (or 'sub-interface'
    when a vlan is set), not 'ext-svi'. Defaulting to the routed case keeps
    an unqualified call producing the simpler, more common interface type."""
    req = CreateL3OutInterfaceRequest(
        tenant="sales",
        l3out="BGP_L3Out",
        node_profile="L101",
        interface_profile="BGP_L3Out_interfaceProfile",
        node_id=101,
        module=1,
        port=4,
    )
    assert req.svi is False
    assert req.vlan is None
    assert req.pod_id == 1
    assert req.mode == "regular"
    assert req.mtu == "inherit"


@pytest.mark.parametrize("bad_vlan", [0, 4095, 5000])
def test_l3out_interface_rejects_out_of_range_vlan(bad_vlan):
    """1-4094 is the real 802.1Q usable range; 4095 is reserved."""
    with pytest.raises(ValidationError):
        CreateL3OutInterfaceRequest(
            tenant="sales",
            l3out="BGP_L3Out",
            node_profile="L101",
            interface_profile="BGP_L3Out_interfaceProfile",
            node_id=101,
            module=1,
            port=4,
            svi=True,
            vlan=bad_vlan,
        )


def test_l3out_interface_accepts_an_svi_with_a_valid_vlan():
    req = CreateL3OutInterfaceRequest(
        tenant="sales",
        l3out="BGP_L3Out",
        node_profile="L101",
        interface_profile="BGP_L3Out_interfaceProfile",
        node_id=101,
        module=1,
        port=4,
        svi=True,
        vlan=51,
        ip="172.16.1.5/30",
    )
    assert (req.svi, req.vlan, req.ip) == (True, 51, "172.16.1.5/30")


def test_bgp_peer_request_defaults():
    """ttl=1 is correct for a directly-connected eBGP peer -- the common
    case for an ACI border-leaf L3Out. A multihop peer must raise it
    explicitly rather than inherit a permissive default."""
    req = CreateBgpPeerRequest(
        tenant="sales",
        l3out="BGP_L3Out",
        node_profile="L101",
        interface_profile="BGP_L3Out_interfaceProfile",
        interface_key="L101/BGP_L3Out_interfaceProfile",
        ip="172.16.1.6",
        remote_as=65002,
        local_as=65003,
    )
    assert req.ttl == 1
    assert req.admin_state is True
    assert req.weight == 0
    assert req.allowed_self_as_count == 0


@pytest.mark.parametrize("field,bad_value", [("remote_as", 0), ("local_as", 0), ("ttl", 0), ("weight", -1), ("allowed_self_as_count", -1)])
def test_bgp_peer_rejects_out_of_range_numeric_fields(field, bad_value):
    kwargs = dict(
        tenant="sales",
        l3out="BGP_L3Out",
        node_profile="L101",
        interface_profile="BGP_L3Out_interfaceProfile",
        interface_key="L101/BGP_L3Out_interfaceProfile",
        ip="172.16.1.6",
        remote_as=65002,
        local_as=65003,
    )
    kwargs[field] = bad_value
    with pytest.raises(ValidationError):
        CreateBgpPeerRequest(**kwargs)


def test_ospf_interface_request_defaults_to_backbone_area():
    req = CreateOspfInterfaceRequest(tenant="sales", l3out="OSPF_L3Out", interface_key="OSPF_NP/OSPF_IP")
    assert req.area == "0.0.0.0"
    assert req.area_type == "regular"
    assert req.name == "ospf"
    assert req.policy is None


def test_ospf_interface_policy_defaults_match_aci_broadcast_timers():
    """10s hello / 40s dead is ACI's own default for a broadcast network
    type; changing either without changing the other is a classic
    adjacency-breaking mistake, so both are pinned together."""
    req = CreateOspfInterfacePolicyRequest(tenant="sales", name="OSPF_bcast")
    assert req.network_type == "broadcast"
    assert req.hello_interval == 10
    assert req.dead_interval == 40
    assert req.passive is False


def test_ospf_interface_policy_carries_auth_by_reference_only():
    """SECURITY BOUNDARY -- this schema has no field capable of holding a
    raw authentication key. Only a non-secret reference (resolved from
    Vault at apply time) plus the key id can be supplied, so an OSPF MD5
    key can never reach Nautobot or the committed NetAsCode YAML. A future
    field named e.g. authentication_key would break this test, which is the
    point of asserting it."""
    req = CreateOspfInterfacePolicyRequest(
        tenant="sales",
        name="OSPF_p2p",
        network_type="point-to-point",
        authentication_type="md5",
        authentication_secret_ref="vault/aci/ospf/p2p",
        authentication_key_id=1,
    )

    assert req.authentication_secret_ref == "vault/aci/ospf/p2p"
    assert not any("key" == f or f.endswith("_key") for f in type(req).model_fields)


@pytest.mark.parametrize("field,bad_value", [("hello_interval", 0), ("dead_interval", 0), ("cost", 0), ("priority", -1), ("authentication_key_id", -1)])
def test_ospf_interface_policy_rejects_out_of_range_numeric_fields(field, bad_value):
    kwargs = {"tenant": "sales", "name": "OSPF_bcast", field: bad_value}
    with pytest.raises(ValidationError):
        CreateOspfInterfacePolicyRequest(**kwargs)


# ---------------------------------------------------------------------------
# L4-L7 / PBR gap closure (2026-09-15).
#
# Three gaps were found by auditing the layers against each other:
#   1. Terraform read `trunking`/`promiscuous_mode` from the YAML but no MCP
#      field or client argument could ever set them -- dead capability.
#   2. The Service Graph had no function node (Terraform side; see main.tf).
#   3. PBR had no health group, IP SLA, thresholds, or multi-destination.
# ---------------------------------------------------------------------------

def test_l4l7_device_exposes_trunking_and_promiscuous_mode():
    """Both default False and both reach the device. Terraform has always
    had `trunking`/`promiscuous_mode` lookups, but until this schema gained
    the fields there was no way to set them and both always resolved null."""
    req = CreateL4L7DeviceRequest(
        tenant="finance", name="fw", consumer_interface="inside",
        provider_interface="outside", vmm_domain="finance-vmm",
        trunking=True, promiscuous_mode=True,
    )
    assert req.trunking is True
    assert req.promiscuous_mode is True


def test_l4l7_device_trunking_and_promiscuous_default_off():
    req = CreateL4L7DeviceRequest(
        tenant="finance", name="fw", consumer_interface="inside", vmm_domain="finance-vmm"
    )
    assert req.trunking is False
    assert req.promiscuous_mode is False


def test_pbr_policy_shorthand_normalises_into_one_destination():
    """The original single-destination shape is kept as shorthand so existing
    callers keep working -- but it is normalised into `destinations` so the
    client only ever sees one shape."""
    req = CreatePbrPolicyRequest(tenant="finance", name="web-pbr", destination_ip="10.0.0.10", destination_mac="00:11:22:33:44:55")

    assert len(req.destinations) == 1
    assert req.destinations[0].ip == "10.0.0.10"
    assert req.destinations[0].mac == "00:11:22:33:44:55"


def test_pbr_policy_accepts_multiple_destinations():
    req = CreatePbrPolicyRequest(
        tenant="finance", name="web-pbr",
        destinations=[
            PbrDestinationSpec(ip="10.0.0.10", health_group="fw-hg"),
            PbrDestinationSpec(ip="10.0.0.11", health_group="fw-hg"),
        ],
    )
    assert [d.ip for d in req.destinations] == ["10.0.0.10", "10.0.0.11"]
    assert all(d.health_group == "fw-hg" for d in req.destinations)


def test_pbr_policy_rejects_both_shorthand_and_list():
    """Accepting both would leave the precedence ambiguous and silently drop
    one set of destinations."""
    with pytest.raises(ValidationError):
        CreatePbrPolicyRequest(
            tenant="finance", name="web-pbr", destination_ip="10.0.0.10",
            destinations=[PbrDestinationSpec(ip="10.0.0.11")],
        )


def test_pbr_policy_requires_at_least_one_destination():
    """A redirect policy with no destination redirects into nothing."""
    with pytest.raises(ValidationError):
        CreatePbrPolicyRequest(tenant="finance", name="web-pbr")


def test_pbr_policy_rejects_inverted_thresholds():
    with pytest.raises(ValidationError):
        CreatePbrPolicyRequest(
            tenant="finance", name="web-pbr", destination_ip="10.0.0.10",
            threshold_enable=True, min_threshold_percent=80, max_threshold_percent=20,
        )


def test_pbr_policy_accepts_ordered_thresholds_and_sla_reference():
    req = CreatePbrPolicyRequest(
        tenant="finance", name="web-pbr", destination_ip="10.0.0.10",
        threshold_enable=True, min_threshold_percent=20, max_threshold_percent=80,
        threshold_down_action="bypass", hashing_algorithm="sip-dip-prototype",
        ip_sla_policy="fw-icmp",
    )
    assert req.threshold_down_action == "bypass"
    assert req.ip_sla_policy == "fw-icmp"


@pytest.mark.parametrize("bad_pct", [-1, 101])
def test_pbr_policy_rejects_out_of_range_threshold_percent(bad_pct):
    with pytest.raises(ValidationError):
        CreatePbrPolicyRequest(tenant="finance", name="web-pbr", destination_ip="10.0.0.10", min_threshold_percent=bad_pct)


def test_pbr_destination_pod_id_must_be_positive():
    with pytest.raises(ValidationError):
        PbrDestinationSpec(ip="10.0.0.10", pod_id=0)


def test_pbr_health_group_request_defaults():
    req = CreatePbrHealthGroupRequest(tenant="finance", name="fw-hg")
    assert req.description == ""


@pytest.mark.parametrize("bad_name", ["fw hg", "fw/hg", ""])
def test_invalid_pbr_health_group_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreatePbrHealthGroupRequest(tenant="finance", name=bad_name)


def test_ip_sla_policy_defaults_to_icmp():
    """icmp needs no port, which is why it is the safe default."""
    req = CreateIpSlaPolicyRequest(tenant="finance", name="fw-icmp")
    assert req.sla_type == "icmp"
    assert req.port is None


def test_ip_sla_tcp_probe_requires_a_port():
    """A TCP probe with no port cannot be programmed -- ACI would reject it
    later, so it is refused here where the error is explainable."""
    with pytest.raises(ValidationError):
        CreateIpSlaPolicyRequest(tenant="finance", name="fw-tcp", sla_type="tcp")


def test_ip_sla_tcp_probe_with_a_port_is_accepted():
    req = CreateIpSlaPolicyRequest(tenant="finance", name="fw-tcp", sla_type="tcp", port=443, frequency=5, detect_multiplier=3)
    assert (req.port, req.frequency, req.detect_multiplier) == (443, 5, 3)


@pytest.mark.parametrize("bad_port", [0, 65536])
def test_ip_sla_rejects_out_of_range_port(bad_port):
    with pytest.raises(ValidationError):
        CreateIpSlaPolicyRequest(tenant="finance", name="fw-tcp", sla_type="tcp", port=bad_port)


def test_trunking_rejected_on_a_physical_device():
    """Trunking is a VMM port-group option. Setting it on a PHYSICAL device
    is accepted by APIC and then flagged invalid -- proven 2026-09-15 by an
    A/B probe of two identical PHYSICAL devices differing only in trunking,
    which isolated three faults caused solely by trunking=yes, led by
    'Configuration is invalid due to trunked port group option specified for
    physical device'. Refused here so the mistake never reaches a fault log
    nobody reads."""
    with pytest.raises(ValidationError):
        CreateL4L7DeviceRequest(
            tenant="finance", name="fw", consumer_interface="inside",
            device_type="PHYSICAL", physical_domain="phys-dom", trunking=True,
        )


def test_trunking_allowed_on_a_virtual_device():
    req = CreateL4L7DeviceRequest(
        tenant="finance", name="fw", consumer_interface="inside",
        device_type="VIRTUAL", vmm_domain="finance-vmm", trunking=True,
    )
    assert req.trunking is True


def test_physical_device_without_trunking_is_accepted():
    req = CreateL4L7DeviceRequest(
        tenant="finance", name="fw", consumer_interface="inside",
        device_type="PHYSICAL", physical_domain="phys-dom", trunking=False,
    )
    assert req.device_type.upper() == "PHYSICAL"
    assert req.trunking is False


def test_physical_device_requires_a_physical_domain():
    """The provider makes relation_vns_rs_al_dev_to_phys_dom_p mandatory for
    PHYSICAL and fails at PLAN time without it. Terraform and the YAML gained
    `physical_domain` on 2026-09-15 but the MCP schema did not, so a physical
    device created through the tool silently had no domain -- Pydantic drops
    unknown fields -- and then failed the provider check. Same silent-drop
    shape as an undeclared Nautobot Custom Field."""
    with pytest.raises(ValidationError):
        CreateL4L7DeviceRequest(
            tenant="finance", name="fw", consumer_interface="inside", device_type="PHYSICAL"
        )


def test_virtual_device_still_requires_a_vmm_domain():
    """Regression guard: the physical rule was added to the same validator
    that enforces the virtual one."""
    with pytest.raises(ValidationError):
        CreateL4L7DeviceRequest(
            tenant="finance", name="fw", consumer_interface="inside", device_type="VIRTUAL"
        )


# ---------------------------------------------------------------------------
# VMM Domain without a Controller (2026-09-15).
#
# The Controller is the only object in the VMM chain that actually reaches
# vCenter -- APIC connects, authenticates, and builds a DVS there. A domain
# alone is inert, which is exactly what you want when modelling a VMM-backed
# L4-L7 device on a fabric whose vCenter is unreachable, or when a DVS must
# not be created yet.
# ---------------------------------------------------------------------------

def test_vmm_domain_can_be_created_with_no_controller():
    req = CreateVmmDomainRequest(name="vCenter_VMM", vlan_pool="vCenter_VMM_Pool")

    assert req.controller_name is None
    assert req.host_or_ip is None
    assert req.root_cont_name is None


def test_vmm_domain_with_a_full_controller_is_still_accepted():
    req = CreateVmmDomainRequest(
        name="vCenter_VMM", controller_name="vCenter", host_or_ip="192.168.10.62", root_cont_name="DC"
    )
    assert req.host_or_ip == "192.168.10.62"


@pytest.mark.parametrize(
    "partial",
    [
        {"controller_name": "vCenter"},
        {"host_or_ip": "192.168.10.62"},
        {"root_cont_name": "DC"},
        {"controller_name": "vCenter", "host_or_ip": "192.168.10.62"},
    ],
)
def test_partial_vmm_controller_is_rejected(partial):
    """ACI needs controller name, host and datacenter together. A partial set
    is always a mistake -- and silently emitting it would produce a
    controller that can never connect."""
    with pytest.raises(ValidationError):
        CreateVmmDomainRequest(name="vCenter_VMM", **partial)


def test_credential_without_a_controller_is_rejected():
    """A credential exists to authenticate the controller's vCenter login.
    Without a controller it authenticates nothing."""
    with pytest.raises(ValidationError):
        CreateVmmDomainRequest(name="vCenter_VMM", credential_name="vCenter_Creds")


# ---------------------------------------------------------------------------
# Concrete devices (vnsCDev) -- 2026-09-15.
#
# A logical L4-L7 device with nothing behind it is not deployable: APIC marks
# it invalid with vnsConfIssue-missing-cdev and the whole service graph above
# it inherits the fault. These tests pin the rules that were MEASURED against
# the lab APIC, not assumed.
# ---------------------------------------------------------------------------

def _virtual_iface(**overrides):
    base = {"name": "cif1", "logical_interface": "db_int", "vnic_name": "Network adapter 2"}
    base.update(overrides)
    return base


def _physical_iface(**overrides):
    base = {"name": "eth1", "logical_interface": "consumer", "node_id": 101, "port": 30}
    base.update(overrides)
    return base


def test_valid_virtual_concrete_device():
    req = CreateConcreteDeviceRequest(
        tenant="ACI:acme", device="FW", name="ASAv_cdev",
        vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
        interfaces=[_virtual_iface(), _virtual_iface(name="cif2", logical_interface="backup_int",
                                                     vnic_name="Network adapter 3")],
    )

    assert req.device_type == "VIRTUAL"
    assert req.vendor == "VMware"
    assert [i.name for i in req.interfaces] == ["cif1", "cif2"]
    assert req.interfaces[0].node_id is None


def test_valid_physical_concrete_device():
    req = CreateConcreteDeviceRequest(
        tenant="ACI:acme", device="FW", name="fw1", device_type="PHYSICAL",
        interfaces=[_physical_iface()],
    )

    assert req.interfaces[0].pod_id == 1
    assert req.interfaces[0].module == 1
    assert req.interfaces[0].vnic_name is None


@pytest.mark.parametrize("missing", ["vm_name", "vmm_domain", "vmm_controller"])
def test_virtual_concrete_device_requires_vcenter_identity(missing):
    """Measured 2026-09-15: a concrete device on a CONTROLLER-LESS VMM domain
    does not reduce the fault count -- it holds at 10 and trades them for
    F1778/F0765. Refusing the combination stops a caller building the
    strictly worse configuration."""
    kwargs = {
        "tenant": "ACI:acme", "device": "FW", "name": "ASAv_cdev",
        "vm_name": "ASAv-1", "vmm_domain": "vCenter_VMM", "vmm_controller": "vCenter",
        "interfaces": [_virtual_iface()],
    }
    kwargs[missing] = None

    with pytest.raises(ValidationError, match=missing):
        CreateConcreteDeviceRequest(**kwargs)


def test_virtual_concrete_device_rejects_a_leaf_path():
    with pytest.raises(ValidationError, match="need vnic_name"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="ASAv_cdev",
            vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
            interfaces=[_physical_iface()],
        )


def test_physical_concrete_device_rejects_a_vnic():
    with pytest.raises(ValidationError, match="need node_id and port"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="fw1", device_type="PHYSICAL",
            interfaces=[_virtual_iface()],
        )


@pytest.mark.parametrize("field", ["vm_name", "vmm_controller"])
def test_physical_concrete_device_rejects_virtual_only_fields(field):
    with pytest.raises(ValidationError, match="VIRTUAL-only field"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="fw1", device_type="PHYSICAL",
            interfaces=[_physical_iface()], **{field: "something"},
        )


def test_concrete_interface_cannot_be_identified_two_ways():
    with pytest.raises(ValidationError, match="not both"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="ASAv_cdev",
            vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
            interfaces=[_virtual_iface(node_id=101, port=30)],
        )


def test_concrete_interface_needs_some_identification():
    with pytest.raises(ValidationError, match="vnic name is missing in CIf"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="ASAv_cdev",
            vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
            interfaces=[{"name": "cif1", "logical_interface": "db_int"}],
        )


def test_physical_path_needs_both_node_and_port():
    with pytest.raises(ValidationError, match="BOTH"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="fw1", device_type="PHYSICAL",
            interfaces=[{"name": "eth1", "logical_interface": "consumer", "node_id": 101}],
        )


def test_concrete_device_needs_at_least_one_interface():
    with pytest.raises(ValidationError, match="at least one concrete interface"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="ASAv_cdev",
            vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
            interfaces=[],
        )


def test_duplicate_concrete_interface_names_rejected():
    with pytest.raises(ValidationError, match="duplicate concrete interface"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="ASAv_cdev",
            vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
            interfaces=[_virtual_iface(), _virtual_iface(logical_interface="backup_int")],
        )


def test_unknown_concrete_device_type_rejected():
    with pytest.raises(ValidationError, match="must be VIRTUAL or PHYSICAL"):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name="fw1", device_type="CONTAINER",
            interfaces=[_physical_iface()],
        )


@pytest.mark.parametrize("bad_name", ["bad name", "bad/name", ""])
def test_invalid_concrete_device_name_rejected(bad_name):
    with pytest.raises(ValidationError):
        CreateConcreteDeviceRequest(
            tenant="ACI:acme", device="FW", name=bad_name, device_type="PHYSICAL",
            interfaces=[_physical_iface()],
        )


# ---------------------------------------------------------------------------
# L3Out Logical Interface Profile sub-policies (2026-09-16).
#
# The rules pinned here were MEASURED against the lab APIC, not assumed --
# in particular the two that a reasonable person would get wrong: these
# relations take a DN rather than a name, and the literal string "default"
# is rejected rather than selecting APIC's built-in default.
# ---------------------------------------------------------------------------

def _bind(**overrides):
    base = {"tenant": "ACI:acme", "l3out": "Edge", "node_profile": "NP",
            "interface_profile": "IP", "nd_interface_policy": "ND_Pol"}
    base.update(overrides)
    return base


def test_valid_nd_interface_policy_leaves_unset_attributes_alone():
    req = CreateNdInterfacePolicyRequest(tenant="ACI:acme", name="ND_Pol", hop_limit=64)

    assert req.hop_limit == 64
    assert req.mtu is None, "an unset attribute must stay None so APIC applies its own default"


@pytest.mark.parametrize("bad_mtu", [1279, 9217])
def test_nd_policy_rejects_an_mtu_outside_the_ipv6_range(bad_mtu):
    """1280 is the IPv6 minimum; APIC would take a smaller value and produce
    an interface that cannot carry IPv6."""
    with pytest.raises(ValidationError):
        CreateNdInterfacePolicyRequest(tenant="ACI:acme", name="ND_Pol", mtu=bad_mtu)


def test_nd_policy_rejects_a_hop_limit_above_255():
    with pytest.raises(ValidationError):
        CreateNdInterfacePolicyRequest(tenant="ACI:acme", name="ND_Pol", hop_limit=256)


def test_valid_dpp_policy():
    req = CreateDppPolicyRequest(
        tenant="ACI:acme", name="Ingress_100M", rate=100, rate_unit="mega",
        burst=200, burst_unit="mega", conform_action="transmit", exceed_action="drop",
    )

    assert (req.rate, req.rate_unit) == (100, "mega")


@pytest.mark.parametrize(
    "value_field,unit_field",
    [("rate", "rate_unit"), ("burst", "burst_unit"),
     ("peak_rate", "peak_rate_unit"), ("excessive_burst", "excessive_burst_unit")],
)
def test_dpp_rate_without_its_unit_is_rejected(value_field, unit_field):
    """`rate: 100` could be 100 bps or 100 Gbps -- APIC silently picks its own
    default unit, which is never what a caller specifying a rate meant."""
    with pytest.raises(ValidationError, match=unit_field):
        CreateDppPolicyRequest(tenant="ACI:acme", name="P", **{value_field: 100})


def test_dpp_unit_without_a_value_is_allowed():
    """Only the value implies the unit, not the other way round -- a lone unit
    is harmless and APIC ignores it."""
    req = CreateDppPolicyRequest(tenant="ACI:acme", name="P", rate_unit="mega")

    assert req.rate is None


def test_pim_policy_has_no_field_that_could_carry_an_auth_key():
    """Same rule as create_ospf_interface_policy: a shared secret must never
    reach Nautobot or the committed YAML. pimIfPol supports one; this schema
    deliberately does not."""
    fields = set(CreatePimInterfacePolicyRequest.model_fields)

    assert "auth_key" not in fields
    assert not [f for f in fields if "key" in f.lower() or "password" in f.lower()]
    assert "auth_type" in fields, "the type is not a secret and stays configurable"


def test_valid_igmp_interface_policy():
    req = CreateIgmpInterfacePolicyRequest(
        tenant="ACI:acme", name="IGMP_v3", version="v3", query_interval=125
    )

    assert req.version == "v3"
    assert req.group_timeout is None


def test_valid_custom_qos_policy():
    req = CreateCustomQosPolicyRequest(
        tenant="ACI:acme", name="CQos",
        dscp_to_priority_maps=[{"from": "EF", "to": "EF", "priority": "level1"}],
    )

    assert len(req.dscp_to_priority_maps) == 1


def test_custom_qos_policy_with_no_mappings_is_rejected():
    """A classifier that classifies nothing is almost certainly a mistake."""
    with pytest.raises(ValidationError, match="classifies nothing"):
        CreateCustomQosPolicyRequest(tenant="ACI:acme", name="CQos")


def test_valid_interface_profile_policy_binding():
    req = BindL3OutInterfaceProfilePoliciesRequest(**_bind(
        qos_priority="level3", ingress_dpp_policy="In", egress_dpp_policy="Out"
    ))

    assert req.qos_priority == "level3"
    assert req.pim_interface_policy is None


def test_binding_nothing_is_rejected():
    with pytest.raises(ValidationError, match="nothing to bind"):
        BindL3OutInterfaceProfilePoliciesRequest(
            tenant="ACI:acme", l3out="Edge", node_profile="NP", interface_profile="IP"
        )


@pytest.mark.parametrize(
    "field",
    ["nd_interface_policy", "ingress_dpp_policy", "egress_dpp_policy",
     "pim_interface_policy", "pim_v6_interface_policy", "igmp_interface_policy",
     "custom_qos_policy"],
)
def test_the_literal_default_is_rejected_on_every_relation(field):
    """Measured 2026-09-16: the provider resolves the name inside the OWNING
    tenant, so `default` fails the apply with "Relation target dn default not
    found". The way to inherit APIC's built-in default is to omit the field.
    Catching it here turns a 20-minute apply failure into an instant one."""
    payload = {"tenant": "ACI:acme", "l3out": "Edge", "node_profile": "NP",
               "interface_profile": "IP", field: "default"}

    with pytest.raises(ValidationError, match="omit the field"):
        BindL3OutInterfaceProfilePoliciesRequest(**payload)


def test_a_full_dn_is_accepted_as_a_policy_reference():
    """The documented escape hatch for pointing at a policy this platform does
    not manage -- main.tf passes a uni/... value straight through."""
    req = BindL3OutInterfaceProfilePoliciesRequest(**_bind(
        nd_interface_policy="uni/tn-common/ndifpol-default"
    ))

    assert req.nd_interface_policy.startswith("uni/")


# ---------------------------------------------------------------------------
# Route control / route maps (2026-09-16).
#
# The rules pinned here were learned by applying, not by reading the schema.
# Two in particular: an ACI route map ends in an implicit deny, so an empty or
# unmatched map silently advertises NOTHING; and a custom-named map is inert
# until something references it.
# ---------------------------------------------------------------------------

def _ctx(**over):
    base = {"name": "permit-explicit", "order": 0, "action": "permit",
            "match_rule": "match-permit-prefix-out"}
    base.update(over)
    return base


def test_valid_match_rule_defaults_match_the_apic_ui():
    """Screenshots 1 and 3 show Aggregate=False and both mask bounds 0 --
    the APIC defaults. The schema must produce the same without being told."""
    req = CreateMatchRuleRequest(
        tenant="ACI:acme", name="match-permit-prefix-out",
        prefixes=[{"ip": "172.16.200.200/32"}],
    )

    p0 = req.prefixes[0]
    assert (p0.aggregate, p0.greater_than_mask, p0.less_than_mask) == (False, 0, 0)


def test_match_rule_with_no_prefixes_is_rejected():
    """A rule matching nothing, inside a map ending in an implicit deny,
    drops every route without any error."""
    with pytest.raises(ValidationError, match="matches nothing"):
        CreateMatchRuleRequest(tenant="ACI:acme", name="empty", prefixes=[])


def test_mask_bounds_must_be_ordered():
    with pytest.raises(ValidationError, match="never match"):
        CreateMatchRuleRequest(
            tenant="ACI:acme", name="r",
            prefixes=[{"ip": "10.0.0.0/8", "greater_than_mask": 24, "less_than_mask": 16}],
        )


def test_valid_route_control_profile_defaults_to_match_routing_policy_only():
    """Screenshot 2 selects 'Match Routing Policy Only', which is type=global."""
    req = CreateRouteControlProfileRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", name="Uni-Route-Profile-OUT",
        contexts=[_ctx(), _ctx(name="explicit-deny-out", order=1, action="deny",
                        match_rule="deny-prefix-out")],
    )

    assert req.type == "global"
    assert [(c.order, c.action) for c in req.contexts] == [(0, "permit"), (1, "deny")]


def test_route_map_with_no_contexts_is_rejected():
    with pytest.raises(ValidationError, match="permits nothing"):
        CreateRouteControlProfileRequest(
            tenant="ACI:acme", l3out="OSPF_L3Out", name="rm", contexts=[]
        )


def test_duplicate_context_order_is_rejected():
    """In a permit/deny list the order IS the meaning, so two contexts sharing
    an order is not a cosmetic problem."""
    with pytest.raises(ValidationError, match="used more than once"):
        CreateRouteControlProfileRequest(
            tenant="ACI:acme", l3out="OSPF_L3Out", name="rm",
            contexts=[_ctx(order=0), _ctx(name="other", order=0)],
        )


def test_duplicate_context_name_is_rejected():
    with pytest.raises(ValidationError, match="duplicate context name"):
        CreateRouteControlProfileRequest(
            tenant="ACI:acme", l3out="OSPF_L3Out", name="rm",
            contexts=[_ctx(order=0), _ctx(order=1)],
        )


@pytest.mark.parametrize("bad", ["allow", "block", "PERMIT_ALL", ""])
def test_context_action_must_be_permit_or_deny(bad):
    with pytest.raises(ValidationError):
        CreateRouteControlProfileRequest(
            tenant="ACI:acme", l3out="OSPF_L3Out", name="rm",
            contexts=[_ctx(action=bad)],
        )


def test_context_action_is_case_normalised():
    req = CreateRouteControlProfileRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", name="rm", contexts=[_ctx(action="Permit")]
    )

    assert req.contexts[0].action == "permit"


@pytest.mark.parametrize("bad_type", ["Global", "match-routing-policy-only", "aggregate"])
def test_unknown_route_map_type_is_rejected(bad_type):
    with pytest.raises(ValidationError, match="global"):
        CreateRouteControlProfileRequest(
            tenant="ACI:acme", l3out="OSPF_L3Out", name="rm",
            contexts=[_ctx()], type=bad_type,
        )


def test_a_context_may_omit_its_match_rule():
    """A context with no match rule matches everything -- as a final deny that
    is how you make ACI's implicit deny explicit."""
    req = CreateRouteControlProfileRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", name="rm",
        contexts=[_ctx(name="catch-all-deny", order=9, action="deny", match_rule=None)],
    )

    assert req.contexts[0].match_rule is None


@pytest.mark.parametrize("direction", ["export", "import"])
def test_valid_route_map_binding(direction):
    req = BindExternalEpgRouteControlProfileRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
        route_control_profile="Uni-Route-Profile-OUT", direction=direction,
    )

    assert req.direction == direction


def test_binding_direction_must_be_export_or_import():
    with pytest.raises(ValidationError, match="export"):
        BindExternalEpgRouteControlProfileRequest(
            tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
            route_control_profile="rm", direction="both",
        )


def test_valid_subnet_scope_change():
    req = SetExternalEpgSubnetScopeRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
        ip="172.16.200.200/32", scope=["import-security"],
    )

    assert req.scope == ["import-security"]


def test_empty_subnet_scope_is_rejected():
    """ACI rejects an external EPG subnet carrying no scope flags at all."""
    with pytest.raises(ValidationError, match="cannot be empty"):
        SetExternalEpgSubnetScopeRequest(
            tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
            ip="172.16.200.200/32", scope=[],
        )


def test_unknown_subnet_scope_value_is_rejected():
    with pytest.raises(ValidationError, match="unknown scope"):
        SetExternalEpgSubnetScopeRequest(
            tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
            ip="172.16.200.200/32", scope=["export-route-control"],
        )


# ---------------------------------------------------------------------------
# Transit-lab corrections (2026-09-16).
# ---------------------------------------------------------------------------

def test_external_epg_contract_binding_needs_something_to_bind():
    with pytest.raises(ValidationError, match="at least one provided or consumed"):
        BindExternalEpgContractRequest(tenant="t", l3out="o", external_epg="e")


def test_external_epg_contract_binding_accepts_either_direction():
    req = BindExternalEpgContractRequest(
        tenant="t", l3out="o", external_epg="e", provided_contracts=["C"]
    )
    assert req.consumed_contracts == []


def test_added_external_epg_subnet_defaults_to_the_contract_classification():
    """import-security is External Subnets for the External EPG -- what a
    contract matches on. Defaulting to anything else would silently make the
    subnet invisible to contracts."""
    req = AddExternalEpgSubnetRequest(tenant="t", l3out="o", external_epg="e",
                                      ip="172.16.199.199/32")
    assert req.scope == ["import-security"]


def test_added_external_epg_subnet_rejects_an_unknown_scope():
    with pytest.raises(ValidationError, match="unknown scope"):
        AddExternalEpgSubnetRequest(tenant="t", l3out="o", external_epg="e",
                                    ip="1.1.1.1/32", scope=["bogus"])


def test_match_rule_prefix_defaults_match_the_apic_ui():
    req = AddMatchRulePrefixRequest(tenant="t", match_rule="deny-prefix-out",
                                    ip="172.16.199.199/32")
    assert (req.aggregate, req.greater_than_mask, req.less_than_mask) == (False, 0, 0)


def test_l3_domain_vlan_pool_is_optional_but_meaningful():
    assert CreateL3DomainRequest(name="ExtL3Dom").vlan_pool is None
    assert CreateL3DomainRequest(name="ExtL3Dom", vlan_pool="P").vlan_pool == "P"


def test_aep_accepts_a_bare_string_and_a_typed_domain():
    """A physical domain and an L3 domain can share a name, so the type cannot
    be inferred -- but a bare string must keep working for existing callers."""
    req = CreateAepRequest(name="A", domains=["PhysDom", {"name": "ExtL3Dom", "type": "l3"}])
    assert req.domains[0] == "PhysDom"
    assert isinstance(req.domains[1], AepDomainSpec)
    assert req.domains[1].type == "l3"


@pytest.mark.parametrize("bad", ["vmm", "L3", "external"])
def test_aep_domain_type_must_be_physical_or_l3(bad):
    with pytest.raises(ValidationError):
        CreateAepRequest(name="A", domains=[{"name": "d", "type": bad}])
