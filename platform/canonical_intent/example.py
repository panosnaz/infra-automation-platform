"""Example: construct Canonical Intent objects for the existing web-tenant
vertical slice (Phase 3), and demonstrate the immutability and domain_id
validation guarantees this contract makes.

Run: /usr/bin/python3 platform/canonical_intent/example.py
"""

from __future__ import annotations

from canonical_intent import (
    ApprovalState,
    CanonicalIntent,
    DeploymentContext,
    Environment,
    ExecutionState,
    LifecycleState,
)
from pydantic import ValidationError

# The actual domain_intent this platform already generates and applies —
# taken from platform/netascode/aci/tenants.yaml (Phase 3 vertical slice).
WEB_TENANT_DOMAIN_INTENT = {
    "apic": {
        "tenants": [
            {
                "name": "web-tenant",
                "description": "Platform Engineering vertical slice - web application tenant",
                "vrfs": [{"name": "web-vrf", "description": "Web tenant VRF"}],
                "bridge_domains": [
                    {
                        "name": "web-bd",
                        "unicast_routing": True,
                        "subnets": [
                            {"ip": "10.10.10.1/24", "public": False, "private": True, "shared": False}
                        ],
                        "vrf": "web-vrf",
                    }
                ],
            }
        ]
    }
}


def main() -> None:
    intent = CanonicalIntent(
        engineering_version=1,
        domain_id="cisco_aci",
        domain_intent=WEB_TENANT_DOMAIN_INTENT,
        owner="platform-engineering",
        tags={"cost-center": "eng-platform", "environment-class": "lab"},
    )
    print("CanonicalIntent created:")
    print(intent.model_dump_json(indent=2))

    # Immutability guarantee: attempting to mutate raises.
    try:
        intent.owner = "someone-else"  # type: ignore[misc]
        raise AssertionError("Expected frozen model to reject mutation")
    except ValidationError:
        print("\nConfirmed: CanonicalIntent is immutable (mutation raised ValidationError).")

    # domain_id validation guarantee: unknown domains are rejected now,
    # not silently accepted, well before a Domain Provider Registry exists.
    try:
        CanonicalIntent(
            engineering_version=1,
            domain_id="azure_networking",
            domain_intent={},
            owner="platform-engineering",
        )
        raise AssertionError("Expected unknown domain_id to be rejected")
    except ValidationError as exc:
        print(f"Confirmed: unknown domain_id rejected -> {exc.errors()[0]['msg']}")

    context = DeploymentContext(
        intent_id=intent.intent_id,
        engineering_version=intent.engineering_version,
        requester="panos",
        entry_point="cli",
        environment=Environment.LAB,
        approval_state=ApprovalState.NONE_REQUIRED,
    )
    print("\nDeploymentContext created:")
    print(context.model_dump_json(indent=2))

    state = ExecutionState(
        deployment_id=context.deployment_id,
        lifecycle_state=LifecycleState.DEPLOYED,
        policy_decision="allow",
    )
    print("\nExecutionState created:")
    print(state.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
