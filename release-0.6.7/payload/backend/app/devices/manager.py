from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine

from app.devices.discovery import DeviceDiscovery
from app.devices.models import ComponentState, DeviceState
from app.devices.persistence import DevicePersistence
from app.devices.registry import DeviceRegistry

logger = logging.getLogger("sbc.devices")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"online", "on", "true", "1", "available", "ready"}:
            return True
        if normalized in {"offline", "off", "false", "0", "unavailable"}:
            return False
    return None


class DeviceManager:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.registry = DeviceRegistry()
        self.persistence = DevicePersistence(engine)
        self.discovery = DeviceDiscovery(engine)
        self.refresh_interval_seconds = max(2, int(os.getenv("DEVICE_REFRESH_INTERVAL_SECONDS", "5")))
        self.heartbeat_timeout_seconds = max(10, int(os.getenv("DEVICE_HEARTBEAT_TIMEOUT_SECONDS", "90")))
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.RLock()
        self._last_refresh_at: str | None = None
        self._last_error: str | None = None
        self._refresh_count = 0

    def start(self) -> None:
        self.persistence.initialize()
        self.registry.replace(self.persistence.load())
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._stop_event.clear()
            self._worker = threading.Thread(target=self._run, name="device-manager", daemon=True)
            self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.refresh()
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("Erreur Device Manager")
            self._stop_event.wait(self.refresh_interval_seconds)

    def refresh(self) -> dict[str, Any]:
        now = utc_now()
        previous = {item["device_id"]: item for item in self.registry.list()}
        discovered = self.discovery.discover_generic_status_devices()
        geo_messages = self.discovery.latest_geocooling_messages()

        seen_ids: set[str] = set()
        for item in discovered:
            device = self._build_generic_device(item, now)
            seen_ids.add(device.device_id)
            self._persist_with_transition(previous.get(device.device_id), device)

        geo_device = self._build_geocooling_device(geo_messages, now)
        seen_ids.add(geo_device.device_id)
        self._persist_with_transition(previous.get(geo_device.device_id), geo_device)

        for old_id, old in previous.items():
            if old_id in seen_ids:
                continue
            device = self._offline_from_previous(old, now)
            self.persistence.save(device)
            self.registry.upsert(device)

        self._last_refresh_at = now.isoformat()
        self._last_error = None
        self._refresh_count += 1
        return self.status()

    def _persist_with_transition(self, previous: dict[str, Any] | None, device: DeviceState) -> None:
        if previous and previous.get("status") != device.status:
            severity = "warning" if device.status in {"degraded", "offline"} else "info"
            self.persistence.add_event(
                device.device_id,
                "device.status_changed",
                severity,
                {"from": previous.get("status"), "to": device.status, "reason": device.reason},
            )
        elif not previous:
            self.persistence.add_event(
                device.device_id,
                "device.discovered",
                "info",
                {"name": device.name, "subsystem": device.subsystem},
            )
        self.persistence.save(device)
        self.registry.upsert(device)

    def _build_geocooling_device(self, messages: dict[str, dict[str, Any]], now: datetime) -> DeviceState:
        device_msg = messages.get("geocooling/status/device")
        heartbeat_msg = messages.get("geocooling/status/heartbeat")
        availability_msg = messages.get("geocooling/status/availability")
        payload = dict(device_msg["payload"]) if device_msg else {}

        last_seen_candidates = [
            item["received_at"] for item in (device_msg, heartbeat_msg, availability_msg) if item
        ]
        last_seen = max(last_seen_candidates) if last_seen_candidates else None
        heartbeat_at = heartbeat_msg["received_at"] if heartbeat_msg else None
        heartbeat_age = int((now - heartbeat_at).total_seconds()) if heartbeat_at else None
        heartbeat_fresh = heartbeat_age is not None and heartbeat_age <= self.heartbeat_timeout_seconds

        availability = None
        if availability_msg:
            availability = as_bool(availability_msg["payload_text"])
            if availability is None:
                availability = as_bool(availability_msg["payload"].get("state"))
        online = heartbeat_fresh and availability is not False

        components = self._components_from_payload(payload, online, now)
        required_ok = all(component.available for component in components if component.metadata.get("required", True))
        ready = online and required_ok
        health = 100 if ready else (60 if online else 0)
        status = "online" if ready else ("degraded" if online else "offline")
        if not heartbeat_at:
            reason = "Heartbeat jamais reçu"
        elif not heartbeat_fresh:
            reason = f"Heartbeat trop ancien ({heartbeat_age}s)"
        elif availability is False:
            reason = "ESP32 déclaré indisponible"
        elif not required_ok:
            reason = "Un ou plusieurs composants requis sont indisponibles"
        else:
            reason = "Équipement disponible"

        first_seen = last_seen
        existing = self.registry.get("geocooling-controller")
        if existing and existing.get("first_seen_at"):
            first_seen = datetime.fromisoformat(existing["first_seen_at"])

        return DeviceState(
            device_id="geocooling-controller",
            name=str(payload.get("name") or payload.get("hostname") or "ESP32 GeoCooling"),
            device_type=str(payload.get("device_type") or "esp32-controller"),
            subsystem="geocooling",
            online=online,
            ready=ready,
            health_score=health,
            status=status,
            reason=reason,
            first_seen_at=iso(first_seen),
            last_seen_at=iso(last_seen),
            last_heartbeat_at=iso(heartbeat_at),
            heartbeat_age_seconds=heartbeat_age,
            heartbeat_timeout_seconds=self.heartbeat_timeout_seconds,
            firmware_version=self._str(payload, "firmware_version", "firmware", "version"),
            ip_address=self._str(payload, "ip_address", "ip"),
            mac_address=self._str(payload, "mac_address", "mac"),
            rssi=self._float(payload.get("rssi")),
            uptime_seconds=self._int(payload.get("uptime_seconds") or payload.get("uptime")),
            source_topic="geocooling/status/device",
            payload=payload,
            components=components,
            updated_at=now.isoformat(),
        )

    def _build_generic_device(self, item: dict[str, Any], now: datetime) -> DeviceState:
        payload = item["payload"]
        received_at = item["received_at"]
        age = int((now - received_at).total_seconds())
        online = age <= self.heartbeat_timeout_seconds
        subsystem = item["topic"].split("/")[0] or "unknown"
        existing = self.registry.get(item["device_id"])
        first_seen_at = existing.get("first_seen_at") if existing else iso(received_at)
        components = self._components_from_payload(payload, online, now)
        return DeviceState(
            device_id=item["device_id"],
            name=str(payload.get("name") or payload.get("hostname") or item["device_id"]),
            device_type=str(payload.get("device_type") or "mqtt-device"),
            subsystem=str(payload.get("subsystem") or subsystem),
            online=online,
            ready=online,
            health_score=100 if online else 0,
            status="online" if online else "offline",
            reason="Message de statut récent" if online else f"Dernier statut trop ancien ({age}s)",
            first_seen_at=first_seen_at,
            last_seen_at=iso(received_at),
            last_heartbeat_at=iso(received_at),
            heartbeat_age_seconds=age,
            heartbeat_timeout_seconds=self.heartbeat_timeout_seconds,
            firmware_version=self._str(payload, "firmware_version", "firmware", "version"),
            ip_address=self._str(payload, "ip_address", "ip"),
            mac_address=self._str(payload, "mac_address", "mac"),
            rssi=self._float(payload.get("rssi")),
            uptime_seconds=self._int(payload.get("uptime_seconds") or payload.get("uptime")),
            source_topic=item["topic"],
            payload=payload,
            components=components,
            updated_at=now.isoformat(),
        )

    def _components_from_payload(self, payload: dict[str, Any], online: bool, now: datetime) -> list[ComponentState]:
        raw_components = payload.get("components") or payload.get("capabilities") or []
        components: list[ComponentState] = []
        if isinstance(raw_components, dict):
            raw_components = [dict(value, id=key) if isinstance(value, dict) else {"id": key, "state": value} for key, value in raw_components.items()]
        if isinstance(raw_components, list):
            for index, raw in enumerate(raw_components):
                if isinstance(raw, str):
                    raw = {"id": raw, "type": "unknown", "name": raw}
                if not isinstance(raw, dict):
                    continue
                component_id = str(raw.get("id") or raw.get("component_id") or f"component-{index + 1}")
                available = as_bool(raw.get("available"))
                if available is None:
                    available = online
                components.append(
                    ComponentState(
                        component_id=component_id,
                        component_type=str(raw.get("type") or raw.get("component_type") or "unknown"),
                        name=str(raw.get("name") or component_id),
                        state=str(raw.get("state") or "unknown"),
                        available=bool(available),
                        health_score=100 if available else 0,
                        metadata={key: value for key, value in raw.items() if key not in {"id", "component_id", "type", "component_type", "name", "state", "available"}},
                        updated_at=now.isoformat(),
                    )
                )
        if not components:
            components = [
                ComponentState("valve", "relay", "Électrovanne", "unknown", online, 100 if online else 0, {"required": True}, now.isoformat()),
                ComponentState("pump", "relay", "Circulateur", "unknown", online, 100 if online else 0, {"required": True}, now.isoformat()),
            ]
        return components

    def _offline_from_previous(self, old: dict[str, Any], now: datetime) -> DeviceState:
        components = [ComponentState(**component) for component in old.get("components", [])]
        for component in components:
            component.available = False
            component.health_score = 0
            component.updated_at = now.isoformat()
        return DeviceState(
            **{
                key: value
                for key, value in old.items()
                if key not in {"components", "online", "ready", "health_score", "status", "reason", "updated_at"}
            },
            online=False,
            ready=False,
            health_score=0,
            status="offline",
            reason="Équipement non redécouvert",
            components=components,
            updated_at=now.isoformat(),
        )

    @staticmethod
    def _str(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def list_devices(self) -> list[dict[str, Any]]:
        return self.registry.list()

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        return self.registry.get(device_id)

    def events(self, device_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.persistence.events(device_id, min(max(limit, 1), 500))

    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self._worker and self._worker.is_alive()),
            "last_refresh_at": self._last_refresh_at,
            "last_error": self._last_error,
            "refresh_count": self._refresh_count,
            "configuration": {
                "refresh_interval_seconds": self.refresh_interval_seconds,
                "heartbeat_timeout_seconds": self.heartbeat_timeout_seconds,
            },
            **self.registry.summary(),
        }
