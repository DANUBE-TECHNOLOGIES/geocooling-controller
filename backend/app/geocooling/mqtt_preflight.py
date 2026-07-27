# C016.1R3 — MQTT Preflight.
# Certification strictement passive avant activation du driver matériel.

from __future__ import annotations

import os
import statistics
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class MQTTPreflightCertification:
    PATCH_VERSION = "C016.1R3"

    COMMAND_HINTS = (
        "/command", "/cmd", "/set",
        "command/", "cmd/", "set/",
    )
    OUTPUT_HINTS = (
        "relay", "switch", "pump", "circulator",
        "circulateur", "valve", "electrovanne",
    )

    def __init__(
        self,
        *,
        sensor_discovery: Any,
        sensor_validation: Any,
        event_bus: Any = None,
        controller: Any = None,
        history_capacity: int = 500,
    ) -> None:
        self.sensor_discovery = sensor_discovery
        self.sensor_validation = sensor_validation
        self.event_bus = event_bus
        self.controller = controller

        self.expected_sensor_count = max(
            1,
            int(os.getenv(
                "GEOCOOLING_EXPECTED_DS18B20_COUNT", "4"
            )),
        )
        self.stale_seconds = max(
            10,
            int(os.getenv(
                "GEOCOOLING_SENSOR_STALE_SECONDS", "120"
            )),
        )
        self.minimum_topic_count = max(
            1,
            int(os.getenv(
                "GEOCOOLING_MQTT_MIN_TOPIC_COUNT", "5"
            )),
        )
        self.minimum_output_state_topics = max(
            0,
            int(os.getenv(
                "GEOCOOLING_MQTT_MIN_OUTPUT_STATE_TOPICS", "1"
            )),
        )
        self.require_command_contract = os.getenv(
            "GEOCOOLING_MQTT_REQUIRE_COMMAND_CONTRACT", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}

        self.history_capacity = max(50, int(history_capacity))
        self._lock = threading.RLock()
        self._history = deque(maxlen=self.history_capacity)
        self._latest = None
        self._started_at = self._utc_now()
        self._metrics = {
            "evaluation_count": 0,
            "ready_count": 0,
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
                str(k): MQTTPreflightCertification._safe(v)
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [
                MQTTPreflightCertification._safe(v)
                for v in value
            ]
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, (bool, int, float, str)):
            return enum_value
        return repr(value)

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
                source="mqtt-preflight",
                payload=self._safe(payload),
                level=level,
            )
            self._metrics["last_error"] = None
        except Exception as exc:
            self._metrics["last_error"] = repr(exc)

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
            result = method(**kwargs)
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            self._metrics["last_error"] = repr(exc)
            return {}

    def _classify_topics(
        self,
        topics: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        command_topics = []
        output_state_topics = []
        retained_topics = []
        qos_topics = []

        for item in topics:
            if not isinstance(item, dict):
                continue

            topic = str(item.get("topic") or "")
            lower = topic.lower()

            if any(hint in lower for hint in self.COMMAND_HINTS):
                command_topics.append(item)

            if (
                any(hint in lower for hint in self.OUTPUT_HINTS)
                and any(
                    state in lower
                    for state in (
                        "/state", "/status",
                        "state/", "status/",
                    )
                )
            ):
                output_state_topics.append(item)

            if bool(item.get("retained")):
                retained_topics.append(item)

            try:
                qos = int(item.get("qos", 0))
            except (TypeError, ValueError):
                qos = 0
            if qos > 0:
                qos_topics.append(item)

        return {
            "command_topics": command_topics,
            "output_state_topics": output_state_topics,
            "retained_topics": retained_topics,
            "qos_topics": qos_topics,
        }

    def evaluate(
        self,
        *,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        generated_at = self._utc_now()

        discovery = self._call(
            self.sensor_discovery,
            "evaluate",
            trigger="mqtt-preflight",
        )
        validation = self._call(
            self.sensor_validation,
            "evaluate",
            trigger="mqtt-preflight",
        )

        mqtt = discovery.get("mqtt", {})
        discovered = discovery.get("discovery", {})
        topics = discovered.get("topics", [])
        if not isinstance(topics, list):
            topics = []

        classified = self._classify_topics(topics)

        topic_ages = [
            float(item["age_seconds"])
            for item in topics
            if isinstance(item.get("age_seconds"), (int, float))
        ]
        median_topic_age = (
            round(statistics.median(topic_ages), 3)
            if topic_ages else None
        )

        connected = bool(mqtt.get("connected"))
        library_available = bool(
            mqtt.get("library_available", True)
        )
        message_count = int(mqtt.get("message_count", 0) or 0)
        topic_count = int(
            mqtt.get("topic_count", len(topics)) or 0
        )
        last_message_age = mqtt.get(
            "last_message_age_seconds"
        )
        message_fresh = (
            isinstance(last_message_age, (int, float))
            and last_message_age <= self.stale_seconds
        )

        fresh_sensor_count = int(
            discovered.get("fresh_sensor_count", 0) or 0
        )
        heartbeat_count = int(
            discovered.get(
                "fresh_heartbeat_topic_count", 0
            ) or 0
        )
        output_state_count = len(
            classified["output_state_topics"]
        )
        command_topic_count = len(
            classified["command_topics"]
        )

        validation_ready = bool(
            validation.get(
                "ready_for_mqtt_driver",
                validation.get("ready", False),
            )
        )
        validation_score = int(
            validation.get("score", 0) or 0
        )

        bridge_armed = False
        bridge = getattr(
            self.controller,
            "controller_command_bridge",
            None,
        )
        if bridge is not None:
            try:
                bridge_armed = bool(
                    bridge.status().get("armed")
                )
            except Exception as exc:
                self._metrics["last_error"] = repr(exc)

        controller_status = self._call(
            self.controller,
            "status",
        )
        driver_name = str(
            controller_status.get(
                "driver",
                controller_status.get("driver_name", ""),
            )
        )
        simulation_driver = (
            not driver_name
            or "simulation" in driver_name.lower()
        )

        checks = [
            self._check(
                "mqtt.library_available",
                library_available,
                True,
                library_available,
                "Installer ou restaurer paho-mqtt.",
            ),
            self._check(
                "mqtt.connected",
                connected,
                True,
                connected,
                "Vérifier broker, réseau, port et identifiants.",
            ),
            self._check(
                "mqtt.messages_received",
                message_count > 0,
                True,
                message_count,
                "Vérifier les publications MQTT du WT32.",
            ),
            self._check(
                "mqtt.message_fresh",
                message_fresh,
                True,
                last_message_age,
                "Rétablir heartbeat et publications périodiques.",
            ),
            self._check(
                "mqtt.minimum_topic_count",
                topic_count >= self.minimum_topic_count,
                True,
                topic_count,
                "Vérifier le préfixe MQTT et les entités ESPHome.",
            ),
            self._check(
                "mqtt.heartbeat_present",
                heartbeat_count >= 1,
                True,
                heartbeat_count,
                "Publier availability, online ou heartbeat.",
            ),
            self._check(
                "mqtt.sensor_topics_present",
                fresh_sensor_count >= self.expected_sensor_count,
                True,
                fresh_sensor_count,
                "Faire publier les quatre DS18B20.",
            ),
            self._check(
                "sensor_validation.certified",
                validation_ready,
                True,
                {
                    "level": validation.get("level"),
                    "score": validation_score,
                },
                "Terminer la validation C016.1R2.",
            ),
            self._check(
                "mqtt.output_state_contract",
                output_state_count
                >= self.minimum_output_state_topics,
                self.minimum_output_state_topics > 0,
                output_state_count,
                "Exposer les états des relais, pompe et vanne.",
            ),
            self._check(
                "mqtt.command_contract_detected",
                command_topic_count > 0,
                self.require_command_contract,
                command_topic_count,
                "Déclarer les topics de commande sans les utiliser.",
            ),
            self._check(
                "safety.bridge_disarmed",
                not bridge_armed,
                True,
                bridge_armed,
                "Désarmer immédiatement le bridge.",
            ),
            self._check(
                "safety.simulation_driver_retained",
                simulation_driver,
                True,
                driver_name or "unknown",
                "Conserver SimulationDriver avant certification.",
            ),
        ]

        blockers = [
            item for item in checks
            if item["blocking"] and not item["passed"]
        ]
        warnings = [
            item for item in checks
            if not item["blocking"] and not item["passed"]
        ]

        score = round(
            sum(1 for item in checks if item["passed"])
            / len(checks)
            * 100
        )
        ready = not blockers

        result = {
            "component": "mqtt_preflight",
            "patch_version": self.PATCH_VERSION,
            "generated_at": generated_at,
            "trigger": trigger,
            "level": (
                "READY_FOR_MQTT_DRIVER"
                if ready
                else "MQTT_PREFLIGHT_INCOMPLETE"
            ),
            "ready": ready,
            "ready_for_mqtt_driver": ready,
            "score": score,
            "passive_only": True,
            "mqtt_publish_allowed": False,
            "physical_commands_allowed": False,
            "driver_change_allowed": False,
            "automatic_bridge_arm_allowed": False,
            "mqtt": {
                "library_available": library_available,
                "connected": connected,
                "message_count": message_count,
                "topic_count": topic_count,
                "last_message_age_seconds": last_message_age,
                "median_topic_age_seconds": median_topic_age,
                "fresh_sensor_count": fresh_sensor_count,
                "fresh_heartbeat_topic_count":
                    heartbeat_count,
                "output_state_topic_count":
                    output_state_count,
                "command_contract_topic_count":
                    command_topic_count,
                "retained_topic_count": len(
                    classified["retained_topics"]
                ),
                "qos_gt_zero_topic_count": len(
                    classified["qos_topics"]
                ),
            },
            "contracts": {
                "output_state_topics":
                    classified["output_state_topics"][:100],
                "command_topics":
                    classified["command_topics"][:100],
            },
            "sensor_validation": {
                "level": validation.get("level"),
                "score": validation_score,
                "ready": validation_ready,
                "sensor_count":
                    validation.get("sensor_count"),
                "certified_sensor_count":
                    validation.get("certified_sensor_count"),
                "failed_sensor_count":
                    validation.get("failed_sensor_count"),
            },
            "safety": {
                "bridge_armed": bridge_armed,
                "driver": driver_name or "unknown",
                "simulation_driver_retained":
                    simulation_driver,
            },
            "checks": checks,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": list(dict.fromkeys(
                item["remediation"]
                for item in blockers + warnings
            )),
        }

        with self._lock:
            self._latest = deepcopy(result)
            self._history.append(deepcopy(result))
            self._metrics["evaluation_count"] += 1
            self._metrics[
                "ready_count" if ready else "blocked_count"
            ] += 1
            self._metrics["last_evaluated_at"] = generated_at
            self._metrics["last_level"] = result["level"]
            self._metrics["last_score"] = score

        self._publish(
            "mqtt.preflight"
            if ready
            else "mqtt.preflight.warning",
            result,
            "INFO" if ready else "WARN",
        )
        return deepcopy(result)

    @staticmethod
    def _check(
        check_id: str,
        passed: bool,
        blocking: bool,
        observed: Any,
        remediation: str,
    ) -> dict[str, Any]:
        return {
            "id": check_id,
            "passed": bool(passed),
            "blocking": bool(blocking),
            "observed": observed,
            "remediation": remediation,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            latest = deepcopy(self._latest)
            metrics = deepcopy(self._metrics)
            history_count = len(self._history)

        return {
            "component": "mqtt_preflight",
            "patch_version": self.PATCH_VERSION,
            "running": True,
            "started_at": self._started_at,
            "passive_only": True,
            "mqtt_publish_allowed": False,
            "physical_commands_allowed": False,
            "driver_change_allowed": False,
            "automatic_bridge_arm_allowed": False,
            "latest_level": (
                latest.get("level") if latest else None
            ),
            "latest_score": (
                latest.get("score") if latest else None
            ),
            "history_count": history_count,
            "metrics": metrics,
        }

    def latest(self) -> dict[str, Any]:
        with self._lock:
            latest = deepcopy(self._latest)
        return {
            "component": "mqtt_preflight",
            "available": latest is not None,
            "evaluation": latest,
        }

    def contracts(self) -> dict[str, Any]:
        with self._lock:
            latest = deepcopy(self._latest)
        return {
            "component": "mqtt_preflight",
            "available": latest is not None,
            "contracts": (
                latest.get("contracts", {})
                if latest else {}
            ),
        }

    def history(self, *, limit: int = 100) -> dict[str, Any]:
        limit = max(
            1,
            min(int(limit), self.history_capacity),
        )
        with self._lock:
            items = list(self._history)[-limit:]
        return {
            "component": "mqtt_preflight",
            "count": len(items),
            "limit": limit,
            "evaluations": deepcopy(items),
        }
