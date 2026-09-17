"""Unit tests for tools/aci.py's business logic -- no live Nautobot needed.

Uses a lightweight fake NautobotClient double (duck-typed, registry.py's
dispatcher has no isinstance check) instead of mocking pynautobot's HTTP
layer -- these tests exist to catch regressions in what the tool *does*
with NautobotClient's return value (namespacing, field pass-through,
response shape), not to re-test NautobotClient itself.

This is the layer that had two real bugs caught only by live testing
during ADR-020 development (create_vrf missing a namespace, create_
bridge_domain embedding the raw 'ACI:' prefixed tenant name in its
description) -- these tests exist so a regression here is caught for
free next time, not only by re-running live verification.
"""
from __future__ import annotations

from mcp_server.schemas.aci import (
    BindEpgContractRequest,
    BindEpgDomainRequest,
    CreateAccessPortBlockRequest,
    CreateAccessPortProfileRequest,
    CreateAccessPortSelectorRequest,
    CreateAepRequest,
    CreateBgpPeerRequest,
    CreateBridgeDomainRequest,
    CreateContractSubjectRequest,
    CreateEpgRequest,
    CreateFabricDeviceRequest,
    CreateFabricInterfaceRequest,
    CreateFilterEntryRequest,
    CreateFilterRequest,
    CreateInterfaceSelectorRequest,
    CreateL3OutInterfaceProfileRequest,
    CreateL3OutInterfaceRequest,
    CreateL3OutNodeProfileRequest,
    BindExternalEpgRouteControlProfileRequest,
    BindL3OutInterfaceProfilePoliciesRequest,
    AddExternalEpgSubnetRequest,
    AddMatchRulePrefixRequest,
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
    CreateLeafInterfaceProfileRequest,
    CreateLeafNodeBlockRequest,
    CreateLeafProfileRequest,
    CreateLeafSelectorRequest,
    CreateOspfInterfacePolicyRequest,
    CreateOspfInterfaceRequest,
    CreateProtocolL3OutRequest,
    CreateStaticPathBindingRequest,
    CreateIpSlaPolicyRequest,
    CreatePbrHealthGroupRequest,
    PbrDestinationSpec,
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
)
from mcp_server.tools.aci import (
    bind_epg_contract,
    bind_epg_domain,
    create_access_port_block,
    create_access_port_profile,
    create_access_port_selector,
    create_aep,
    create_bgp_l3out,
    create_bgp_peer,
    create_bridge_domain,
    create_contract_subject,
    create_epg,
    create_fabric_device,
    create_fabric_interface,
    create_filter,
    create_filter_entry,
    create_interface_selector,
    create_l3out_interface,
    create_l3out_interface_profile,
    create_l3out_node_profile,
    bind_external_epg_route_control_profile,
    bind_l3out_interface_profile_policies,
    add_external_epg_subnet,
    add_match_rule_prefix,
    bind_external_epg_contract,
    create_l3_domain,
    create_match_rule,
    create_route_control_profile,
    set_external_epg_subnet_scope,
    create_concrete_device,
    create_custom_qos_policy,
    create_dpp_policy,
    create_igmp_interface_policy,
    create_nd_interface_policy,
    create_pim_interface_policy,
    create_l4l7_device,
    create_leaf_interface_policy_group,
    create_leaf_interface_profile,
    create_leaf_node_block,
    create_leaf_profile,
    create_leaf_selector,
    create_ospf_interface,
    create_ospf_interface_policy,
    create_ospf_l3out,
    create_static_path_binding,
    create_ip_sla_policy,
    create_pbr_health_group,
    create_local_user,
    create_one_arm_service_graph,
    create_pbr_contract,
    create_pbr_policy,
    create_physical_domain,
    create_pod_policy_group,
    create_security_domain,
    create_service_graph,
    create_tenant,
    create_vlan_pool,
    create_vmm_domain,
    create_vrf,
    create_vrf_route_leak,
)


class _FakeNautobotClient:
    """Records every call it receives; returns a fixed fixture dict."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def create_tenant(self, **kwargs):
        self.calls.append(("create_tenant", kwargs))
        return {"id": "tenant-id", **kwargs}

    def create_filter(self, **kwargs):
        self.calls.append(("create_filter", kwargs))
        return {"tenant": kwargs["tenant"], "filter": kwargs["name"], "entries": kwargs["entries"]}

    def create_filter_entry(self, **kwargs):
        self.calls.append(("create_filter_entry", kwargs))
        return {"tenant": kwargs["tenant"], "filter": kwargs["filter_name"], "entries": [kwargs["entry"]]}

    def create_contract_subject(self, **kwargs):
        self.calls.append(("create_contract_subject", kwargs))
        return {"tenant": kwargs["tenant"], "contract": kwargs["contract"], "subjects": [kwargs["subject"]]}

    def bind_epg_contract(self, **kwargs):
        self.calls.append(("bind_epg_contract", kwargs))
        return {"tenant": kwargs["tenant"], "epg": kwargs["epg"], "provided": [], "consumed": []}

    def create_vrf(self, **kwargs):
        self.calls.append(("create_vrf", kwargs))
        return {"id": "vrf-id", **kwargs}

    def create_bridge_domain(self, **kwargs):
        self.calls.append(("create_bridge_domain", kwargs))
        return {"id": "prefix-id", **kwargs}

    def create_epg(self, **kwargs):
        self.calls.append(("create_epg", kwargs))
        return {"id": "vlan-id", **kwargs}

    def create_vlan_pool(self, **kwargs):
        self.calls.append(("create_vlan_pool", kwargs))
        return {"location": kwargs["location"], "vlan_pool": kwargs["name"], "vlan_pools": []}

    def create_physical_domain(self, **kwargs):
        self.calls.append(("create_physical_domain", kwargs))
        return {"location": kwargs["location"], "physical_domain": kwargs["name"], "physical_domains": []}

    def create_aep(self, **kwargs):
        self.calls.append(("create_aep", kwargs))
        return {"location": kwargs["location"], "aep": kwargs["name"], "aeps": []}

    def create_leaf_interface_policy_group(self, **kwargs):
        self.calls.append(("create_leaf_interface_policy_group", kwargs))
        return {"location": kwargs["location"], "leaf_interface_policy_group": kwargs["name"], "leaf_interface_policy_groups": []}

    def create_pod_policy_group(self, **kwargs):
        self.calls.append(("create_pod_policy_group", kwargs))
        return {"location": kwargs["location"], "pod_policy_group": kwargs["name"], "pod_policy_groups": []}

    def create_security_domain(self, **kwargs):
        self.calls.append(("create_security_domain", kwargs))
        return {"location": kwargs["location"], "security_domain": kwargs["name"], "security_domains": []}

    def create_local_user(self, **kwargs):
        self.calls.append(("create_local_user", kwargs))
        return {"location": kwargs["location"], "local_user": kwargs["name"], "local_users": []}

    def bind_external_epg_contract(self, **kwargs):
        self.calls.append(("bind_external_epg_contract", kwargs))
        return dict(kwargs)

    def add_external_epg_subnet(self, **kwargs):
        self.calls.append(("add_external_epg_subnet", kwargs))
        return dict(kwargs)

    def add_match_rule_prefix(self, **kwargs):
        self.calls.append(("add_match_rule_prefix", kwargs))
        return dict(kwargs)

    def create_l3_domain(self, **kwargs):
        self.calls.append(("create_l3_domain", kwargs))
        return dict(kwargs)

    def create_match_rule(self, **kwargs):
        self.calls.append(("create_match_rule", kwargs))
        return {"tenant": kwargs["tenant"], "match_rule": kwargs["name"]}

    def create_route_control_profile(self, **kwargs):
        self.calls.append(("create_route_control_profile", kwargs))
        return {"tenant": kwargs["tenant"], "route_control_profile": kwargs["name"]}

    def bind_external_epg_route_control_profile(self, **kwargs):
        self.calls.append(("bind_external_epg_route_control_profile", kwargs))
        return dict(kwargs)

    def set_external_epg_subnet_scope(self, **kwargs):
        self.calls.append(("set_external_epg_subnet_scope", kwargs))
        return {**kwargs, "previous_scope": ["export-rtctrl"]}

    def create_nd_interface_policy(self, **kwargs):
        self.calls.append(("create_nd_interface_policy", kwargs))
        return {"tenant": kwargs["tenant"], "policy": kwargs["name"]}

    def create_dpp_policy(self, **kwargs):
        self.calls.append(("create_dpp_policy", kwargs))
        return {"tenant": kwargs["tenant"], "policy": kwargs["name"]}

    def create_pim_interface_policy(self, **kwargs):
        self.calls.append(("create_pim_interface_policy", kwargs))
        return {"tenant": kwargs["tenant"], "policy": kwargs["name"]}

    def create_igmp_interface_policy(self, **kwargs):
        self.calls.append(("create_igmp_interface_policy", kwargs))
        return {"tenant": kwargs["tenant"], "policy": kwargs["name"]}

    def create_custom_qos_policy(self, **kwargs):
        self.calls.append(("create_custom_qos_policy", kwargs))
        return {"tenant": kwargs["tenant"], "policy": kwargs["name"]}

    def bind_l3out_interface_profile_policies(self, **kwargs):
        self.calls.append(("bind_l3out_interface_profile_policies", kwargs))
        bound = {k: v for k, v in kwargs.items()
                 if k not in ("tenant", "l3out", "node_profile", "interface_profile") and v}
        return {"tenant": kwargs["tenant"], "bound": bound, "profile": {}}

    def create_concrete_device(self, **kwargs):
        self.calls.append(("create_concrete_device", kwargs))
        return {"tenant": kwargs["tenant"], "device": kwargs["device"],
                "concrete_device": kwargs["name"], "concrete_devices": [], "logical_interfaces": []}

    def create_vmm_domain(self, **kwargs):
        self.calls.append(("create_vmm_domain", kwargs))
        return {"location": kwargs["location"], "vmm_domain": kwargs["name"], "vmm_domains": []}

    def bind_epg_domain(self, **kwargs):
        self.calls.append(("bind_epg_domain", kwargs))
        return {
            "tenant": kwargs["tenant"],
            "application_profile": kwargs["application_profile"],
            "epg": kwargs["epg"],
            "domains": [],
        }

    def create_l4l7_device(self, **kwargs):
        self.calls.append(("create_l4l7_device", kwargs))
        return {"id": "device-id", **kwargs}

    def create_service_graph(self, **kwargs):
        self.calls.append(("create_service_graph", kwargs))
        return {"id": "graph-id", **kwargs}

    def create_pbr_health_group(self, **kwargs):
        self.calls.append(("create_pbr_health_group", kwargs))
        return {"tenant": kwargs["tenant"], "health_group": kwargs["name"], "health_groups": []}

    def create_ip_sla_policy(self, **kwargs):
        self.calls.append(("create_ip_sla_policy", kwargs))
        return {"tenant": kwargs["tenant"], "ip_sla_policy": kwargs["name"], "ip_sla_policies": []}

    def create_pbr_policy(self, **kwargs):
        self.calls.append(("create_pbr_policy", kwargs))
        return {"id": "policy-id", **kwargs}

    def create_pbr_contract(self, **kwargs):
        self.calls.append(("create_pbr_contract", kwargs))
        return {"id": "contract-id", **kwargs}

    def create_one_arm_service_graph(self, **kwargs):
        self.calls.append(("create_one_arm_service_graph", kwargs))
        return {"id": "one-arm-graph-id", **kwargs}

    def create_vrf_route_leak(self, **kwargs):
        self.calls.append(("create_vrf_route_leak", kwargs))
        return {"id": "route-leak-id", **kwargs}

    # XML-compatible access hierarchy + DCIM fabric inventory. Each handler
    # is a thin pass-through (`nautobot.create_X(**request.model_dump())`),
    # so the fixture only needs to echo what it received back.
    def create_access_port_profile(self, **kwargs):
        self.calls.append(("create_access_port_profile", kwargs))
        return {"id": "access-port-profile-id", **kwargs}

    def create_access_port_selector(self, **kwargs):
        self.calls.append(("create_access_port_selector", kwargs))
        return {"id": "access-port-selector-id", **kwargs}

    def create_access_port_block(self, **kwargs):
        self.calls.append(("create_access_port_block", kwargs))
        return {"id": "access-port-block-id", **kwargs}

    def create_leaf_profile(self, **kwargs):
        self.calls.append(("create_leaf_profile", kwargs))
        return {"id": "leaf-profile-id", **kwargs}

    def create_leaf_selector(self, **kwargs):
        self.calls.append(("create_leaf_selector", kwargs))
        return {"id": "leaf-selector-id", **kwargs}

    def create_leaf_node_block(self, **kwargs):
        self.calls.append(("create_leaf_node_block", kwargs))
        return {"id": "leaf-node-block-id", **kwargs}

    def create_fabric_device(self, **kwargs):
        self.calls.append(("create_fabric_device", kwargs))
        return {"id": "device-id", **kwargs}

    def create_fabric_interface(self, **kwargs):
        self.calls.append(("create_fabric_interface", kwargs))
        return {"id": "interface-id", **kwargs}

    # Physical/protocol L3Out cluster -- all thin pass-throughs except
    # create_protocol_l3out, which receives an injected `protocol` kwarg the
    # caller never supplies.
    def create_leaf_interface_profile(self, **kwargs):
        self.calls.append(("create_leaf_interface_profile", kwargs))
        return {"id": "leaf-if-profile-id", **kwargs}

    def create_interface_selector(self, **kwargs):
        self.calls.append(("create_interface_selector", kwargs))
        return {"id": "interface-selector-id", **kwargs}

    def create_static_path_binding(self, **kwargs):
        self.calls.append(("create_static_path_binding", kwargs))
        return {"id": "static-path-id", **kwargs}

    def create_protocol_l3out(self, **kwargs):
        self.calls.append(("create_protocol_l3out", kwargs))
        return {"id": "l3out-id", **kwargs}

    def create_l3out_node_profile(self, **kwargs):
        self.calls.append(("create_l3out_node_profile", kwargs))
        return {"id": "node-profile-id", **kwargs}

    def create_l3out_interface_profile(self, **kwargs):
        self.calls.append(("create_l3out_interface_profile", kwargs))
        return {"id": "interface-profile-id", **kwargs}

    def create_l3out_interface(self, **kwargs):
        self.calls.append(("create_l3out_interface", kwargs))
        return {"id": "l3out-interface-id", **kwargs}

    def create_bgp_peer(self, **kwargs):
        self.calls.append(("create_bgp_peer", kwargs))
        return {"id": "bgp-peer-id", **kwargs}

    def create_ospf_interface(self, **kwargs):
        self.calls.append(("create_ospf_interface", kwargs))
        return {"id": "ospf-interface-id", **kwargs}

    def create_ospf_interface_policy(self, **kwargs):
        self.calls.append(("create_ospf_interface_policy", kwargs))
        return {"id": "ospf-policy-id", **kwargs}


def test_create_tenant_passes_name_through_unprefixed():
    """Current, real behavior: CreateTenantRequest.name is validated against
    ^[a-z0-9-]+$ (no colon allowed) and create_tenant() passes it straight
    through to NautobotClient.create_tenant() with no 'ACI:' prefix added --
    unlike EVPN's create_evpn_tenant, which adds 'EVPN:' itself. This means
    a tenant created via this MCP tool as-is will NOT carry the 'ACI:'
    prefix the live OPA tenant_naming policy expects (see the real
    'ACI:Sales' -> 'ACI:sales' incident in Platform-Status-and-Pending-
    Items.md) and would fail the pipeline's policy_check job. Documented
    here as a real gap, not asserted as correct/desired behavior."""
    fake = _FakeNautobotClient()
    request = CreateTenantRequest(name="acme", description="d")

    result = create_tenant(request, nautobot=fake)

    assert fake.calls == [("create_tenant", {"name": "acme", "description": "d"})]
    assert result["tenant"]["name"] == "acme"


def test_create_vrf_passes_tenant_and_name_through():
    fake = _FakeNautobotClient()
    request = CreateVrfRequest(tenant="ACI:acme", name="acme-vrf")

    result = create_vrf(request, nautobot=fake)

    assert fake.calls == [("create_vrf", {"tenant": "ACI:acme", "name": "acme-vrf", "description": ""})]
    assert result["vrf"]["name"] == "acme-vrf"
    assert "ACI:acme" in result["note"]


def test_create_bridge_domain_passes_gateway_ip_through():
    fake = _FakeNautobotClient()
    request = CreateBridgeDomainRequest(
        tenant="ACI:acme", vrf="acme-vrf", name="acme-bd", gateway_ip="10.0.0.1/24"
    )

    result = create_bridge_domain(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_bridge_domain",
            {
                "tenant": "ACI:acme",
                "vrf": "acme-vrf",
                "name": "acme-bd",
                "gateway_ip": "10.0.0.1/24",
                "subnet_scope": "private",
                "description": "",
                "l3outs": [],
            },
        )
    ]
    assert result["prefix"]["name"] == "acme-bd"


def test_create_vlan_pool_passes_range_through():
    fake = _FakeNautobotClient()
    request = CreateVlanPoolRequest(name="pool1", range_from=100, range_to=200)

    result = create_vlan_pool(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_vlan_pool",
            {
                "location": None,
                "name": "pool1",
                "alloc_mode": "static",
                "range_from": 100,
                "range_to": 200,
                "range_alloc_mode": None,
                "role": "external",
                "description": "",
            },
        )
    ]
    assert result["vlan_pool"]["vlan_pool"] == "pool1"
    assert "100-200" in result["note"]


def test_create_physical_domain_passes_vlan_pool_through():
    fake = _FakeNautobotClient()
    request = CreatePhysicalDomainRequest(name="phys-dom1", vlan_pool="pool1")

    result = create_physical_domain(request, nautobot=fake)

    assert fake.calls == [
        ("create_physical_domain", {"location": None, "name": "phys-dom1", "vlan_pool": "pool1"})
    ]
    assert result["physical_domain"]["physical_domain"] == "phys-dom1"


def test_create_aep_passes_domains_through():
    fake = _FakeNautobotClient()
    request = CreateAepRequest(name="aep1", domains=["phys-dom1", "phys-dom2"])

    result = create_aep(request, nautobot=fake)

    assert fake.calls == [
        ("create_aep", {"location": None, "name": "aep1", "domains": ["phys-dom1", "phys-dom2"]})
    ]
    assert result["aep"]["aep"] == "aep1"


def test_create_aep_defaults_to_no_domains():
    fake = _FakeNautobotClient()
    request = CreateAepRequest(name="aep1")

    create_aep(request, nautobot=fake)

    assert fake.calls == [("create_aep", {"location": None, "name": "aep1", "domains": []})]


def test_create_leaf_interface_policy_group_passes_aep_through():
    fake = _FakeNautobotClient()
    request = CreateLeafInterfacePolicyGroupRequest(name="leaf-pg1", aep="aep1")

    result = create_leaf_interface_policy_group(request, nautobot=fake)

    assert fake.calls == [
        ("create_leaf_interface_policy_group", {"location": None, "name": "leaf-pg1", "aep": "aep1"})
    ]
    assert result["leaf_interface_policy_group"]["leaf_interface_policy_group"] == "leaf-pg1"


def test_create_vmm_domain_passes_fields_through():
    fake = _FakeNautobotClient()
    request = CreateVmmDomainRequest(
        name="vmm1",
        controller_name="vc1",
        host_or_ip="vcenter.example.com",
        root_cont_name="Datacenter1",
        vlan_pool="pool1",
        credential_name="vc1-cred",
    )

    result = create_vmm_domain(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_vmm_domain",
            {
                "location": None,
                "name": "vmm1",
                "controller_name": "vc1",
                "host_or_ip": "vcenter.example.com",
                "root_cont_name": "Datacenter1",
                "vendor": "VMware",
                "vlan_pool": "pool1",
                "credential_name": "vc1-cred",
                "dvs_version": "unmanaged",
            },
        )
    ]
    assert result["vmm_domain"]["vmm_domain"] == "vmm1"


def test_bind_epg_domain_passes_fields_through():
    fake = _FakeNautobotClient()
    request = BindEpgDomainRequest(
        tenant="ACI:acme",
        application_profile="acme-ap",
        epg="acme-epg",
        domain="vmm-dom1",
        domain_type="vmm",
        resolution_immediacy="immediate",
    )

    result = bind_epg_domain(request, nautobot=fake)

    assert fake.calls == [
        (
            "bind_epg_domain",
            {
                "tenant": "ACI:acme",
                "application_profile": "acme-ap",
                "epg": "acme-epg",
                "domain": "vmm-dom1",
                "domain_type": "vmm",
                "resolution_immediacy": "immediate",
                "deployment_immediacy": None,
            },
        )
    ]
    assert result["binding"]["epg"] == "acme-epg"
    assert "vmm domain 'vmm-dom1'" in result["note"]


def test_create_security_domain_passes_description_through():
    fake = _FakeNautobotClient()
    request = CreateSecurityDomainRequest(name="phase-f-domain", description="test")

    result = create_security_domain(request, nautobot=fake)

    assert fake.calls == [
        ("create_security_domain", {"location": None, "name": "phase-f-domain", "description": "test"})
    ]
    assert result["security_domain"]["security_domain"] == "phase-f-domain"


def test_create_local_user_defaults_no_domain_binding():
    fake = _FakeNautobotClient()
    request = CreateLocalUserRequest(name="phase-f-user")

    create_local_user(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_local_user",
            {
                "location": None,
                "name": "phase-f-user",
                "email": "",
                "first_name": "",
                "last_name": "",
                "phone": "",
                "account_status": "active",
                "security_domain": None,
                "role": None,
                "priv_type": None,
            },
        )
    ]


def test_create_local_user_passes_security_domain_and_role_through():
    fake = _FakeNautobotClient()
    request = CreateLocalUserRequest(name="phase-f-user", security_domain="phase-f-domain", role="read-all", priv_type="readPriv")

    result = create_local_user(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_local_user",
            {
                "location": None,
                "name": "phase-f-user",
                "email": "",
                "first_name": "",
                "last_name": "",
                "phone": "",
                "account_status": "active",
                "security_domain": "phase-f-domain",
                "role": "read-all",
                "priv_type": "readPriv",
            },
        )
    ]
    assert result["local_user"]["local_user"] == "phase-f-user"
    assert "local_user_passwords" in result["note"]


# Ported from copilot/aci-platform-comparison (2026-09-08) -- L4-L7/PBR/
# Service Graph and VRF route-leak tool tests, genuinely new coverage.
def test_l4l7_tools_pass_tenant_intent_through():
    fake = _FakeNautobotClient()

    device = create_l4l7_device(
        CreateL4L7DeviceRequest(tenant="ACI:acme", name="fw", consumer_interface="inside", provider_interface="outside", vmm_domain="acme-vmm"),
        nautobot=fake,
    )
    graph = create_service_graph(
        CreateServiceGraphRequest(
            tenant="ACI:acme",
            name="fw-graph",
            contract="web-to-db",
            device="fw",
            consumer_logical_interface="inside",
            consumer_redirect_policy="inside-pbr",
            provider_logical_interface="outside",
            provider_redirect_policy="outside-pbr",
        ),
        nautobot=fake,
    )
    policy = create_pbr_policy(
        CreatePbrPolicyRequest(tenant="ACI:acme", name="web-pbr", destination_ip="10.0.0.10"),
        nautobot=fake,
    )
    contract = create_pbr_contract(
        CreatePbrContractRequest(tenant="ACI:acme", name="web-to-db", filter_name="tcp-filter", service_graph="fw-graph", consumer_epg="web", provider_epg="db"),
        nautobot=fake,
    )

    assert [call[0] for call in fake.calls] == ["create_l4l7_device", "create_service_graph", "create_pbr_policy", "create_pbr_contract"]
    assert device["l4l7_device"]["name"] == "fw"
    assert graph["service_graph"]["name"] == "fw-graph"
    assert policy["pbr_policy"]["name"] == "web-pbr"
    assert contract["pbr_contract"]["name"] == "web-to-db"


def test_create_one_arm_service_graph_passes_single_arm_binding():
    fake = _FakeNautobotClient()
    request = CreateOneArmServiceGraphRequest(
        tenant="ACI:acme", name="adc-graph", contract="client-to-app", device="adc", logical_interface="client", redirect_policy="adc-pbr"
    )

    result = create_one_arm_service_graph(request, nautobot=fake)

    assert fake.calls[0][0] == "create_one_arm_service_graph"
    assert fake.calls[0][1]["redirect_policy"] == "adc-pbr"
    assert result["service_graph"]["name"] == "adc-graph"


def test_create_vrf_route_leak_passes_source_and_destination():
    fake = _FakeNautobotClient()
    request = CreateVrfRouteLeakRequest(
        tenant="ACI:acme",
        name="shared-to-app",
        source_vrf="shared-vrf",
        destination_vrf="app-vrf",
        subnet="10.10.10.0/24",
        allow_l3out_advertisement=True,
    )

    result = create_vrf_route_leak(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_vrf_route_leak",
            {
                "tenant": "ACI:acme",
                "name": "shared-to-app",
                "source_vrf": "shared-vrf",
                "destination_vrf": "app-vrf",
                "subnet": "10.10.10.0/24",
                "allow_l3out_advertisement": True,
                "description": "",
            },
        )
    ]
    assert result["vrf_route_leak"]["source_vrf"] == "shared-vrf"


def test_create_filter_passes_full_entry_attributes():
    fake = _FakeNautobotClient()
    request = CreateFilterRequest(
        tenant="acme",
        name="web-filter",
        entries=[
            {
                "name": "https",
                "ether_type": "ip",
                "ip_protocol": "tcp",
                "dest_from_port": "443",
                "dest_to_port": "443",
                "tcp_rules": ["est"],
                "stateful": True,
            }
        ],
    )

    result = create_filter(request, nautobot=fake)

    name, kwargs = fake.calls[0]
    assert name == "create_filter"
    entry = kwargs["entries"][0]
    assert entry["dest_from_port"] == "443"
    assert entry["tcp_rules"] == ["est"]
    assert entry["stateful"] is True
    # exclude_none must drop unset optionals rather than emitting nulls
    assert "arp_opcode" not in entry
    assert result["filter"]["filter"] == "web-filter"


def test_create_filter_entry_targets_existing_filter():
    fake = _FakeNautobotClient()
    request = CreateFilterEntryRequest(
        tenant="acme",
        filter_name="web-filter",
        entry={"name": "http", "ip_protocol": "tcp", "dest_from_port": "80", "dest_to_port": "80"},
    )

    create_filter_entry(request, nautobot=fake)

    name, kwargs = fake.calls[0]
    assert name == "create_filter_entry"
    assert kwargs["filter_name"] == "web-filter"
    assert kwargs["entry"]["name"] == "http"


def test_create_contract_subject_defaults_are_bidirectional():
    fake = _FakeNautobotClient()
    request = CreateContractSubjectRequest(
        tenant="acme",
        contract="web-ct",
        name="web-subj",
        filters=["web-filter", "icmp-filter"],
    )

    create_contract_subject(request, nautobot=fake)

    name, kwargs = fake.calls[0]
    assert name == "create_contract_subject"
    subject = kwargs["subject"]
    assert subject["filters"] == ["web-filter", "icmp-filter"]
    assert subject["apply_both_directions"] is True
    assert subject["reverse_filter_ports"] is True
    assert "priority" not in subject


def test_bind_epg_contract_passes_relation():
    fake = _FakeNautobotClient()
    request = BindEpgContractRequest(
        tenant="acme",
        application_profile="web-ap",
        epg="web-epg",
        contract="web-ct",
        relation="provided",
    )

    result = bind_epg_contract(request, nautobot=fake)

    name, kwargs = fake.calls[0]
    assert name == "bind_epg_contract"
    assert kwargs["relation"] == "provided"
    assert "provided contract 'web-ct'" in result["note"]


def test_create_pod_policy_group_defaults_to_default_rr_policy():
    fake = _FakeNautobotClient()
    request = CreatePodPolicyGroupRequest(location="Isolated Lab Site", name="Pod_PG")

    result = create_pod_policy_group(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_pod_policy_group",
            {
                "location": "Isolated Lab Site",
                "name": "Pod_PG",
                "bgp_route_reflector_policy": "default",
            },
        )
    ]
    assert result["pod_policy_group"]["pod_policy_group"] == "Pod_PG"


def test_create_pod_policy_group_can_leave_rr_policy_unresolved():
    fake = _FakeNautobotClient()
    request = CreatePodPolicyGroupRequest(
        location="Isolated Lab Site", name="Pod_PG", bgp_route_reflector_policy=None
    )

    create_pod_policy_group(request, nautobot=fake)

    assert fake.calls[0][1]["bgp_route_reflector_policy"] is None


# ---------------------------------------------------------------------------
# XML-compatible access hierarchy (infraAccPortP / infraHPortS / infraPortBlk
# / infraNodeP / infraLeafS / infraNodeBlk) and DCIM fabric inventory.
#
# These eight tools shipped with no tests at all. Each handler is a thin
# pass-through -- `{"<key>": nautobot.create_X(**request.model_dump())}` --
# so what these tests actually pin down is the part that can silently break:
# the EXACT kwarg set reaching NautobotClient (a renamed or dropped schema
# field changes it), and the response key the MCP client sees. Asserting the
# whole kwargs dict rather than individual keys is deliberate: a newly-added
# schema field that nobody wired into the client shows up here as a failure
# instead of being silently ignored, which is the precise failure mode that
# left aci_application_profile orphaned in Nautobot.
# ---------------------------------------------------------------------------

def test_create_access_port_profile_passes_full_kwargs_and_returns_keyed_result():
    fake = _FakeNautobotClient()
    request = CreateAccessPortProfileRequest(
        location="Isolated Lab Site", name="LEAF101_IFP", description="Leaf 101 interface profile"
    )

    result = create_access_port_profile(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_access_port_profile",
            {
                "location": "Isolated Lab Site",
                "name": "LEAF101_IFP",
                "description": "Leaf 101 interface profile",
            },
        )
    ]
    assert result["access_port_profile"]["name"] == "LEAF101_IFP"


def test_create_access_port_selector_carries_profile_and_policy_group():
    """The selector is the join between a port profile and the IPG that
    supplies its CDP/LLDP/link policies -- dropping either field would
    produce an infraHPortS with an unresolved relation."""
    fake = _FakeNautobotClient()
    request = CreateAccessPortSelectorRequest(
        location="Isolated Lab Site", name="Ext_Nexus", access_port_profile="LEAF101_IFP", policy_group="ExtL3_IPG"
    )

    result = create_access_port_selector(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_access_port_selector",
            {
                "location": "Isolated Lab Site",
                "name": "Ext_Nexus",
                "access_port_profile": "LEAF101_IFP",
                "policy_group": "ExtL3_IPG",
                "selector_type": "range",
            },
        )
    ]
    assert result["access_port_selector"]["policy_group"] == "ExtL3_IPG"


def test_create_access_port_block_passes_unset_to_fields_through_as_none():
    """to_card/to_port are left as None by the schema and resolved to the
    from_* value by main.tf. This asserts the tool does NOT quietly fill
    them in -- two independent defaults for the same field is exactly how
    the generator and Terraform drift apart."""
    fake = _FakeNautobotClient()
    request = CreateAccessPortBlockRequest(
        location="Isolated Lab Site",
        access_port_profile="LEAF101_IFP",
        selector="Ext_Nexus",
        name="portblk_ext_nexus",
        from_card=1,
        from_port=4,
    )

    result = create_access_port_block(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_access_port_block",
            {
                "location": "Isolated Lab Site",
                "access_port_profile": "LEAF101_IFP",
                "selector": "Ext_Nexus",
                "name": "portblk_ext_nexus",
                "from_card": 1,
                "from_port": 4,
                "to_card": None,
                "to_port": None,
            },
        )
    ]
    assert result["access_port_block"]["from_port"] == 4


def test_create_leaf_profile_passes_attached_port_profiles_through():
    fake = _FakeNautobotClient()
    request = CreateLeafProfileRequest(
        location="Isolated Lab Site", name="LEAF101_SWP", access_port_profiles=["LEAF101_IFP"]
    )

    result = create_leaf_profile(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_leaf_profile",
            {
                "location": "Isolated Lab Site",
                "name": "LEAF101_SWP",
                "access_port_profiles": ["LEAF101_IFP"],
                "description": "",
            },
        )
    ]
    assert result["leaf_profile"]["access_port_profiles"] == ["LEAF101_IFP"]


def test_create_leaf_selector_passes_parent_profile_through():
    fake = _FakeNautobotClient()
    request = CreateLeafSelectorRequest(
        location="Isolated Lab Site", leaf_profile="LEAF101_SWP", name="LEAF101_Sel"
    )

    result = create_leaf_selector(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_leaf_selector",
            {
                "location": "Isolated Lab Site",
                "leaf_profile": "LEAF101_SWP",
                "name": "LEAF101_Sel",
                "selector_type": "range",
            },
        )
    ]
    assert result["leaf_selector"]["leaf_profile"] == "LEAF101_SWP"


def test_create_leaf_node_block_passes_node_range_through():
    fake = _FakeNautobotClient()
    request = CreateLeafNodeBlockRequest(
        location="Isolated Lab Site",
        leaf_profile="LEAF101_SWP",
        selector="LEAF101_Sel",
        name="nodeblk_101_101",
        from_node=101,
    )

    result = create_leaf_node_block(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_leaf_node_block",
            {
                "location": "Isolated Lab Site",
                "leaf_profile": "LEAF101_SWP",
                "selector": "LEAF101_Sel",
                "name": "nodeblk_101_101",
                "from_node": 101,
                "to_node": None,
            },
        )
    ]
    assert result["leaf_node_block"]["from_node"] == 101


def test_create_fabric_device_passes_lab_defaults_through():
    """create_fabric_device writes to Nautobot DCIM, not a Custom Field --
    it is what gives the generator a real node_id/pod_id to build a
    topology/pod-N/paths-M DN from. The defaults asserted here are this
    lab's conventions and reach the client verbatim."""
    fake = _FakeNautobotClient()
    request = CreateFabricDeviceRequest(name="Leaf101", node_id=101)

    result = create_fabric_device(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_fabric_device",
            {
                "name": "Leaf101",
                "node_id": 101,
                "serial": "",
                "role": "leaf",
                "pod_id": 1,
                "location": None,
                "model": "Nexus 9000v",
                "description": "",
            },
        )
    ]
    assert result["device"]["node_id"] == 101


def test_create_fabric_device_passes_pod_id_and_spine_role_through():
    """pod_id reaches NautobotClient, which writes it to the `aci_pod_id`
    Custom Field. That field existed in Nautobot from the start but nothing
    could write it until 2026-09-14, so every device carried a node ID with
    no pod and the generator had to assume pod 1 -- which silently rules out
    a multi-pod fabric."""
    fake = _FakeNautobotClient()
    request = CreateFabricDeviceRequest(
        name="spine-1", node_id=1001, role="spine", pod_id=2, serial="FDO2306FG77"
    )

    result = create_fabric_device(request, nautobot=fake)

    kwargs = fake.calls[0][1]
    assert kwargs["role"] == "spine"
    assert kwargs["pod_id"] == 2
    assert kwargs["serial"] == "FDO2306FG77"
    assert result["device"]["node_id"] == 1001


def test_create_fabric_interface_defaults_to_enabled_and_keeps_slash_in_name():
    fake = _FakeNautobotClient()
    request = CreateFabricInterfaceRequest(device="Leaf101", name="Ethernet1/4")

    result = create_fabric_interface(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_fabric_interface",
            {"device": "Leaf101", "name": "Ethernet1/4", "description": "", "enabled": True},
        )
    ]
    assert result["interface"]["name"] == "Ethernet1/4"


# ---------------------------------------------------------------------------
# Physical/protocol L3Out cluster dispatch.
#
# create_bgp_l3out / create_ospf_l3out are the only two tools in the whole
# ACI catalogue whose handler adds an argument the caller never supplies
# (`protocol=`). That injected value is what main.tf's
# `local.l3out_bgp_policies` / `l3out_ospf_policies` filters split on, so
# getting it wrong silently produces an L3Out with no protocol enabled --
# hence a dedicated test for each rather than one shared one.
# ---------------------------------------------------------------------------

def test_create_epg_passes_application_profile_and_bridge_domain_through():
    """An EPG is a VLAN carrying aci_application_profile and
    aci_epg_bridge_domain -- the generator exports it ONLY when both are
    set (transformer._build_application_profiles). Dropping either here
    produces a VLAN that is silently never exported as an EPG at all, with
    no error anywhere, so both are asserted explicitly."""
    fake = _FakeNautobotClient()
    request = CreateEpgRequest(
        tenant="ACI:sales",
        application_profile="eCommerce_AP",
        bridge_domain="Presales_BD",
        name="Web_EPG",
        vid=11,
    )

    result = create_epg(request, nautobot=fake)

    kwargs = fake.calls[0][1]
    assert fake.calls[0][0] == "create_epg"
    assert kwargs["application_profile"] == "eCommerce_AP"
    assert kwargs["bridge_domain"] == "Presales_BD"
    assert kwargs["vid"] == 11
    assert kwargs["subnet_scope"] == "private"
    assert result["epg"]["name"] == "Web_EPG"
    assert "ACI:sales" in result["note"]


def test_create_bgp_l3out_injects_protocol_bgp():
    fake = _FakeNautobotClient()
    request = CreateProtocolL3OutRequest(tenant="sales", name="BGP_L3Out", vrf="Presales_VRF", domain="ExtL3Dom")

    result = create_bgp_l3out(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_protocol_l3out",
            {
                "protocol": "bgp",
                "tenant": "sales",
                "name": "BGP_L3Out",
                "vrf": "Presales_VRF",
                "domain": "ExtL3Dom",
                "description": "",
                "external_epgs": [],
            },
        )
    ]
    assert result["l3out"]["protocol"] == "bgp"


def test_create_ospf_l3out_injects_protocol_ospf():
    fake = _FakeNautobotClient()
    request = CreateProtocolL3OutRequest(tenant="sales", name="OSPF_L3Out", vrf="Presales_VRF", domain="ExtL3Dom")

    create_ospf_l3out(request, nautobot=fake)

    assert fake.calls[0][1]["protocol"] == "ospf"


def test_bgp_and_ospf_l3out_share_one_schema_but_never_one_protocol():
    """Both tools take CreateProtocolL3OutRequest, which carries no protocol
    field of its own -- so the only thing distinguishing them is the
    injected kwarg. This pins that the schema stays protocol-free and the
    two tools stay distinguishable."""
    assert "protocol" not in CreateProtocolL3OutRequest.model_fields

    fake = _FakeNautobotClient()
    request = CreateProtocolL3OutRequest(tenant="sales", name="L3Out", vrf="v", domain="d")
    create_bgp_l3out(request, nautobot=fake)
    create_ospf_l3out(request, nautobot=fake)

    assert [call[1]["protocol"] for call in fake.calls] == ["bgp", "ospf"]


def test_create_leaf_interface_profile_passes_node_and_pod():
    fake = _FakeNautobotClient()
    request = CreateLeafInterfaceProfileRequest(location="Isolated Lab Site", name="Leaf101_Profile", node_id=101)

    result = create_leaf_interface_profile(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_leaf_interface_profile",
            {"location": "Isolated Lab Site", "name": "Leaf101_Profile", "node_id": 101, "pod_id": 1, "description": ""},
        )
    ]
    assert result["leaf_interface_profile"]["node_id"] == 101


def test_create_interface_selector_passes_port_and_policy_group():
    fake = _FakeNautobotClient()
    request = CreateInterfaceSelectorRequest(
        location="Isolated Lab Site",
        name="eth1-5",
        leaf_interface_profile="Leaf101_Profile",
        policy_group="ExtL3_IPG",
        module=1,
        port=5,
    )

    result = create_interface_selector(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_interface_selector",
            {
                "location": "Isolated Lab Site",
                "name": "eth1-5",
                "leaf_interface_profile": "Leaf101_Profile",
                "policy_group": "ExtL3_IPG",
                "module": 1,
                "port": 5,
            },
        )
    ]
    assert result["interface_selector"]["port"] == 5


def test_create_static_path_binding_passes_every_path_component():
    """node_id/module/port/pod_id together render the
    topology/pod-N/paths-M/pathep-[ethX/Y] DN in main.tf. Losing any one of
    them produces a malformed DN rather than an error, so the whole set is
    asserted."""
    fake = _FakeNautobotClient()
    request = CreateStaticPathBindingRequest(
        tenant="sales",
        application_profile="eCommerce_AP",
        epg="Web_EPG",
        node_id=101,
        module=1,
        port=10,
        encap="vlan-11",
    )

    result = create_static_path_binding(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_static_path_binding",
            {
                "tenant": "sales",
                "application_profile": "eCommerce_AP",
                "epg": "Web_EPG",
                "node_id": 101,
                "module": 1,
                "port": 10,
                "encap": "vlan-11",
                "pod_id": 1,
                "mode": "regular",
            },
        )
    ]
    assert result["static_path"]["encap"] == "vlan-11"


def test_create_l3out_node_profile_and_interface_profile_dispatch():
    fake = _FakeNautobotClient()

    node_result = create_l3out_node_profile(
        CreateL3OutNodeProfileRequest(tenant="sales", l3out="BGP_L3Out", name="L101"), nautobot=fake
    )
    interface_result = create_l3out_interface_profile(
        CreateL3OutInterfaceProfileRequest(
            tenant="sales", l3out="BGP_L3Out", node_profile="L101", name="BGP_L3Out_interfaceProfile"
        ),
        nautobot=fake,
    )

    assert [call[0] for call in fake.calls] == ["create_l3out_node_profile", "create_l3out_interface_profile"]
    assert node_result["node_profile"]["nodes"] == []
    assert interface_result["interface_profile"]["node_profile"] == "L101"


def test_create_l3out_interface_passes_svi_encapsulation_through():
    fake = _FakeNautobotClient()
    request = CreateL3OutInterfaceRequest(
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

    result = create_l3out_interface(request, nautobot=fake)

    assert fake.calls == [
        (
            "create_l3out_interface",
            {
                "tenant": "sales",
                "l3out": "BGP_L3Out",
                "node_profile": "L101",
                "interface_profile": "BGP_L3Out_interfaceProfile",
                "node_id": 101,
                "module": 1,
                "port": 4,
                "pod_id": 1,
                "ip": "172.16.1.5/30",
                "svi": True,
                "vlan": 51,
                "mode": "regular",
                "mtu": "inherit",
            },
        )
    ]
    assert result["interface"]["svi"] is True


def test_create_bgp_peer_passes_both_as_numbers_through():
    """remote_as and local_as land on different provider attributes
    (as_number vs local_asn); swapping them is a silent, plausible bug that
    only shows up as a session that never establishes."""
    fake = _FakeNautobotClient()
    request = CreateBgpPeerRequest(
        tenant="sales",
        l3out="BGP_L3Out",
        node_profile="L101",
        interface_profile="BGP_L3Out_interfaceProfile",
        interface_key="L101/BGP_L3Out_interfaceProfile",
        ip="172.16.1.6",
        remote_as=65002,
        local_as=65003,
    )

    result = create_bgp_peer(request, nautobot=fake)

    kwargs = fake.calls[0][1]
    assert kwargs["remote_as"] == 65002
    assert kwargs["local_as"] == 65003
    assert kwargs["interface_key"] == "L101/BGP_L3Out_interfaceProfile"
    assert result["bgp_peer"]["ip"] == "172.16.1.6"


def test_create_ospf_interface_passes_interface_key_through_verbatim():
    """interface_key is an undocumented, unvalidated string contract: main.tf
    resolves it as "<tenant>/<l3out>/<interface_key>" against
    aci_logical_interface_profile's keys, so it must be
    "<node_profile>/<interface_profile>". Asserting it survives verbatim is
    the only guard that exists today -- see the audit's F-09."""
    fake = _FakeNautobotClient()
    request = CreateOspfInterfaceRequest(
        tenant="sales", l3out="OSPF_L3Out", interface_key="OSPF_NP/OSPF_IP", policy="OSPF_p2p"
    )

    result = create_ospf_interface(request, nautobot=fake)

    assert fake.calls[0][1]["interface_key"] == "OSPF_NP/OSPF_IP"
    assert result["ospf_interface"]["policy"] == "OSPF_p2p"


def test_create_ospf_interface_policy_returns_a_note_and_never_a_raw_key():
    fake = _FakeNautobotClient()
    request = CreateOspfInterfacePolicyRequest(
        tenant="sales",
        name="OSPF_p2p",
        network_type="point-to-point",
        authentication_type="md5",
        authentication_secret_ref="vault/aci/ospf/p2p",
        authentication_key_id=1,
    )

    result = create_ospf_interface_policy(request, nautobot=fake)

    kwargs = fake.calls[0][1]
    assert kwargs["authentication_secret_ref"] == "vault/aci/ospf/p2p"
    assert not any("key" == k or k.endswith("_key") for k in kwargs)
    assert "OSPF_p2p" in result["note"]
    assert "sales" in result["note"]


# ---------------------------------------------------------------------------
# L4-L7 / PBR gap closure dispatch (2026-09-15).
# ---------------------------------------------------------------------------

def test_create_l4l7_device_passes_trunking_and_promiscuous_mode():
    """Terraform has always had `trunking`/`promiscuous_mode` lookups on
    aci_l4_l7_device, but nothing could set them -- no schema field, no
    client argument -- so both always resolved to null. This pins the whole
    chain now that it exists."""
    fake = _FakeNautobotClient()
    request = CreateL4L7DeviceRequest(
        tenant="finance", name="fw", consumer_interface="inside", provider_interface="outside",
        vmm_domain="finance-vmm", trunking=True, promiscuous_mode=True,
    )

    create_l4l7_device(request, nautobot=fake)

    kwargs = fake.calls[0][1]
    assert kwargs["trunking"] is True
    assert kwargs["promiscuous_mode"] is True


def test_create_pbr_policy_drops_the_shorthand_fields_before_the_client():
    """The schema normalises destination_ip into `destinations`; the handler
    must then drop the shorthand so the client sees exactly one destination
    shape rather than having to reconcile two."""
    fake = _FakeNautobotClient()
    request = CreatePbrPolicyRequest(tenant="finance", name="web-pbr", destination_ip="10.0.0.10")

    create_pbr_policy(request, nautobot=fake)

    kwargs = fake.calls[0][1]
    assert "destination_ip" not in kwargs
    assert "destination_mac" not in kwargs
    assert kwargs["destinations"] == [{
        "ip": "10.0.0.10", "mac": None, "second_ip": None, "dest_name": None,
        "pod_id": None, "health_group": None, "description": "",
    }]


def test_create_pbr_policy_warns_when_no_destination_is_health_tracked():
    """An untracked destination keeps receiving redirected traffic after it
    dies -- a silent black hole. The tool cannot refuse (untracked PBR is
    legal) so it says so loudly in the response the agent reads back."""
    fake = _FakeNautobotClient()
    request = CreatePbrPolicyRequest(tenant="finance", name="web-pbr", destination_ip="10.0.0.10")

    result = create_pbr_policy(request, nautobot=fake)

    assert "WARNING" in result["note"]
    assert "health group" in result["note"]


def test_create_pbr_policy_does_not_warn_when_destinations_are_tracked():
    fake = _FakeNautobotClient()
    request = CreatePbrPolicyRequest(
        tenant="finance", name="web-pbr",
        destinations=[PbrDestinationSpec(ip="10.0.0.10", health_group="fw-hg")],
    )

    result = create_pbr_policy(request, nautobot=fake)

    assert "WARNING" not in result["note"]
    assert "1 destination(s)" in result["note"]


def test_create_pbr_policy_passes_thresholds_and_sla_reference():
    fake = _FakeNautobotClient()
    request = CreatePbrPolicyRequest(
        tenant="finance", name="web-pbr",
        destinations=[PbrDestinationSpec(ip="10.0.0.10", health_group="fw-hg")],
        ip_sla_policy="fw-icmp", threshold_enable=True,
        min_threshold_percent=20, max_threshold_percent=80, threshold_down_action="bypass",
        hashing_algorithm="sip-dip-prototype",
    )

    create_pbr_policy(request, nautobot=fake)

    kwargs = fake.calls[0][1]
    assert kwargs["ip_sla_policy"] == "fw-icmp"
    assert kwargs["threshold_enable"] is True
    assert (kwargs["min_threshold_percent"], kwargs["max_threshold_percent"]) == (20, 80)
    assert kwargs["hashing_algorithm"] == "sip-dip-prototype"


def test_create_pbr_health_group_dispatch():
    fake = _FakeNautobotClient()
    request = CreatePbrHealthGroupRequest(tenant="finance", name="fw-hg")

    result = create_pbr_health_group(request, nautobot=fake)

    assert fake.calls == [("create_pbr_health_group", {"tenant": "finance", "name": "fw-hg", "description": ""})]
    assert "fw-hg" in result["note"]


def test_create_ip_sla_policy_dispatch_passes_probe_settings():
    fake = _FakeNautobotClient()
    request = CreateIpSlaPolicyRequest(
        tenant="finance", name="fw-tcp", sla_type="tcp", port=443, frequency=5, detect_multiplier=3
    )

    result = create_ip_sla_policy(request, nautobot=fake)

    kwargs = fake.calls[0][1]
    assert kwargs["sla_type"] == "tcp"
    assert kwargs["port"] == 443
    assert kwargs["detect_multiplier"] == 3
    assert "tcp" in result["note"]


def test_create_vmm_domain_without_a_controller_passes_none_through():
    """A VMM domain with no controller is the only way to get an L4-L7
    VIRTUAL device visible in APIC when there is no vCenter to talk to
    (live-verified 2026-09-15 against the lab APIC: the domain forms, and
    vnsRsALDevToDomP reaches state=formed). The tool must carry the absent
    controller through as None rather than substituting a placeholder."""
    fake = _FakeNautobotClient()
    request = CreateVmmDomainRequest(name="vCenter_VMM", vlan_pool="vCenter_VMM_Pool")

    create_vmm_domain(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert kwargs["controller_name"] is None
    assert kwargs["host_or_ip"] is None
    assert kwargs["root_cont_name"] is None
    assert kwargs["credential_name"] is None
    assert kwargs["vlan_pool"] == "vCenter_VMM_Pool"


def test_create_concrete_device_passes_interfaces_through_as_dicts():
    """The handler must flatten the nested ConcreteInterfaceSpec models --
    the client writes them straight into a JSON Custom Field, and a Pydantic
    model is not JSON-serialisable."""
    fake = _FakeNautobotClient()
    request = CreateConcreteDeviceRequest(
        tenant="ACI:acme", device="FW", name="ASAv_cdev",
        vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
        interfaces=[
            {"name": "cif1", "logical_interface": "db_int", "vnic_name": "Network adapter 2"},
            {"name": "cif2", "logical_interface": "backup_int", "vnic_name": "Network adapter 3"},
        ],
    )

    result = create_concrete_device(request, nautobot=fake)

    name, kwargs = fake.calls[0]
    assert name == "create_concrete_device"
    assert kwargs["device"] == "FW"
    assert kwargs["vm_name"] == "ASAv-1"
    assert all(isinstance(i, dict) for i in kwargs["interfaces"])
    assert kwargs["interfaces"][0]["vnic_name"] == "Network adapter 2"
    assert "cif1->db_int" in result["note"]


def test_create_concrete_device_note_warns_about_vcenter_resolution():
    """A VIRTUAL concrete device silently stays invalid if the VM or vNIC
    names do not match vCenter, so the tool says so rather than reporting
    plain success."""
    fake = _FakeNautobotClient()
    request = CreateConcreteDeviceRequest(
        tenant="ACI:acme", device="FW", name="ASAv_cdev",
        vm_name="ASAv-1", vmm_domain="vCenter_VMM", vmm_controller="vCenter",
        interfaces=[{"name": "cif1", "logical_interface": "db_int", "vnic_name": "Network adapter 2"}],
    )

    note = create_concrete_device(request, nautobot=fake)["note"]

    assert "ASAv-1" in note and "vCenter" in note
    assert "must match what vCenter reports" in note


def test_create_physical_concrete_device_note_warns_about_unformed_paths():
    fake = _FakeNautobotClient()
    request = CreateConcreteDeviceRequest(
        tenant="ACI:acme", device="FW", name="fw1", device_type="PHYSICAL",
        interfaces=[{"name": "eth1", "logical_interface": "consumer", "node_id": 101, "port": 30}],
    )

    note = create_concrete_device(request, nautobot=fake)["note"]

    assert "unformed" in note


def test_create_nd_interface_policy_splits_identity_from_attributes():
    """tenant/name are positional identity for the client; everything else is
    a policy attribute passed through as kwargs."""
    fake = _FakeNautobotClient()
    request = CreateNdInterfacePolicyRequest(tenant="ACI:acme", name="ND_Pol", hop_limit=64, mtu=1500)

    create_nd_interface_policy(request, nautobot=fake)

    name, kwargs = fake.calls[0]
    assert name == "create_nd_interface_policy"
    assert kwargs["tenant"] == "ACI:acme" and kwargs["name"] == "ND_Pol"
    assert kwargs["hop_limit"] == 64 and kwargs["mtu"] == 1500


def test_create_dpp_policy_passes_units_alongside_values():
    fake = _FakeNautobotClient()
    request = CreateDppPolicyRequest(tenant="ACI:acme", name="In", rate=100, rate_unit="mega")

    create_dpp_policy(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert kwargs["rate"] == 100 and kwargs["rate_unit"] == "mega"


def test_create_pim_interface_policy_never_forwards_an_auth_key():
    fake = _FakeNautobotClient()
    request = CreatePimInterfacePolicyRequest(tenant="ACI:acme", name="PIM", auth_type="ah-md5")

    create_pim_interface_policy(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert kwargs["auth_type"] == "ah-md5"
    assert not [k for k in kwargs if "key" in k.lower()]


def test_create_igmp_interface_policy_passes_fields_through():
    fake = _FakeNautobotClient()
    request = CreateIgmpInterfacePolicyRequest(tenant="ACI:acme", name="IGMP", version="v3")

    create_igmp_interface_policy(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert kwargs["version"] == "v3"


def test_create_custom_qos_policy_passes_maps_through():
    fake = _FakeNautobotClient()
    request = CreateCustomQosPolicyRequest(
        tenant="ACI:acme", name="CQos",
        dscp_to_priority_maps=[{"from": "EF", "to": "EF", "priority": "level1"}],
    )

    create_custom_qos_policy(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert kwargs["dscp_to_priority_maps"][0]["priority"] == "level1"


def test_bind_policies_reports_what_it_bound_and_warns_about_validation():
    fake = _FakeNautobotClient()
    request = BindL3OutInterfaceProfilePoliciesRequest(
        tenant="ACI:acme", l3out="Edge", node_profile="NP", interface_profile="IP",
        nd_interface_policy="ND_Pol", qos_priority="level3",
    )

    result = bind_l3out_interface_profile_policies(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert kwargs["interface_profile"] == "IP"
    assert kwargs["nd_interface_policy"] == "ND_Pol"
    assert "nd_interface_policy=ND_Pol" in result["note"]
    assert "apply time" in result["note"], "the note must say the provider only catches this late"


def test_create_match_rule_flattens_prefix_models():
    """Prefixes go straight into a JSON Custom Field, so the nested Pydantic
    models must be dicts by the time they reach the client."""
    fake = _FakeNautobotClient()
    request = CreateMatchRuleRequest(
        tenant="ACI:acme", name="match-permit-prefix-out",
        prefixes=[{"ip": "172.16.200.200/32"}],
    )

    result = create_match_rule(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert all(isinstance(p, dict) for p in kwargs["prefixes"])
    assert kwargs["prefixes"][0]["ip"] == "172.16.200.200/32"
    assert "172.16.200.200/32" in result["note"]


def test_create_route_control_profile_warns_a_custom_name_is_inert():
    """A custom-named map does nothing until bound. Saying so in the response
    is the difference between a working lab and a silent no-op."""
    fake = _FakeNautobotClient()
    request = CreateRouteControlProfileRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", name="Uni-Route-Profile-OUT",
        contexts=[{"name": "permit-explicit", "order": 0, "action": "permit",
                   "match_rule": "m1"}],
    )

    note = create_route_control_profile(request, nautobot=fake)["note"]

    assert "does nothing until it is referenced" in note
    assert "0:permit-explicit(permit)" in note
    assert "implicit deny" in note


def test_create_route_control_profile_does_not_warn_for_default_export():
    """default-export applies to the L3Out on its own, so the warning would be
    wrong there."""
    fake = _FakeNautobotClient()
    request = CreateRouteControlProfileRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", name="default-export",
        contexts=[{"name": "permit-explicit", "order": 0, "action": "permit"}],
    )

    note = create_route_control_profile(request, nautobot=fake)["note"]

    assert "does nothing until it is referenced" not in note


def test_route_map_contexts_are_reported_in_evaluation_order():
    """The note sorts by order, not by the order they were supplied in."""
    fake = _FakeNautobotClient()
    request = CreateRouteControlProfileRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", name="rm",
        contexts=[{"name": "deny-b", "order": 1, "action": "deny"},
                  {"name": "permit-a", "order": 0, "action": "permit"}],
    )

    note = create_route_control_profile(request, nautobot=fake)["note"]

    assert note.index("0:permit-a") < note.index("1:deny-b")


def test_bind_route_map_passes_direction_through():
    fake = _FakeNautobotClient()
    request = BindExternalEpgRouteControlProfileRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
        route_control_profile="Uni-Route-Profile-OUT", direction="export",
    )

    bind_external_epg_route_control_profile(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert kwargs["direction"] == "export"
    assert kwargs["route_control_profile"] == "Uni-Route-Profile-OUT"


def test_subnet_scope_change_reports_both_sides():
    """Which flags were removed matters as much as which were set -- dropping
    export-rtctrl is the whole point of the operation."""
    fake = _FakeNautobotClient()
    request = SetExternalEpgSubnetScopeRequest(
        tenant="ACI:acme", l3out="OSPF_L3Out", external_epg="Cat_ExtNet",
        ip="172.16.200.200/32", scope=["import-security"],
    )

    note = set_external_epg_subnet_scope(request, nautobot=fake)["note"]

    assert "export-rtctrl" in note and "import-security" in note


def test_bind_external_epg_contract_reports_both_directions():
    fake = _FakeNautobotClient()
    request = BindExternalEpgContractRequest(
        tenant="t", l3out="o", external_epg="Cat_ExtNet", consumed_contracts=["FileServices_Ct"]
    )

    note = bind_external_epg_contract(request, nautobot=fake)["note"]

    assert "consumes FileServices_Ct" in note


def test_add_match_rule_prefix_splits_identity_from_the_prefix():
    fake = _FakeNautobotClient()
    request = AddMatchRulePrefixRequest(
        tenant="t", match_rule="deny-prefix-out", ip="172.16.199.199/32"
    )

    add_match_rule_prefix(request, nautobot=fake)

    _, kwargs = fake.calls[0]
    assert kwargs["match_rule"] == "deny-prefix-out"
    assert kwargs["ip"] == "172.16.199.199/32"
    assert "tenant" in kwargs


def test_add_external_epg_subnet_reports_the_scope():
    fake = _FakeNautobotClient()
    request = AddExternalEpgSubnetRequest(
        tenant="t", l3out="o", external_epg="Nexus_ExtNet", ip="172.16.199.199/32"
    )

    note = add_external_epg_subnet(request, nautobot=fake)["note"]

    assert "import-security" in note


def test_create_l3_domain_warns_when_no_vlan_pool_is_bound():
    """An L3Out encap outside every pool is invalid on real hardware even
    though this simulator accepts it."""
    fake = _FakeNautobotClient()

    note = create_l3_domain(CreateL3DomainRequest(name="ExtL3Dom"), nautobot=fake)["note"]

    assert "no VLAN pool bound" in note


def test_create_l3_domain_does_not_warn_when_a_pool_is_bound():
    fake = _FakeNautobotClient()

    note = create_l3_domain(
        CreateL3DomainRequest(name="ExtL3Dom", vlan_pool="ExtL3_Pool"), nautobot=fake
    )["note"]

    assert "WARNING" not in note
