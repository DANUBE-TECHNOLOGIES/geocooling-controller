import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger("sbc.geocooling.mqtt")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    return utc_now().isoformat()


def parse_boolean_payload(payload: str) -> bool | None:
    normalized = payload.strip().lower()

    if normalized in {
        "1",
        "true",
        "on",
        "open",
        "opened",
        "running",
        "active",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "off",
        "close",
        "closed",
        "stopped",
        "inactive",
    }:
        return False

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if isinstance(decoded, bool):
        return decoded

    if isinstance(decoded, (int, float)):
        return bool(decoded)

    if isinstance(decoded, dict):
        for key in (
            "state",
            "value",
            "on",
            "running",
            "open",
        ):
            if key in decoded:
                value = decoded[key]

                if isinstance(value, bool):
                    return value

                if isinstance(value, (int, float)):
                    return bool(value)

                if isinstance(value, str):
                    return parse_boolean_payload(value)

    return None


class MQTTDriver:
    """
    Pilote MQTT pour l'ESP32 GeoCooling.

    Les topics sont configurables dans .env.

    Le serveur publie les commandes :
    - électrovanne ;
    - circulateur.

    Il écoute :
    - les retours d'état ;
    - le heartbeat ;
    - la disponibilité de l'ESP32.
    """

    def __init__(self) -> None:
        self.host = os.getenv(
            "MQTT_HOST",
            "host.docker.internal",
        )

        self.port = int(
            os.getenv(
                "MQTT_PORT",
                "1883",
            )
        )

        self.username = os.getenv(
            "MQTT_USERNAME",
            "",
        )

        self.password = os.getenv(
            "MQTT_PASSWORD",
            "",
        )

        self.client_id = os.getenv(
            "GEOCOOLING_MQTT_CLIENT_ID",
            "sbc-geocooling-controller",
        )

        self.valve_command_topic = os.getenv(
            "GEOCOOLING_VALVE_COMMAND_TOPIC",
            "geocooling/actuators/valve/set",
        )

        self.valve_state_topic = os.getenv(
            "GEOCOOLING_VALVE_STATE_TOPIC",
            "geocooling/actuators/valve/state",
        )

        self.pump_command_topic = os.getenv(
            "GEOCOOLING_PUMP_COMMAND_TOPIC",
            "geocooling/actuators/pump/set",
        )

        self.pump_state_topic = os.getenv(
            "GEOCOOLING_PUMP_STATE_TOPIC",
            "geocooling/actuators/pump/state",
        )

        self.availability_topic = os.getenv(
            "GEOCOOLING_AVAILABILITY_TOPIC",
            "geocooling/status/availability",
        )

        self.heartbeat_topic = os.getenv(
            "GEOCOOLING_HEARTBEAT_TOPIC",
            "geocooling/status/heartbeat",
        )

        self.device_status_topic = os.getenv(
            "GEOCOOLING_DEVICE_STATUS_TOPIC",
            "geocooling/status/device",
        )

        self.command_on_payload = os.getenv(
            "GEOCOOLING_COMMAND_ON_PAYLOAD",
            "ON",
        )

        self.command_off_payload = os.getenv(
            "GEOCOOLING_COMMAND_OFF_PAYLOAD",
            "OFF",
        )

        self.command_qos = int(
            os.getenv(
                "GEOCOOLING_COMMAND_QOS",
                "1",
            )
        )

        self.command_retain = (
            os.getenv(
                "GEOCOOLING_COMMAND_RETAIN",
                "false",
            ).lower()
            == "true"
        )

        self._lock = threading.RLock()

        self._connected = False
        self._valve_open = False
        self._pump_running = False
        self._device_online = False

        self._last_connected_at: str | None = None
        self._last_disconnected_at: str | None = None
        self._last_message_at: str | None = None
        self._last_heartbeat_at: str | None = None
        self._last_action_at: str | None = None
        self._last_error: str | None = None
        self._device_payload: dict[str, Any] | None = None

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=True,
        )

        if self.username:
            self.client.username_pw_set(
                self.username,
                self.password,
            )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.client.reconnect_delay_set(
            min_delay=1,
            max_delay=30,
        )

        self.client.connect_async(
            self.host,
            self.port,
            keepalive=30,
        )

        self.client.loop_start()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        if int(reason_code) != 0:
            with self._lock:
                self._connected = False
                self._last_error = (
                    f"Connexion MQTT refusée : {reason_code}"
                )

            logger.error(self._last_error)
            return

        subscriptions = [
            self.valve_state_topic,
            self.pump_state_topic,
            self.availability_topic,
            self.heartbeat_topic,
            self.device_status_topic,
        ]

        for topic in subscriptions:
            client.subscribe(
                topic,
                qos=1,
            )

            logger.info(
                "Abonnement GeoCooling MQTT : %s",
                topic,
            )

        with self._lock:
            self._connected = True
            self._last_connected_at = utc_iso()
            self._last_error = None

        logger.info(
            "Pilote GeoCooling MQTT connecté à %s:%s",
            self.host,
            self.port,
        )

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        with self._lock:
            self._connected = False
            self._device_online = False
            self._last_disconnected_at = utc_iso()

            if int(reason_code) != 0:
                self._last_error = (
                    f"Connexion MQTT perdue : {reason_code}"
                )

        logger.warning(
            "Pilote GeoCooling MQTT déconnecté : %s",
            reason_code,
        )

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        payload = message.payload.decode(
            "utf-8",
            errors="replace",
        )

        now = utc_iso()

        with self._lock:
            self._last_message_at = now

            if message.topic == self.valve_state_topic:
                parsed = parse_boolean_payload(payload)

                if parsed is not None:
                    self._valve_open = parsed

            elif message.topic == self.pump_state_topic:
                parsed = parse_boolean_payload(payload)

                if parsed is not None:
                    self._pump_running = parsed

            elif message.topic == self.availability_topic:
                normalized = payload.strip().lower()

                self._device_online = normalized in {
                    "online",
                    "available",
                    "true",
                    "1",
                    "on",
                }

            elif message.topic == self.heartbeat_topic:
                self._device_online = True
                self._last_heartbeat_at = now

            elif message.topic == self.device_status_topic:
                try:
                    decoded = json.loads(payload)
                except json.JSONDecodeError:
                    decoded = {
                        "raw": payload,
                    }

                if isinstance(decoded, dict):
                    self._device_payload = decoded

                self._device_online = True

    def _publish(
        self,
        topic: str,
        payload: str,
    ) -> None:
        with self._lock:
            if not self._connected:
                raise RuntimeError(
                    "Le pilote GeoCooling n'est pas connecté "
                    "au broker MQTT."
                )

        result = self.client.publish(
            topic,
            payload,
            qos=self.command_qos,
            retain=self.command_retain,
        )

        result.wait_for_publish(timeout=5)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"Échec de publication MQTT sur {topic}: "
                f"code={result.rc}"
            )

        with self._lock:
            self._last_action_at = utc_iso()

    def open_valve(self) -> None:
        self._publish(
            self.valve_command_topic,
            self.command_on_payload,
        )

    def close_valve(self) -> None:
        self._publish(
            self.valve_command_topic,
            self.command_off_payload,
        )

    def start_pump(self) -> None:
        with self._lock:
            if not self._valve_open:
                raise RuntimeError(
                    "Démarrage du circulateur refusé : "
                    "le retour d'état de l'électrovanne "
                    "n'indique pas qu'elle est ouverte."
                )

        self._publish(
            self.pump_command_topic,
            self.command_on_payload,
        )

    def stop_pump(self) -> None:
        self._publish(
            self.pump_command_topic,
            self.command_off_payload,
        )

    def force_safe_state(self) -> None:
        errors: list[str] = []

        try:
            self._publish(
                self.pump_command_topic,
                self.command_off_payload,
            )
        except Exception as exc:
            errors.append(
                f"circulateur: {exc}"
            )

        time.sleep(0.2)

        try:
            self._publish(
                self.valve_command_topic,
                self.command_off_payload,
            )
        except Exception as exc:
            errors.append(
                f"électrovanne: {exc}"
            )

        if errors:
            raise RuntimeError(
                "État sécurisé incomplet : "
                + " ; ".join(errors)
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "driver": "mqtt",
                "simulation": False,
                "connected": self._connected,
                "device_online": self._device_online,
                "valve_open": self._valve_open,
                "pump_running": self._pump_running,
                "last_connected_at": self._last_connected_at,
                "last_disconnected_at":
                    self._last_disconnected_at,
                "last_message_at": self._last_message_at,
                "last_heartbeat_at":
                    self._last_heartbeat_at,
                "last_action_at": self._last_action_at,
                "last_error": self._last_error,
                "device": self._device_payload,
                "topics": {
                    "valve_command":
                        self.valve_command_topic,
                    "valve_state":
                        self.valve_state_topic,
                    "pump_command":
                        self.pump_command_topic,
                    "pump_state":
                        self.pump_state_topic,
                    "availability":
                        self.availability_topic,
                    "heartbeat":
                        self.heartbeat_topic,
                    "device_status":
                        self.device_status_topic,
                },
            }

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
