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

    # Lab environment + approval_state=NONE_REQUIRED means the Approval
    # Workflow (ADR-015) resolves immediately within RequestDeployment —
    # this ExecutionState never rests at PENDING_APPROVAL at all.
    state = ExecutionState(
        deployment_id=context.deployment_id,
        lifecycle_state=LifecycleState.DEPLOYING,
        desired_version=intent.engineering_version,
        applied_version=None,  # not yet confirmed live — only set after successful validation
        approval_decision="not_required",
    )
    print("\nExecutionState created:")
    print(state.model_dump_json(indent=2))

    # Once validation confirms deployed == desired, applied_version catches
    # up to desired_version and lifecycle_state becomes STABLE. If a later
    # drift check finds the live infrastructure no longer matches
    # applied_version's domain_intent, lifecycle_state becomes DRIFTED —
    # desired_version and applied_version diverging is exactly what makes
    # drift detectable without re-deriving it from raw infrastructure state.
    state = state.model_copy(
        update={
            "lifecycle_state": LifecycleState.STABLE,
            "applied_version": intent.engineering_version,
            "validated_at": state.last_updated_at,
        }
    )
    print("\nExecutionState after successful validation (STABLE):")
    print(state.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
