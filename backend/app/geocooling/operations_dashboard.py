from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _safe_call(callable_obj, default: Any) -> Any:
    try:
        value = callable_obj()
    except Exception:
        return default
    return value if value is not None else default


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class GeoCoolingOperationsDashboard:
    """Vue d'exploitation consolidée, sans effet sur les actionneurs."""

    def __init__(self, controller: Any, hardware_control: Any | None = None) -> None:
        self.controller = controller
        self.hardware_control = hardware_control

    def _hardware(self) -> dict[str, Any]:
        if self.hardware_control is not None:
            status = _safe_call(self.hardware_control.status, {})
            if isinstance(status, dict):
                return status

        status = _mapping(_safe_call(self.controller.status, {}))
        return {
            "driver_name": status.get("driver_name"),
            "armed": False,
            "connected": False,
            "ready": _mapping(status.get("device")).get("ready", False),
            "valve_open": status.get("valve_open", False),
            "pump_running": status.get("pump_running", False),
            "controller": {
                "mode": status.get("mode"),
                "state": status.get("state"),
            },
        }

    @staticmethod
    def _diagnostics(
        *,
        brain: dict[str, Any],
        hardware: dict[str, Any],
        thermal: dict[str, Any],
        autopilot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []

        def add(code: str, severity: str, message: str, blocking: bool) -> None:
            diagnostics.append(
                {
                    "code": code,
                    "severity": severity,
                    "message": message,
                    "blocking": blocking,
                }
            )

        driver = str(hardware.get("driver_name") or "unknown")
        if driver == "simulation":
            add("SIMULATION_MODE", "info", "Le driver matériel est en simulation.", True)
        elif not hardware.get("connected", False):
            add("DRIVER_DISCONNECTED", "critical", "Le driver matériel n'est pas connecté.", True)

        if not hardware.get("armed", False):
            add("HARDWARE_DISARMED", "warning", "Le matériel est désarmé.", True)

        if not hardware.get("ready", False):
            add("HARDWARE_NOT_READY", "warning", "Le matériel n'est pas prêt.", True)

        safety = _mapping(thermal.get("safety"))
        if safety and not safety.get("safe", False):
            add(
                "THERMAL_SAFETY",
                "critical",
                str(safety.get("reason") or "Sécurité thermique bloquante."),
                True,
            )

        if not autopilot.get("enabled", False):
            add("AUTOPILOT_DISABLED", "info", "Le pilotage automatique est désactivé.", False)
        elif not autopilot.get("allowed", False):
            add(
                "AUTOPILOT_BLOCKED",
                "warning",
                str(autopilot.get("reason") or "Le pilotage automatique est bloqué."),
                True,
            )

        explanation = _mapping(brain.get("explanation"))
        for item in explanation.get("blocking_conditions") or []:
            if isinstance(item, dict):
                message = str(item.get("reason") or item.get("message") or "Blocage Brain")
            else:
                message = str(item)
            add("BRAIN_BLOCKING_CONDITION", "warning", message, True)

        if not diagnostics:
            add("READY", "ok", "Aucun blocage détecté.", False)

        return diagnostics

    def snapshot(self) -> dict[str, Any]:
        brain = _mapping(_safe_call(self.controller.brain_status, {}))
        thermal = _mapping(_safe_call(self.controller.thermal_status, {}))
        autopilot = _mapping(_safe_call(self.controller.autopilot_status, {}))
        hardware = self._hardware()
        metrics = _mapping(
            _safe_call(
                getattr(self.controller.brain, "decision_metrics", lambda: {}),
                {},
            )
        )
        latest = _mapping(thermal.get("latest"))
        diagnostics = self._diagnostics(
            brain=brain,
            hardware=hardware,
            thermal=thermal,
            autopilot=autopilot,
        )

        return {
            "component": "geocooling",
            "view": "operations_dashboard",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": _mapping(hardware.get("controller")).get("mode"),
            "state": _mapping(hardware.get("controller")).get("state"),
            "brain": {
                "decision_id": brain.get("decision_id"),
                "decision": brain.get("decision"),
                "confidence": brain.get("confidence"),
                "score": brain.get("total_score"),
                "reason": brain.get("reason") or [],
                "explanation": brain.get("explanation") or {},
                "generated_at": brain.get("generated_at"),
            },
            "metrics": metrics,
            "hardware": {
                "driver_name": hardware.get("driver_name"),
                "armed": bool(hardware.get("armed", False)),
                "connected": bool(hardware.get("connected", False)),
                "ready": bool(hardware.get("ready", False)),
                "valve_open": bool(hardware.get("valve_open", False)),
                "pump_running": bool(hardware.get("pump_running", False)),
                "last_action": hardware.get("last_action"),
            },
            "thermal": {
                "indoor_temperature_c": latest.get("indoor_temperature_c"),
                "indoor_humidity_percent": latest.get("indoor_humidity_percent"),
                "outdoor_temperature_c": latest.get("outdoor_temperature_c"),
                "surface_temperature_c": latest.get("surface_temperature_c"),
                "floor_supply_temperature_c": latest.get("floor_supply_temperature_c"),
                "floor_return_temperature_c": latest.get("floor_return_temperature_c"),
                "source_inlet_temperature_c": latest.get("source_inlet_temperature_c"),
                "source_outlet_temperature_c": latest.get("source_outlet_temperature_c"),
                "flow_rate_l_min": latest.get("flow_rate_l_min"),
                "cooling_power_kw": thermal.get("cooling_power_kw"),
                "floor_delta_t_c": thermal.get("floor_delta_t_c"),
                "safety": thermal.get("safety") or {},
            },
            "automation": {
                "enabled": bool(autopilot.get("enabled", False)),
                "allowed": bool(autopilot.get("allowed", False)),
                "reason": autopilot.get("reason"),
                "last_decision": autopilot.get("last_decision"),
                "last_action": autopilot.get("last_action"),
                "last_run_at": autopilot.get("last_run_at"),
            },
            "diagnostics": diagnostics,
            "blocking": any(item.get("blocking") for item in diagnostics),
        }
