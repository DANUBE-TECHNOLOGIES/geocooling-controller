from __future__ import annotations

from typing import Any

from app.geocooling.brain_v2.integration.home_assistant_bridge import (
    HomeAssistantBridge,
)


class SafeHomeAssistantBridge(HomeAssistantBridge):
    """Fail-safe Home Assistant presentation layer.

    Missing thermal telemetry must never be represented by a plausible numeric
    zero. The wrapper also completes the hydraulic surface by exposing the six
    GeoCooling telemetry roles without granting any hardware authority.
    """

    VERSION = "C022.7-HOME-ASSISTANT-BRIDGE-1.2-SAFE"

    CRITICAL_MEASUREMENTS = (
        "floor_surface_temperature_c",
        "floor_supply_temperature_c",
        "floor_return_temperature_c",
        "source_inlet_temperature_c",
        "source_outlet_temperature_c",
        "flow_rate_l_min",
    )

    def state(self) -> dict[str, Any]:
        payload = super().state()
        snapshot = self._latest_snapshot()

        payload["source_inlet_temperature_c"] = self._safe_round(
            snapshot.get("source_inlet_temperature_c")
        )
        payload["source_outlet_temperature_c"] = self._safe_round(
            snapshot.get("source_outlet_temperature_c")
        )
        payload["flow_rate_l_min"] = self._safe_round(
            snapshot.get("flow_rate_l_min"),
            2,
        )

        missing = [
            name
            for name in self.CRITICAL_MEASUREMENTS
            if payload.get(name) is None
        ]

        payload["version"] = self.VERSION
        payload["telemetry_complete"] = not missing
        payload["missing_measurements"] = missing
        payload["fail_safe_missing_values"] = True
        payload["hydraulic_role_count"] = len(self.CRITICAL_MEASUREMENTS)
        payload["hydraulic_roles_ready"] = (
            len(self.CRITICAL_MEASUREMENTS) - len(missing)
        )
        return payload

    def package_yaml(self, base_url: str) -> str:
        package = super().package_yaml(base_url)

        # Never turn an absent physical/derived measurement into a numeric zero.
        package = package.replace("| float(0)", "| float(none)")
        package = package.replace("| int(0)", "| int(none)")

        package = package.replace(
            "          - floor_return_temperature_c\n",
            "          - floor_return_temperature_c\n"
            "          - source_inlet_temperature_c\n"
            "          - source_outlet_temperature_c\n"
            "          - flow_rate_l_min\n",
            1,
        )

        package = package.replace(
            "          - relay_command\n",
            "          - relay_command\n"
            "          - telemetry_complete\n"
            "          - missing_measurements\n"
            "          - fail_safe_missing_values\n"
            "          - hydraulic_role_count\n"
            "          - hydraulic_roles_ready\n",
            1,
        )

        marker = "      - name: GeoCooling cible Brain\n"
        hydraulic_sensors = """      - name: GeoCooling température entrée source
        unique_id: geocooling_brain_v2_source_inlet_temperature
        state: >
          {{ state_attr('sensor.geocooling_brain_v2', 'source_inlet_temperature_c') | float(none) }}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling température sortie source
        unique_id: geocooling_brain_v2_source_outlet_temperature
        state: >
          {{ state_attr('sensor.geocooling_brain_v2', 'source_outlet_temperature_c') | float(none) }}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling débit hydraulique
        unique_id: geocooling_brain_v2_flow_rate
        state: >
          {{ state_attr('sensor.geocooling_brain_v2', 'flow_rate_l_min') | float(none) }}
        unit_of_measurement: "L/min"
        state_class: measurement
        icon: mdi:water-pump

"""
        if marker in package:
            package = package.replace(
                marker,
                hydraulic_sensors + marker,
                1,
            )

        header = (
            "# FAIL-SAFE: missing measurements remain unknown; "
            "they are never coerced to zero.\n"
        )
        return header + package
