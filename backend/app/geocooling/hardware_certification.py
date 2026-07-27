"""
C016.1R4 — Hardware Certification.

Certification passive consolidée avant essais hydrauliques réels.

Garanties absolues :
- aucune publication MQTT ;
- aucune commande de relais ;
- aucun changement de driver ;
- aucun armement automatique du bridge ;
- aucun passage automatique en READY_FOR_WATER_TEST sans preuves suffisantes.
"""

from __future__ import annotations

import os
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class HardwareCertificationEngine:
    PATCH_VERSION = "C016.1R4"

    def __init__(
        self,
        *,
        controller: Any,
        sensor_discovery: Any,
        sensor_validation: Any,
        mqtt_preflight: Any,
        event_bus: Any = None,
        history_capacity: int = 500,
    ) -> None:
        self.controller = controller
        self.sensor_discovery = sensor_discovery
        self.sensor_validation = sensor_validation
        self.mqtt_preflight = mqtt_preflight
        self.event_bus = event_bus

        self.expected_sensor_count = max(
            1,
            int(os.getenv("GEOCOOLING_EXPECTED_DS18B20_COUNT", "4")),
        )
        self.minimum_relay_count = max(
            1,
            int(os.getenv("GEOCOOLING_MIN_RELAY_COUNT", "2")),
        )
        self.minimum_score = max(
            1,
            min(
                100,
                int(os.getenv("GEOCOOLING_HARDWARE_MIN_SCORE", "85")),
            ),
        )

        self.history_capacity = max(50, int(history_capacity))
        self._lock = threading.RLock()
        self._history: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )
        self._latest: dict[str, Any] | None = None
        self._started_at = self._utc_now()
        self._metrics = {
            "evaluation_count": 0,
            "certified_count": 0,
            "blocked_count": 0,
            "last_evaluated_at": None,
            "last_level": None,
            "last_score": None,
            "last_error": None,
        }

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, dict):
            return {
                str(key): HardwareCertificationEngine._safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [
                HardwareCertificationEngine._safe(item)
                for item in value
            ]
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, (bool, int, float, str)):
            return enum_value
        return repr(value)

    def _call(
        self,
        target: Any,
        method_name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        method = getattr(target, method_name, None)
        if not callable(method):
            return {}
        try:
            value = method(**kwargs)
            return value if isinstance(value, dict) else {}
        except Exception as exc:
            self._metrics["last_error"] = repr(exc)
            return {}

    def _publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        level: str,
    ) -> None:
        if self.event_bus is None:
            return
        try:
            self.event_bus.publish(
                event_type=event_type,
                source="hardware-certification",
                payload=self._safe(payload),
                level=level,
            )
            self._metrics["last_error"] = None
        except Exception as exc:
            self._metrics["last_error"] = repr(exc)

    @staticmethod
    def _check(
        check_id: str,
        passed: bool,
        blocking: bool,
        observed: Any,
        expected: Any,
        remediation: str,
    ) -> dict[str, Any]:
        return {
            "id": check_id,
            "passed": bool(passed),
            "blocking": bool(blocking),
            "observed": observed,
            "expected": expected,
            "remediation": remediation,
        }

    @staticmethod
    def _extract_topics(discovery: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [
            discovery.get("discovery", {}).get("topics"),
            discovery.get("topics"),
        ]
        for candidate in candidates:
            if isinstance(candidate, list):
                return [
                    item for item in candidate
                    if isinstance(item, dict)
                ]
        return []

    @staticmethod
    def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
        lower = text.lower()
        return any(needle in lower for needle in needles)

    def evaluate(self, *, trigger: str = "manual") -> dict[str, Any]:
        generated_at = self._utc_now()

        discovery = self._call(
            self.sensor_discovery,
            "evaluate",
            trigger="hardware-certification",
        )
        validation = self._call(
            self.sensor_validation,
            "evaluate",
            trigger="hardware-certification",
        )
        preflight = self._call(
            self.mqtt_preflight,
            "evaluate",
            trigger="hardware-certification",
        )
        controller_status = self._call(self.controller, "status")

        bridge = getattr(
            self.controller,
            "controller_command_bridge",
            None,
        )
        bridge_status = self._call(bridge, "status") if bridge else {}
        bridge_armed = bool(bridge_status.get("armed", False))

        topics = self._extract_topics(discovery)
        topic_names = [
            str(item.get("topic") or "")
            for item in topics
        ]

        wt32_topics = [
            topic for topic in topic_names
            if self._contains_any(
                topic,
                ("wt32", "geocooling", "esphome", "ethernet"),
            )
        ]

        sensor_topics = [
            topic for topic in topic_names
            if self._contains_any(
                topic,
                ("temperature", "ds18b20", "onewire", "sensor"),
            )
        ]

        relay_topics = [
            topic for topic in topic_names
            if self._contains_any(
                topic,
                (
                    "relay",
                    "switch",
                    "pump",
                    "circulator",
                    "circulateur",
                    "valve",
                    "electrovanne",
                ),
            )
        ]

        output_state_topics = [
            topic for topic in relay_topics
            if self._contains_any(
                topic,
                ("/state", "/status", "state/", "status/"),
            )
        ]

        command_topics = [
            topic for topic in relay_topics
            if self._contains_any(
                topic,
                ("/set", "/cmd", "/command", "set/", "cmd/", "command/"),
            )
        ]

        sensor_count = int(
            validation.get(
                "sensor_count",
                discovery.get(
                    "discovery",
                    {},
                ).get("sensor_count", 0),
            )
            or 0
        )
        certified_sensor_count = int(
            validation.get("certified_sensor_count", 0) or 0
        )
        validation_ready = bool(
            validation.get(
                "ready",
                validation.get("ready_for_mqtt_driver", False),
            )
        )
        preflight_ready = bool(
            preflight.get(
                "ready",
                preflight.get("ready_for_mqtt_driver", False),
            )
        )

        mqtt_connected = bool(
            preflight.get("mqtt", {}).get("connected", False)
        )
        heartbeat_count = int(
            preflight.get("mqtt", {}).get(
                "fresh_heartbeat_topic_count", 0
            )
            or 0
        )

        driver_name = str(
            controller_status.get(
                "driver",
                controller_status.get("driver_name", ""),
            )
        )
        simulation_retained = (
            not driver_name
            or "simulation" in driver_name.lower()
        )

        controller_state = str(
            controller_status.get(
                "state",
                controller_status.get("mode", ""),
            )
        )
        controller_idle = (
            not controller_state
            or controller_state.upper()
            in {"OFF", "IDLE", "STOPPED", "SIMULATION"}
        )

        device = controller_status.get("device", {})
        if not isinstance(device, dict):
            device = {}

        device_ready = bool(
            device.get(
                "ready",
                controller_status.get("ready", True),
            )
        )
        device_connected = bool(
            device.get(
                "connected",
                controller_status.get("connected", True),
            )
        )

        checks = [
            self._check(
                "chain.discovery.available",
                bool(discovery),
                True,
                bool(discovery),
                True,
                "Restaurer C016.1R1.",
            ),
            self._check(
                "chain.sensor_validation.certified",
                validation_ready,
                True,
                validation.get("level"),
                "SENSORS_CERTIFIED",
                "Terminer C016.1R2.",
            ),
            self._check(
                "chain.mqtt_preflight.ready",
                preflight_ready,
                True,
                preflight.get("level"),
                "READY_FOR_MQTT_DRIVER",
                "Terminer C016.1R3.",
            ),
            self._check(
                "hardware.mqtt_connected",
                mqtt_connected,
                True,
                mqtt_connected,
                True,
                "Rétablir la connexion au broker.",
            ),
            self._check(
                "hardware.wt32_detected",
                bool(wt32_topics) or device_connected,
                True,
                {
                    "matching_topics": wt32_topics[:20],
                    "device_connected": device_connected,
                },
                "WT32 détecté",
                "Vérifier le WT32, Ethernet et le préfixe MQTT.",
            ),
            self._check(
                "hardware.heartbeat_fresh",
                heartbeat_count >= 1,
                True,
                heartbeat_count,
                ">= 1",
                "Publier un heartbeat ou availability frais.",
            ),
            self._check(
                "hardware.ds18b20_count",
                sensor_count >= self.expected_sensor_count,
                True,
                sensor_count,
                f">= {self.expected_sensor_count}",
                "Faire détecter les quatre DS18B20.",
            ),
            self._check(
                "hardware.ds18b20_certified",
                certified_sensor_count >= self.expected_sensor_count,
                True,
                certified_sensor_count,
                f">= {self.expected_sensor_count}",
                "Corriger les sondes non certifiées.",
            ),
            self._check(
                "hardware.sensor_topics_present",
                len(sensor_topics) >= self.expected_sensor_count,
                False,
                len(sensor_topics),
                f">= {self.expected_sensor_count}",
                "Exposer explicitement les topics des sondes.",
            ),
            self._check(
                "hardware.output_state_contract",
                len(output_state_topics) >= self.minimum_relay_count,
                True,
                output_state_topics[:30],
                f">= {self.minimum_relay_count} états de sortie",
                "Exposer les états Waveshare de la pompe et de la vanne.",
            ),
            self._check(
                "hardware.command_contract_detected",
                len(command_topics) >= self.minimum_relay_count,
                False,
                command_topics[:30],
                f">= {self.minimum_relay_count} topics de commande",
                "Déclarer les topics de commande sans les actionner.",
            ),
            self._check(
                "hardware.device_ready",
                device_ready,
                True,
                device_ready,
                True,
                "Vérifier l'état du DeviceManager.",
            ),
            self._check(
                "safety.controller_idle",
                controller_idle,
                True,
                controller_state or "unknown",
                "OFF/IDLE/STOPPED/SIMULATION",
                "Arrêter le contrôleur avant certification.",
            ),
            self._check(
                "safety.simulation_driver_retained",
                simulation_retained,
                True,
                driver_name or "unknown",
                "SimulationDriver",
                "Conserver le driver de simulation.",
            ),
            self._check(
                "safety.bridge_disarmed",
                not bridge_armed,
                True,
                bridge_armed,
                False,
                "Désarmer immédiatement le bridge.",
            ),
        ]

        blockers = [
            check
            for check in checks
            if check["blocking"] and not check["passed"]
        ]
        warnings = [
            check
            for check in checks
            if not check["blocking"] and not check["passed"]
        ]

        score = round(
            sum(1 for check in checks if check["passed"])
            / len(checks)
            * 100
        )
        certified = not blockers and score >= self.minimum_score

        result = {
            "component": "hardware_certification",
            "patch_version": self.PATCH_VERSION,
            "generated_at": generated_at,
            "trigger": trigger,
            "level": (
                "READY_FOR_WATER_TEST"
                if certified
                else "HARDWARE_CERTIFICATION_INCOMPLETE"
            ),
            "certified": certified,
            "ready_for_water_test": certified,
            "score": score,
            "minimum_score": self.minimum_score,
            "passive_only": True,
            "mqtt_publish_allowed": False,
            "physical_commands_allowed": False,
            "driver_change_allowed": False,
            "automatic_bridge_arm_allowed": False,
            "hardware": {
                "wt32_topic_count": len(wt32_topics),
                "sensor_topic_count": len(sensor_topics),
                "relay_topic_count": len(relay_topics),
                "output_state_topic_count": len(output_state_topics),
                "command_topic_count": len(command_topics),
                "sensor_count": sensor_count,
                "certified_sensor_count": certified_sensor_count,
                "heartbeat_count": heartbeat_count,
                "mqtt_connected": mqtt_connected,
                "device_ready": device_ready,
                "device_connected": device_connected,
            },
            "safety": {
                "bridge_armed": bridge_armed,
                "driver": driver_name or "unknown",
                "simulation_driver_retained": simulation_retained,
                "controller_state": controller_state or "unknown",
                "controller_idle": controller_idle,
            },
            "certification_chain": {
                "sensor_discovery": discovery.get("level"),
                "sensor_validation": validation.get("level"),
                "mqtt_preflight": preflight.get("level"),
            },
            "contracts": {
                "wt32_topics": wt32_topics[:100],
                "sensor_topics": sensor_topics[:100],
                "relay_topics": relay_topics[:100],
                "output_state_topics": output_state_topics[:100],
                "command_topics": command_topics[:100],
            },
            "checks": checks,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": list(
                dict.fromkeys(
                    check["remediation"]
                    for check in blockers + warnings
                )
            ),
        }

        with self._lock:
            self._latest = deepcopy(result)
            self._history.append(deepcopy(result))
            self._metrics["evaluation_count"] += 1
            self._metrics[
                "certified_count" if certified else "blocked_count"
            ] += 1
            self._metrics["last_evaluated_at"] = generated_at
            self._metrics["last_level"] = result["level"]
            self._metrics["last_score"] = score

        self._publish(
            "hardware.certification"
            if certified
            else "hardware.certification.blocked",
            result,
            "INFO" if certified else "WARN",
        )
        return deepcopy(result)

    def status(self) -> dict[str, Any]:
        with self._lock:
            latest = deepcopy(self._latest)
            metrics = deepcopy(self._metrics)
            history_count = len(self._history)

        return {
            "component": "hardware_certification",
            "patch_version": self.PATCH_VERSION,
            "running": True,
            "started_at": self._started_at,
            "passive_only": True,
            "mqtt_publish_allowed": False,
            "physical_commands_allowed": False,
            "driver_change_allowed": False,
            "automatic_bridge_arm_allowed": False,
            "latest_level": latest.get("level") if latest else None,
            "latest_score": latest.get("score") if latest else None,
            "history_count": history_count,
            "metrics": metrics,
        }

    def latest(self) -> dict[str, Any]:
        with self._lock:
            latest = deepcopy(self._latest)
        return {
            "component": "hardware_certification",
            "available": latest is not None,
            "evaluation": latest,
        }

    def history(self, *, limit: int = 100) -> dict[str, Any]:
        limit = max(1, min(int(limit), self.history_capacity))
        with self._lock:
            items = list(self._history)[-limit:]
        return {
            "component": "hardware_certification",
            "count": len(items),
            "limit": limit,
            "evaluations": deepcopy(items),
        }

    def certificate(self) -> dict[str, Any]:
        with self._lock:
            latest = deepcopy(self._latest)
        if not latest:
            return {
                "component": "hardware_certification",
                "available": False,
                "certificate": None,
            }
        return {
            "component": "hardware_certification",
            "available": True,
            "certificate": {
                "patch_version": latest["patch_version"],
                "generated_at": latest["generated_at"],
                "level": latest["level"],
                "certified": latest["certified"],
                "ready_for_water_test":
                    latest["ready_for_water_test"],
                "score": latest["score"],
                "hardware": latest["hardware"],
                "safety": latest["safety"],
                "blocker_count": len(latest["blockers"]),
                "warning_count": len(latest["warnings"]),
            },
        }
