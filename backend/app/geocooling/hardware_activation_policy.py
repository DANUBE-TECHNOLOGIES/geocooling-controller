"""Central read-only policy for GeoCooling hardware activation paths."""

from __future__ import annotations

from typing import Any, Mapping


FIELD_STAGE = "FIELD_CERTIFICATION_REQUIRED"
RELEASE_STAGE = "READY_FOR_RELEASE"


def build_hardware_activation_policy(
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe which positive hardware paths are allowed for a readiness state.

    This function never touches hardware. OFF/safe-state actions are deliberately
    always allowed by policy so a degraded commissioning state can never block a
    shutdown.
    """

    state = str(readiness.get("state") or "UNKNOWN")
    field_stage_reached = state in {FIELD_STAGE, RELEASE_STAGE}
    release_ready = state == RELEASE_STAGE

    return {
        "component": "geocooling_hardware_activation_policy",
        "readiness_state": state,
        "controller_start_allowed": release_ready,
        "manual_arm_allowed": field_stage_reached,
        "manual_positive_commands_allowed": release_ready,
        "commissioning_tests_allowed": field_stage_reached,
        "safe_stop_allowed": True,
        "pump_stop_allowed": True,
        "valve_close_allowed": True,
        "disarm_allowed": True,
        "read_only": True,
        "hardware_touched": False,
        "rules": {
            "controller_start": "READY_FOR_RELEASE",
            "manual_arm": "FIELD_CERTIFICATION_REQUIRED or READY_FOR_RELEASE",
            "manual_positive_commands": "READY_FOR_RELEASE",
            "commissioning_tests": "FIELD_CERTIFICATION_REQUIRED or READY_FOR_RELEASE",
            "safe_actions": "always allowed",
        },
    }
