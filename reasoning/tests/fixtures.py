"""Payloads shaped exactly like the live MCP responses for tenant sales,
pipeline 60 (2026-10-15): 116 resources applied, 19 new APIC faults."""
from __future__ import annotations

import copy

INTENT = {
    "tenant": "sales",
    "vrfs": [{"name": "Presales_VRF"}],
    "bridge_domains": [{"name": "Presales_BD", "vrfs": ["Presales_VRF"], "subnets": [], "attributes": {}}],
    "application_profiles": [{"name": "eCommerce_AP", "epgs": [{"name": "Web_EPG", "bridge_domain": "Presales_BD"}]}],
    "json_intent": {
        "aci_l3outs": {"l3outs": [{"name": "BGP_L3Out", "external_epgs": [{"name": "Nexus_ExtNet"}]}]},
        "aci_l4l7_services": {"devices": [{"name": "FW"}], "service_graphs": [{"name": "FW_SGT"}]},
    },
    "deployment_status": {"last_pipeline_id": 60},
}

GENERATED = {
    "found": True,
    "pipeline_id": 60,
    "source": "artifact of job 989 (generate_nac), the file this pipeline's Terraform consumed",
    "tenants_in_file": ["sales"],
    "tenant_present": True,
    "intent": {
        "name": "sales",
        "vrfs": [{"name": "Presales_VRF"}],
        "bridge_domains": [{"name": "Presales_BD"}],
        "application_profiles": [{"name": "eCommerce_AP", "endpoint_groups": [{"name": "Web_EPG"}]}],
        "l3outs": [{"name": "BGP_L3Out", "external_epgs": [{"name": "Nexus_ExtNet"}]}],
        "services": {"devices": [{"name": "FW"}], "service_graphs": [{"name": "FW_SGT"}]},
    },
}

FAULTS = [
    {"severity": "minor", "lc": "soaking", "code": "F1298",
     "dn": "uni/epp/rtd-[uni/tn-sales/out-BGP_L3Out/instP-Nexus_ExtNet]/node-101/polDelSt/fault-F1298",
     "descr": "For tenant sales, outside BGP_L3Out, deployment of external EPG Nexus_ExtNet failed on node 101. Reason Node Cannot Deploy EPG"},
    {"severity": "minor", "lc": "soaking", "code": "F0699",
     "dn": "uni/infra/nodecfgcont/node-101/host-[uni/infra/funcprof/accportgrp-Host_Access_IPG]/fault-F0699",
     "descr": "Policies from switch interface policy group  failed to be deployed on node 101. Reason: Node Not Leaf For Infra Policies"},
    {"severity": "minor", "lc": "soaking", "code": "F0764",
     "dn": "uni/tn-sales/lDevVip-FW/fault-F0764",
     "descr": "L4-L7 Devices configuration FW for tenant sales is invalid."},
    {"severity": "minor", "lc": "soaking", "code": "F1690",
     "dn": "uni/tn-sales/lDevVip-FW/vnsConfIssue-missing-cdev/fault-F1690",
     "descr": "Configuration is invalid due to No device found in cluster."},
    {"severity": "minor", "lc": "soaking", "code": "F0757",
     "dn": "uni/tn-sales/AbsGraph-FW_SGT/fault-F0757",
     "descr": "Service graph template FW_SGT for tenant sales configuration is invalid."},
]

REPORT = {
    "found": True,
    "pipeline": {"id": 60, "status": "failed"},
    "jobs": [],
    "awaiting_approval": [],
    "terraform": {
        "terraform_plan": {"job_id": 995, "status": "success", "plan": {"add": 116, "change": 0, "destroy": 0}},
        "terraform_apply": {"job_id": 998, "status": "success", "apply": {"added": 116, "changed": 0, "destroyed": 0}},
    },
    "apic_fault_checks": {
        "verify_apic_faults": {"job_id": 1003, "job_status": "failed",
                               "status": "new_faults", "detail": "", "faults": FAULTS},
    },
}

STATUS = {"found": True, "name": "sales", "nautobot": {"last_pipeline_id": 60}}


def fresh(payload: dict) -> dict:
    return copy.deepcopy(payload)
