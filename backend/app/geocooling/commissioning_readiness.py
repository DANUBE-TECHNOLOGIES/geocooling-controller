"""Read-only GeoCooling commissioning readiness gate."""

from __future__ import annotations

from typing import Any, Mapping


READINESS_STATES = (
    "UPSTREAM_NOT_READY",
    "IDENTIFICATION_REQUIRED",
    "MAPPING_INCOMPLETE",
    "TELEMETRY_READY",
    "FIELD_CERTIFICATION_REQUIRED",
    "READY_FOR_RELEASE",
)


def build_commissioning_readiness(
    telemetry_health: Mapping[str, Any],
    *,
    physical_identification_confirmed: bool = False,
    field_certification_confirmed: bool = False,
) -> dict[str, Any]:
    """Return the next commissioning gate without touching hardware.

    The gate is deliberately conservative. Observed candidates are never treated
    as identified sensors, and telemetry readiness never implies field
    certification.
    """

    upstream_state = str(telemetry_health.get("upstream_state") or "UPSTREAM_EMPTY")
    roles = telemetry_health.get("roles") or {}
    configured_role_count = int(telemetry_health.get("configured_role_count") or 0)
    role_count = len(roles) or 6
    all_roles_ready = bool(telemetry_health.get("ready"))

    if upstream_state != "OBSERVED":
        state = "UPSTREAM_NOT_READY"
        next_action = "Restore WT32/ESPHome telemetry publication to MQTT."
    elif not physical_identification_confirmed:
        state = "IDENTIFICATION_REQUIRED"
        next_action = "Physically confirm the identity of each observed hydraulic sensor."
    elif configured_role_count < role_count:
        state = "MAPPING_INCOMPLETE"
        next_action = "Configure the six GEOCOOLING_*_SENSOR mappings from confirmed identities."
    elif not all_roles_ready:
        state = "MAPPING_INCOMPLETE"
        next_action = "Resolve absent, incorrect or stale mapped telemetry until all six roles are OK."
    elif not field_certification_confirmed:
        state = "FIELD_CERTIFICATION_REQUIRED"
        next_action = "Perform the physical EV and M11/M13 field certification with hardware still controlled manually."
    else:
        state = "READY_FOR_RELEASE"
        next_action = "Commissioning gates are complete; release preparation may proceed."

    return {
        "component": "geocooling_commissioning_readiness",
        "state": state,
        "ready_for_release": state == "READY_FOR_RELEASE",
        "telemetry_ready": all_roles_ready,
        "upstream_state": upstream_state,
        "physical_identification_confirmed": physical_identification_confirmed,
        "field_certification_confirmed": field_certification_confirmed,
        "configured_role_count": configured_role_count,
        "role_count": role_count,
        "next_action": next_action,
        "read_only": True,
        "hardware_touched": False,
        "automatic_hardware_enable": False,
    }
