from __future__ import annotations

from typing import Any

from app.geocooling.brain_v2.integration.home_assistant_bridge import (
    HomeAssistantBridge,
)


class SafeHomeAssistantBridge(HomeAssistantBridge):
    """Fail-safe Home Assistant presentation layer.

    The historical package generator used ``float(0)`` / ``int(0)`` fallbacks.
    For thermal telemetry, zero is a valid-looking physical value and therefore
    must never be used to represent a missing observation. This wrapper keeps
    the existing bridge contract while making missing values render as unknown.
    """

    VERSION = "C022.7-HOME-ASSISTANT-BRIDGE-1.1-SAFE"

    CRITICAL_MEASUREMENTS = (
        "indoor_temperature_c",
        "indoor_humidity_percent",
        "floor_surface_temperature_c",
        "floor_supply_temperature_c",
        "floor_return_temperature_c",
    )

    def state(self) -> dict[str, Any]:
        payload = super().state()
        missing = [
            name
            for name in self.CRITICAL_MEASUREMENTS
            if payload.get(name) is None
        ]

        payload["version"] = self.VERSION
        payload["telemetry_complete"] = not missing
        payload["missing_measurements"] = missing
        payload["fail_safe_missing_values"] = True
        return payload

    def package_yaml(self, base_url: str) -> str:
        package = super().package_yaml(base_url)

        # Never turn an absent physical/derived measurement into a numeric zero.
        # Jinja's ``none`` propagates an unavailable/unknown state to HA instead.
        package = package.replace("| float(0)", "| float(none)")
        package = package.replace("| int(0)", "| int(none)")

        package = package.replace(
            "          - relay_command\n",
            "          - relay_command\n"
            "          - telemetry_complete\n"
            "          - missing_measurements\n"
            "          - fail_safe_missing_values\n",
            1,
        )

        header = (
            "# FAIL-SAFE: missing measurements remain unknown; "
            "they are never coerced to zero.\n"
        )
        return header + package
