"""
C016.1R1 — Sensor & MQTT Discovery.

Découverte passive :
- connexion au broker MQTT ;
- écoute des topics sans publication ;
- découverte WT32 / ESPHome ;
- découverte DS18B20 ;
- analyse de fraîcheur ;
- identification des topics de relais ;
- certification de prévol MQTT.

Aucune commande MQTT n'est envoyée.
Aucun relais n'est actionné.
Le driver actif n'est jamais modifié.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None


class SensorMQTTDiscovery:
    PATCH_VERSION = "C016.1R1"

    TEMPERATURE_MIN_C = -20.0
    TEMPERATURE_MAX_C = 85.0

    DS18B20_ID_PATTERN = re.compile(
        r"(?<![0-9a-f])"
        r"(?:28[-:]?)?[0-9a-f]{12,16}"
        r"(?![0-9a-f])",
        re.IGNORECASE,
    )

    TEMPERATURE_WORDS = (
        "temperature",
        "temp",
        "ds18",
        "onewire",
        "one_wire",
        "one-wire",
        "water",
        "floor",
        "surface",
        "depart",
        "retour",
        "inlet",
        "outlet",
    )

    HEARTBEAT_WORDS = (
        "heartbeat",
        "availability",
        "status",
        "online",
        "uptime",
        "last_seen",
    )

    RELAY_WORDS = (
        "relay",
        "switch",
        "pump",
        "circulator",
        "circulateur",
        "valve",
        "electrovanne",
        "electro_valve",
    )

    def __init__(
        self,
        *,
        event_bus: Any = None,
        controller: Any = None,
        expected_sensor_count: int = 4,
        history_capacity: int = 1000,
    ) -> None:
        self.event_bus = event_bus
        self.controller = controller

        self.expected_sensor_count = max(
            1,
            int(
                os.getenv(
                    "GEOCOOLING_EXPECTED_DS18B20_COUNT",
                    expected_sensor_count,
                )
            ),
        )

        self.host = os.getenv(
            "GEOCOOLING_MQTT_HOST",
            os.getenv("MQTT_HOST", "mosquitto"),
        )

        self.port = int(
            os.getenv(
                "GEOCOOLING_MQTT_PORT",
                os.getenv("MQTT_PORT", "1883"),
            )
        )

        self.username = os.getenv(
            "GEOCOOLING_MQTT_USERNAME",
            os.getenv("MQTT_USERNAME"),
        )

        self.password = os.getenv(
            "GEOCOOLING_MQTT_PASSWORD",
            os.getenv("MQTT_PASSWORD"),
        )

        self.topic_filter = os.getenv(
            "GEOCOOLING_MQTT_DISCOVERY_TOPIC",
            "#",
        )

        self.client_id = os.getenv(
            "GEOCOOLING_MQTT_DISCOVERY_CLIENT_ID",
            "geocooling-sensor-discovery",
        )

        self.message_stale_seconds = int(
            os.getenv(
                "GEOCOOLING_SENSOR_STALE_SECONDS",
                "120",
            )
        )

        self.history_capacity = max(
            100,
            int(history_capacity),
        )

        self._lock = threading.RLock()

        self._client: Any = None
        self._thread_started = False
        self._stopping = False

        self._connected = False
        self._connection_error: str | None = None
        self._connected_at: str | None = None
        self._disconnected_at: str | None = None

        self._started_at = self._utc_now()
        self._last_message_at: str | None = None
        self._last_message_monotonic: float | None = None

        self._message_count = 0
        self._parse_error_count = 0
        self._publish_attempt_count = 0

        self._topics: dict[str, dict[str, Any]] = {}
        self._sensors: dict[str, dict[str, Any]] = {}
        self._relay_topics: dict[str, dict[str, Any]] = {}
        self._heartbeat_topics: dict[str, dict[str, Any]] = {}

        self._events: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )

        self._evaluations: deque[dict[str, Any]] = deque(
            maxlen=500
        )

        self._latest_evaluation: dict[str, Any] | None = None

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if math.isnan(number) or math.isinf(number):
            return None

        return number

    @staticmethod
    def _decode_payload(payload: bytes) -> str:
        return payload.decode(
            "utf-8",
            errors="replace",
        ).strip()

    @classmethod
    def _extract_json(cls, text: str) -> Any:
        if not text:
            return None

        try:
            return json.loads(text)
        except Exception:
            return None

    @classmethod
    def _flatten(
        cls,
        value: Any,
        prefix: str = "",
    ) -> list[tuple[str, Any]]:
        result: list[tuple[str, Any]] = []

        if isinstance(value, dict):
            for key, item in value.items():
                child = (
                    f"{prefix}.{key}"
                    if prefix
                    else str(key)
                )

                result.extend(
                    cls._flatten(
                        item,
                        child,
                    )
                )

        elif isinstance(value, list):
            for index, item in enumerate(value):
                child = (
                    f"{prefix}[{index}]"
                    if prefix
                    else f"[{index}]"
                )

                result.extend(
                    cls._flatten(
                        item,
                        child,
                    )
                )

        else:
            result.append(
                (
                    prefix,
                    value,
                )
            )

        return result

    @classmethod
    def _sensor_identity(
        cls,
        topic: str,
        field: str,
    ) -> str:
        combined = f"{topic}/{field}"

        match = cls.DS18B20_ID_PATTERN.search(
            combined
        )

        if match:
            normalized = re.sub(
                r"[^0-9a-f]",
                "",
                match.group(0).lower(),
            )

            if (
                len(normalized) == 14
                and not normalized.startswith("28")
            ):
                normalized = f"28{normalized}"

            return normalized

        cleaned = re.sub(
            r"[^a-z0-9]+",
            "_",
            combined.lower(),
        ).strip("_")

        return cleaned[-160:]

    @classmethod
    def _looks_temperature(
        cls,
        topic: str,
        field: str,
        value: Any,
    ) -> bool:
        number = cls._safe_float(value)

        if number is None:
            return False

        combined = f"{topic} {field}".lower()

        if not any(
            word in combined
            for word in cls.TEMPERATURE_WORDS
        ):
            return False

        return (
            cls.TEMPERATURE_MIN_C
            <= number
            <= cls.TEMPERATURE_MAX_C
        )

    @staticmethod
    def _age_seconds(
        monotonic_timestamp: float | None,
    ) -> float | None:
        if monotonic_timestamp is None:
            return None

        return max(
            0.0,
            time.monotonic()
            - monotonic_timestamp,
        )

    def _publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        level: str = "INFO",
    ) -> None:
        if self.event_bus is None:
            return

        try:
            self.event_bus.publish(
                event_type=event_type,
                source="sensor-mqtt-discovery",
                payload=deepcopy(payload),
                level=level,
            )
        except Exception as exc:
            with self._lock:
                self._events.append(
                    {
                        "generated_at": self._utc_now(),
                        "event": "event_publish_failed",
                        "error": repr(exc),
                    }
                )

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread_started:
                return self.status()

            self._thread_started = True
            self._stopping = False

        if mqtt is None:
            with self._lock:
                self._connection_error = (
                    "Bibliothèque paho-mqtt indisponible"
                )

            return self.status()

        try:
            try:
                client = mqtt.Client(
                    callback_api_version=(
                        mqtt.CallbackAPIVersion.VERSION2
                    ),
                    client_id=self.client_id,
                    clean_session=True,
                )
            except (TypeError, AttributeError):
                client = mqtt.Client(
                    client_id=self.client_id,
                    clean_session=True,
                )

            if self.username:
                client.username_pw_set(
                    self.username,
                    self.password,
                )

            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message

            self._client = client

            client.connect_async(
                self.host,
                self.port,
                keepalive=30,
            )

            client.loop_start()

        except Exception as exc:
            with self._lock:
                self._connection_error = repr(exc)

        return self.status()

    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            client = self._client

        if client is None:
            return

        try:
            client.disconnect()
        except Exception:
            pass

        try:
            client.loop_stop()
        except Exception:
            pass

    def _on_connect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        try:
            code = int(reason_code)
        except Exception:
            code = 0 if str(reason_code).lower() in {
                "success",
                "0",
            } else -1

        if code != 0:
            with self._lock:
                self._connected = False
                self._connection_error = (
                    f"Connexion MQTT refusée : {reason_code}"
                )
            return

        client.subscribe(
            self.topic_filter,
            qos=0,
        )

        generated_at = self._utc_now()

        with self._lock:
            self._connected = True
            self._connected_at = generated_at
            self._connection_error = None

            self._events.append(
                {
                    "generated_at": generated_at,
                    "event": "mqtt_connected",
                    "host": self.host,
                    "port": self.port,
                    "topic_filter": self.topic_filter,
                }
            )

        self._publish_event(
            "sensor.discovery",
            {
                "event": "mqtt_connected",
                "host": self.host,
                "port": self.port,
                "topic_filter": self.topic_filter,
            },
        )

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags: Any = None,
        reason_code: Any = None,
        properties: Any = None,
    ) -> None:
        generated_at = self._utc_now()

        with self._lock:
            self._connected = False
            self._disconnected_at = generated_at

            if not self._stopping:
                self._connection_error = (
                    f"Déconnexion MQTT : {reason_code}"
                )

            self._events.append(
                {
                    "generated_at": generated_at,
                    "event": "mqtt_disconnected",
                    "reason": str(reason_code),
                }
            )

    def _on_message(
        self,
        client: Any,
        userdata: Any,
        message: Any,
    ) -> None:
        topic = str(message.topic)
        payload_text = self._decode_payload(
            message.payload
        )

        generated_at = self._utc_now()
        observed_monotonic = time.monotonic()

        parsed = self._extract_json(
            payload_text
        )

        with self._lock:
            self._message_count += 1
            self._last_message_at = generated_at
            self._last_message_monotonic = (
                observed_monotonic
            )

            self._topics[topic] = {
                "topic": topic,
                "payload": payload_text[:1000],
                "retained": bool(
                    getattr(
                        message,
                        "retain",
                        False,
                    )
                ),
                "qos": int(
                    getattr(
                        message,
                        "qos",
                        0,
                    )
                ),
                "last_seen_at": generated_at,
                "last_seen_monotonic": (
                    observed_monotonic
                ),
                "message_count": (
                    self._topics.get(
                        topic,
                        {},
                    ).get(
                        "message_count",
                        0,
                    )
                    + 1
                ),
            }

        self._inspect_topic(
            topic=topic,
            payload_text=payload_text,
            parsed=parsed,
            generated_at=generated_at,
            observed_monotonic=(
                observed_monotonic
            ),
        )

    def _inspect_topic(
        self,
        *,
        topic: str,
        payload_text: str,
        parsed: Any,
        generated_at: str,
        observed_monotonic: float,
    ) -> None:
        topic_lower = topic.lower()

        if any(
            word in topic_lower
            for word in self.HEARTBEAT_WORDS
        ):
            with self._lock:
                self._heartbeat_topics[topic] = {
                    "topic": topic,
                    "payload": payload_text[:500],
                    "last_seen_at": generated_at,
                    "last_seen_monotonic": (
                        observed_monotonic
                    ),
                }

        if any(
            word in topic_lower
            for word in self.RELAY_WORDS
        ):
            with self._lock:
                self._relay_topics[topic] = {
                    "topic": topic,
                    "payload": payload_text[:500],
                    "last_seen_at": generated_at,
                    "last_seen_monotonic": (
                        observed_monotonic
                    ),
                }

        candidates: list[tuple[str, Any]]

        if parsed is not None:
            candidates = self._flatten(parsed)
        else:
            candidates = [
                (
                    "",
                    payload_text,
                )
            ]

        discovered: list[dict[str, Any]] = []

        for field, value in candidates:
            if not self._looks_temperature(
                topic,
                field,
                value,
            ):
                continue

            temperature = self._safe_float(value)

            if temperature is None:
                continue

            sensor_id = self._sensor_identity(
                topic,
                field,
            )

            explicit_ds18b20 = bool(
                self.DS18B20_ID_PATTERN.search(
                    f"{topic}/{field}"
                )
            ) or "ds18" in f"{topic}/{field}".lower()

            sensor = {
                "sensor_id": sensor_id,
                "technology": (
                    "DS18B20"
                    if explicit_ds18b20
                    else "temperature_sensor"
                ),
                "topic": topic,
                "field": field or None,
                "temperature_c": temperature,
                "valid_range": True,
                "last_seen_at": generated_at,
                "last_seen_monotonic": (
                    observed_monotonic
                ),
            }

            with self._lock:
                previous = self._sensors.get(
                    sensor_id,
                    {}
                )

                sensor["message_count"] = (
                    previous.get(
                        "message_count",
                        0,
                    )
                    + 1
                )

                sensor["first_seen_at"] = (
                    previous.get(
                        "first_seen_at",
                        generated_at,
                    )
                )

                sensor["previous_temperature_c"] = (
                    previous.get(
                        "temperature_c"
                    )
                )

                self._sensors[sensor_id] = sensor

            discovered.append(
                deepcopy(sensor)
            )

        if discovered:
            self._publish_event(
                "sensor.discovery",
                {
                    "event": "temperature_observed",
                    "topic": topic,
                    "sensors": discovered,
                },
            )

    def _decorate_age(
        self,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        result = deepcopy(item)

        age = self._age_seconds(
            result.pop(
                "last_seen_monotonic",
                None,
            )
        )

        result["age_seconds"] = (
            round(age, 3)
            if age is not None
            else None
        )

        result["fresh"] = (
            age is not None
            and age <= self.message_stale_seconds
        )

        return result

    def evaluate(
        self,
        *,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        generated_at = self._utc_now()

        with self._lock:
            connected = self._connected
            connection_error = self._connection_error

            topics = [
                self._decorate_age(item)
                for item in self._topics.values()
            ]

            sensors = [
                self._decorate_age(item)
                for item in self._sensors.values()
            ]

            relay_topics = [
                self._decorate_age(item)
                for item in self._relay_topics.values()
            ]

            heartbeat_topics = [
                self._decorate_age(item)
                for item in self._heartbeat_topics.values()
            ]

            message_count = self._message_count
            last_message_at = self._last_message_at
            last_message_monotonic = (
                self._last_message_monotonic
            )

        fresh_sensors = [
            sensor
            for sensor in sensors
            if sensor["fresh"]
        ]

        explicit_ds18b20 = [
            sensor
            for sensor in fresh_sensors
            if sensor["technology"] == "DS18B20"
        ]

        fresh_heartbeat_topics = [
            item
            for item in heartbeat_topics
            if item["fresh"]
        ]

        fresh_relay_topics = [
            item
            for item in relay_topics
            if item["fresh"]
        ]

        last_message_age = self._age_seconds(
            last_message_monotonic
        )

        checks = [
            {
                "id": "mqtt.library_available",
                "passed": mqtt is not None,
                "observed": mqtt is not None,
                "expected": True,
                "blocking": True,
                "remediation": (
                    "Installer paho-mqtt dans le backend."
                ),
            },
            {
                "id": "mqtt.connected",
                "passed": connected,
                "observed": connected,
                "expected": True,
                "blocking": True,
                "remediation": (
                    "Vérifier le broker, son adresse, "
                    "le port et les identifiants."
                ),
            },
            {
                "id": "mqtt.messages_received",
                "passed": message_count > 0,
                "observed": message_count,
                "expected": "> 0",
                "blocking": True,
                "remediation": (
                    "Vérifier les publications MQTT "
                    "du WT32 et le filtre de topics."
                ),
            },
            {
                "id": "mqtt.message_fresh",
                "passed": (
                    last_message_age is not None
                    and last_message_age
                    <= self.message_stale_seconds
                ),
                "observed": (
                    round(last_message_age, 3)
                    if last_message_age is not None
                    else None
                ),
                "expected": (
                    f"<= {self.message_stale_seconds} s"
                ),
                "blocking": True,
                "remediation": (
                    "Rétablir les publications périodiques "
                    "du WT32."
                ),
            },
            {
                "id": "sensors.expected_count",
                "passed": (
                    len(fresh_sensors)
                    >= self.expected_sensor_count
                ),
                "observed": len(fresh_sensors),
                "expected": (
                    f">= {self.expected_sensor_count}"
                ),
                "blocking": True,
                "remediation": (
                    "Vérifier le bus OneWire, la résistance "
                    "de tirage et les quatre DS18B20."
                ),
            },
            {
                "id": "sensors.ds18b20_identified",
                "passed": (
                    len(explicit_ds18b20)
                    >= self.expected_sensor_count
                ),
                "observed": len(explicit_ds18b20),
                "expected": (
                    f">= {self.expected_sensor_count}"
                ),
                "blocking": False,
                "remediation": (
                    "Publier les identifiants ROM DS18B20 "
                    "dans les noms de topics ou le JSON."
                ),
            },
            {
                "id": "heartbeat.detected",
                "passed": bool(
                    fresh_heartbeat_topics
                ),
                "observed": len(
                    fresh_heartbeat_topics
                ),
                "expected": ">= 1",
                "blocking": True,
                "remediation": (
                    "Publier un heartbeat ou un topic "
                    "availability depuis le WT32."
                ),
            },
            {
                "id": "relay_topics.detected",
                "passed": bool(
                    fresh_relay_topics
                ),
                "observed": len(
                    fresh_relay_topics
                ),
                "expected": ">= 1",
                "blocking": False,
                "remediation": (
                    "Exposer les états des relais sans "
                    "encore autoriser leurs commandes."
                ),
            },
        ]

        blockers = [
            check
            for check in checks
            if check["blocking"]
            and not check["passed"]
        ]

        warnings = [
            check
            for check in checks
            if not check["blocking"]
            and not check["passed"]
        ]

        passed_count = sum(
            1
            for check in checks
            if check["passed"]
        )

        score = round(
            passed_count
            / len(checks)
            * 100
        )

        ready = not blockers

        result = {
            "component": "sensor_mqtt_discovery",
            "patch_version": self.PATCH_VERSION,
            "generated_at": generated_at,
            "trigger": trigger,
            "ready_for_mqtt_driver": ready,
            "level": (
                "READY_FOR_MQTT_DRIVER"
                if ready
                else "SENSOR_PREFLIGHT_INCOMPLETE"
            ),
            "score": score,
            "passive_only": True,
            "mqtt_publish_allowed": False,
            "physical_commands_allowed": False,
            "configuration": {
                "host": self.host,
                "port": self.port,
                "topic_filter": self.topic_filter,
                "client_id": self.client_id,
                "authentication_configured": bool(
                    self.username
                ),
                "expected_sensor_count": (
                    self.expected_sensor_count
                ),
                "message_stale_seconds": (
                    self.message_stale_seconds
                ),
            },
            "mqtt": {
                "library_available": mqtt is not None,
                "connected": connected,
                "connection_error": connection_error,
                "message_count": message_count,
                "topic_count": len(topics),
                "last_message_at": last_message_at,
                "last_message_age_seconds": (
                    round(last_message_age, 3)
                    if last_message_age is not None
                    else None
                ),
            },
            "discovery": {
                "sensor_count": len(sensors),
                "fresh_sensor_count": len(
                    fresh_sensors
                ),
                "explicit_ds18b20_count": len(
                    explicit_ds18b20
                ),
                "heartbeat_topic_count": len(
                    heartbeat_topics
                ),
                "fresh_heartbeat_topic_count": len(
                    fresh_heartbeat_topics
                ),
                "relay_topic_count": len(
                    relay_topics
                ),
                "fresh_relay_topic_count": len(
                    fresh_relay_topics
                ),
                "sensors": sorted(
                    sensors,
                    key=lambda item: item[
                        "sensor_id"
                    ],
                ),
                "heartbeat_topics": sorted(
                    heartbeat_topics,
                    key=lambda item: item["topic"],
                ),
                "relay_topics": sorted(
                    relay_topics,
                    key=lambda item: item["topic"],
                ),
                "topics": sorted(
                    topics,
                    key=lambda item: item["topic"],
                )[:500],
            },
            "checks": checks,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": [
                check["remediation"]
                for check in blockers + warnings
            ],
        }

        with self._lock:
            self._latest_evaluation = deepcopy(
                result
            )

            self._evaluations.append(
                deepcopy(result)
            )

        self._publish_event(
            (
                "sensor.discovery"
                if ready
                else "sensor.discovery.warning"
            ),
            result,
            (
                "INFO"
                if ready
                else "WARN"
            ),
        )

        return result

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "component": "sensor_mqtt_discovery",
                "patch_version": self.PATCH_VERSION,
                "running": self._thread_started,
                "passive_only": True,
                "mqtt_publish_allowed": False,
                "physical_commands_allowed": False,
                "started_at": self._started_at,
                "mqtt": {
                    "host": self.host,
                    "port": self.port,
                    "topic_filter": self.topic_filter,
                    "connected": self._connected,
                    "connection_error": (
                        self._connection_error
                    ),
                    "connected_at": self._connected_at,
                    "disconnected_at": (
                        self._disconnected_at
                    ),
                    "last_message_at": (
                        self._last_message_at
                    ),
                    "message_count": (
                        self._message_count
                    ),
                    "topic_count": len(
                        self._topics
                    ),
                },
                "discovery": {
                    "sensor_count": len(
                        self._sensors
                    ),
                    "heartbeat_topic_count": len(
                        self._heartbeat_topics
                    ),
                    "relay_topic_count": len(
                        self._relay_topics
                    ),
                },
                "latest_level": (
                    self._latest_evaluation.get(
                        "level"
                    )
                    if self._latest_evaluation
                    else None
                ),
                "latest_score": (
                    self._latest_evaluation.get(
                        "score"
                    )
                    if self._latest_evaluation
                    else None
                ),
            }

    def latest(self) -> dict[str, Any]:
        with self._lock:
            result = deepcopy(
                self._latest_evaluation
            )

        return {
            "component": "sensor_mqtt_discovery",
            "available": result is not None,
            "evaluation": result,
        }

    def sensors(self) -> dict[str, Any]:
        with self._lock:
            sensors = [
                self._decorate_age(item)
                for item in self._sensors.values()
            ]

        return {
            "component": "sensor_mqtt_discovery",
            "expected_count": self.expected_sensor_count,
            "count": len(sensors),
            "sensors": sorted(
                sensors,
                key=lambda item: item["sensor_id"],
            ),
        }

    def topics(
        self,
        *,
        limit: int = 500,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                2000,
            ),
        )

        with self._lock:
            topics = [
                self._decorate_age(item)
                for item in self._topics.values()
            ]

        topics = sorted(
            topics,
            key=lambda item: item["topic"],
        )[:limit]

        return {
            "component": "sensor_mqtt_discovery",
            "count": len(topics),
            "limit": limit,
            "topics": topics,
        }

    def history(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                500,
            ),
        )

        with self._lock:
            items = list(
                self._evaluations
            )[-limit:]

        return {
            "component": "sensor_mqtt_discovery",
            "count": len(items),
            "evaluations": deepcopy(items),
        }
