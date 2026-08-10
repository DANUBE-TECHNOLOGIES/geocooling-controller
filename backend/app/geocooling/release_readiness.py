"""Pure GeoCooling release-readiness evaluator.

The evaluator is deliberately read-only. It combines commissioning state,
hardware activation policy and runtime safety flags without touching hardware,
MQTT or persistent storage.
"""

from __future__ import annotations

from typing import Any, Mapping


DANGEROUS_RUNTIME_FLAGS = (
    "hardware_armed",
    "hardware_sequence_enabled",
    "autopilot_enabled",
    "autopilot_allow_real_driver",
)


def build_release_readiness(
    commissioning: Mapping[str, Any],
    activation_policy: Mapping[str, Any],
    runtime_flags: Mapping[str, Any],
) -> dict[str, Any]:
    commissioning_state = str(commissioning.get("state") or "UNKNOWN")
    ready_for_release = commissioning_state == "READY_FOR_RELEASE"

    active_dangerous_flags = [
        name
        for name in DANGEROUS_RUNTIME_FLAGS
        if bool(runtime_flags.get(name, False))
    ]

    blockers: list[str] = []

    if not ready_for_release:
        blockers.append(
            str(
                commissioning.get("next_action")
                or f"Commissioning incomplete: {commissioning_state}"
            )
        )

    if active_dangerous_flags:
        blockers.append(
            "Return runtime activation flags to safe defaults before deployment: "
            + ", ".join(active_dangerous_flags)
        )

    if blockers:
        if ready_for_release and active_dangerous_flags:
            state = "CONFIG_REVIEW_REQUIRED"
        else:
            state = "COMMISSIONING_BLOCKED"
    else:
        state = "READY_FOR_DEPLOYMENT"

    return {
        "component": "geocooling_release_readiness",
        "state": state,
        "software_release_candidate": True,
        "commissioning_state": commissioning_state,
        "commissioning_ready": ready_for_release,
        "deployment_ready": state == "READY_FOR_DEPLOYMENT",
        "runtime_safe_defaults": not active_dangerous_flags,
        "active_dangerous_flags": active_dangerous_flags,
        "blockers": blockers,
        "activation_policy": dict(activation_policy),
        "read_only": True,
        "hardware_touched": False,
        "mqtt_publish": False,
        "database_write": False,
    }
