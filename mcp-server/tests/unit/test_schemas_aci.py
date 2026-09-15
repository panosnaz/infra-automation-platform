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
    assert req.location == "ACI-Lab"
    assert req.alloc_mode == "static"
    assert req.role == "external"
    assert req.range_alloc_mode is None


@pytest.mark.parametrize("bad_vid", [0, 4095])
def test_vlan_pool_range_out_of_bounds_rejected(bad_vid):
    with pytest.raises(ValidationError):
        CreateVlanPoolRequest(name="pool1", range_from=bad_vid, range_to=200)


def test_valid_physical_domain_request_defaults():
    req = CreatePhysicalDomainRequest(name="phys-dom1")
    assert req.location == "ACI-Lab"
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
    assert req.location == "ACI-Lab"
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
    assert req.location == "ACI-Lab"
    assert req.description == ""


def test_valid_local_user_request_defaults():
    req = CreateLocalUserRequest(name="phase-f-user")
    assert req.location == "ACI-Lab"
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
    assert req.location == "Isolated Lab Site"
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
