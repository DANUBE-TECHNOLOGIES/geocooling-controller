"""
GeoCooling Release 0.7.0 — Digital Twin.

Source de vérité passive pour les essais hydrauliques simulés.
Ce module ne publie rien vers MQTT et ne pilote aucun actionneur.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class GeoCoolingDigitalTwin:
    VERSION = "0.7.0"

    def __init__(self, *, controller: Any, event_bus: Any = None) -> None:
        self.controller = controller
        self.event_bus = event_bus
        self._lock = threading.RLock()
        self._created_at = self._utc_now()
        self._revision = 0
        self._state = self._default_state()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe(value: Any, depth: int = 0, seen: set[int] | None = None) -> Any:
        if seen is None:
            seen = set()
        if depth > 6:
            return "<MAX_DEPTH>"
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        oid = id(value)
        if oid in seen:
            return "<RECURSION>"
        seen.add(oid)
        if isinstance(value, dict):
            return {
                str(key): GeoCoolingDigitalTwin._safe(
                    item, depth + 1, seen.copy()
                )
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [
                GeoCoolingDigitalTwin._safe(
                    item, depth + 1, seen.copy()
                )
                for item in value
            ]
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, (bool, int, float, str)):
            return enum_value
        return repr(value)

    def _default_state(self) -> dict[str, Any]:
        return {
            "component": "digital_twin",
            "version": self.VERSION,
            "created_at": self._created_at,
            "updated_at": self._created_at,
            "revision": 0,
            "mode": "SIMULATION",
            "passive_only": True,
            "installation": {
                "hydraulic_loop": {
                    "valve": {"state": "CLOSED", "source": "default"},
                    "pump": {"state": "OFF", "source": "default"},
                    "flow_l_min": None,
                    "pressure_bar": None,
                },
                "thermal_loop": {
                    "source_in_c": None,
                    "source_out_c": None,
                    "floor_in_c": None,
                    "floor_out_c": None,
                    "delta_t_c": None,
                    "power_w": None,
                },
                "building": {
                    "indoor_c": None,
                    "outdoor_c": None,
                    "humidity_pct": None,
                },
                "controller": {
                    "state": "UNKNOWN",
                    "driver": "UNKNOWN",
                    "bridge_armed": False,
                    "hardware_certification": None,
                },
            },
            "quality": {
                "available_measurements": 0,
                "missing_measurements": [],
                "status": "EMPTY",
            },
        }

    def _call(self, target: Any, method_name: str) -> dict[str, Any]:
        method = getattr(target, method_name, None)
        if not callable(method):
            return {}
        try:
            result = method()
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _first_number(*values: Any) -> float | None:
        for value in values:
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return float(value)
        return None

    @staticmethod
    def _nested(data: dict[str, Any], *keys: str) -> Any:
        current: Any = data
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def refresh(self, *, trigger: str = "manual") -> dict[str, Any]:
        controller_status = self._call(self.controller, "status")
        thermal_status = self._call(self.controller, "thermal_status")

        bridge = getattr(self.controller, "controller_command_bridge", None)
        bridge_status = self._call(bridge, "status") if bridge is not None else {}

        certification = getattr(
            self.controller, "hardware_certification", None
        )
        certificate = self._call(certification, "certificate")
        certificate_data = certificate.get("certificate") if certificate else None

        state_name = str(
            controller_status.get(
                "state", controller_status.get("mode", "UNKNOWN")
            )
        )
        driver_name = str(
            controller_status.get(
                "driver", controller_status.get("driver_name", "UNKNOWN")
            )
        )

        thermal = thermal_status.get("latest", thermal_status)
        if not isinstance(thermal, dict):
            thermal = {}

        source_in = self._first_number(
            thermal.get("source_in_c"),
            thermal.get("inlet_temperature"),
            thermal.get("source_in"),
        )
        source_out = self._first_number(
            thermal.get("source_out_c"),
            thermal.get("outlet_temperature"),
            thermal.get("source_out"),
        )
        floor_in = self._first_number(
            thermal.get("floor_in_c"),
            thermal.get("supply_temperature"),
            thermal.get("floor_in"),
        )
        floor_out = self._first_number(
            thermal.get("floor_out_c"),
            thermal.get("return_temperature"),
            thermal.get("floor_out"),
        )
        flow = self._first_number(
            thermal.get("flow_l_min"),
            thermal.get("flow"),
            thermal.get("flow_rate"),
        )
        pressure = self._first_number(
            thermal.get("pressure_bar"),
            thermal.get("pressure"),
        )
        power = self._first_number(
            thermal.get("power_w"),
            thermal.get("thermal_power_w"),
        )
        indoor = self._first_number(
            thermal.get("indoor_c"),
            thermal.get("indoor_temperature"),
        )
        outdoor = self._first_number(
            thermal.get("outdoor_c"),
            thermal.get("outdoor_temperature"),
        )
        humidity = self._first_number(
            thermal.get("humidity_pct"),
            thermal.get("humidity"),
        )

        delta_t = None
        if source_in is not None and source_out is not None:
            delta_t = round(source_out - source_in, 3)

        valve_state = str(
            controller_status.get(
                "valve_state",
                self._nested(
                    controller_status, "device", "valve_state"
                )
                or "UNKNOWN",
            )
        )
        pump_state = str(
            controller_status.get(
                "pump_state",
                self._nested(
                    controller_status, "device", "pump_state"
                )
                or "UNKNOWN",
            )
        )

        values = {
            "flow_l_min": flow,
            "pressure_bar": pressure,
            "source_in_c": source_in,
            "source_out_c": source_out,
            "floor_in_c": floor_in,
            "floor_out_c": floor_out,
            "delta_t_c": delta_t,
            "power_w": power,
            "indoor_c": indoor,
            "outdoor_c": outdoor,
            "humidity_pct": humidity,
        }
        missing = [key for key, value in values.items() if value is None]
        available = len(values) - len(missing)

        with self._lock:
            self._revision += 1
            now = self._utc_now()
            self._state = {
                "component": "digital_twin",
                "version": self.VERSION,
                "created_at": self._created_at,
                "updated_at": now,
                "revision": self._revision,
                "trigger": trigger,
                "mode": "SIMULATION",
                "passive_only": True,
                "installation": {
                    "hydraulic_loop": {
                        "valve": {
                            "state": valve_state,
                            "source": "controller",
                        },
                        "pump": {
                            "state": pump_state,
                            "source": "controller",
                        },
                        "flow_l_min": flow,
                        "pressure_bar": pressure,
                    },
                    "thermal_loop": {
                        "source_in_c": source_in,
                        "source_out_c": source_out,
                        "floor_in_c": floor_in,
                        "floor_out_c": floor_out,
                        "delta_t_c": delta_t,
                        "power_w": power,
                    },
                    "building": {
                        "indoor_c": indoor,
                        "outdoor_c": outdoor,
                        "humidity_pct": humidity,
                    },
                    "controller": {
                        "state": state_name,
                        "driver": driver_name,
                        "bridge_armed": bool(
                            bridge_status.get("armed", False)
                        ),
                        "hardware_certification": certificate_data,
                    },
                },
                "quality": {
                    "available_measurements": available,
                    "missing_measurements": missing,
                    "status": (
                        "COMPLETE"
                        if not missing
                        else "PARTIAL"
                        if available
                        else "EMPTY"
                    ),
                },
            }
            result = deepcopy(self._state)

        self._publish("digital_twin.updated", result)
        return result

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        try:
            self.event_bus.publish(
                event_type=event_type,
                source="digital-twin",
                payload=self._safe(payload),
                level="INFO",
            )
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = deepcopy(self._state)
        return {
            "component": "digital_twin",
            "version": self.VERSION,
            "running": True,
            "passive_only": True,
            "revision": state["revision"],
            "updated_at": state["updated_at"],
            "quality": state["quality"],
        }

    def snapshot(self, *, refresh: bool = True) -> dict[str, Any]:
        if refresh:
            return self.refresh(trigger="snapshot")
        with self._lock:
            return deepcopy(self._state)

    def apply_simulation(
        self,
        *,
        valve_state: str | None = None,
        pump_state: str | None = None,
        flow_l_min: float | None = None,
        source_in_c: float | None = None,
        source_out_c: float | None = None,
    ) -> dict[str, Any]:
        """Modifie uniquement le jumeau numérique, jamais le matériel."""
        with self._lock:
            self._revision += 1
            now = self._utc_now()
            hydraulic = self._state["installation"]["hydraulic_loop"]
            thermal = self._state["installation"]["thermal_loop"]

            if valve_state is not None:
                hydraulic["valve"] = {
                    "state": str(valve_state).upper(),
                    "source": "simulation",
                }
            if pump_state is not None:
                hydraulic["pump"] = {
                    "state": str(pump_state).upper(),
                    "source": "simulation",
                }
            if flow_l_min is not None:
                hydraulic["flow_l_min"] = float(flow_l_min)
            if source_in_c is not None:
                thermal["source_in_c"] = float(source_in_c)
            if source_out_c is not None:
                thermal["source_out_c"] = float(source_out_c)

            if (
                thermal.get("source_in_c") is not None
                and thermal.get("source_out_c") is not None
            ):
                thermal["delta_t_c"] = round(
                    thermal["source_out_c"]
                    - thermal["source_in_c"],
                    3,
                )

            self._state["updated_at"] = now
            self._state["revision"] = self._revision
            self._state["trigger"] = "simulation"
            result = deepcopy(self._state)

        self._publish("digital_twin.simulated", result)
        return result
