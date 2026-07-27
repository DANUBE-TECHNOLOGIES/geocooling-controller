from __future__ import annotations

import copy
import threading
from typing import Any

from app.devices.models import DeviceState


class DeviceRegistry:
    """Registre en mémoire thread-safe des équipements connus."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._devices: dict[str, DeviceState] = {}

    def replace(self, devices: list[DeviceState]) -> None:
        with self._lock:
            self._devices = {device.device_id: device for device in devices}

    def upsert(self, device: DeviceState) -> None:
        with self._lock:
            self._devices[device.device_id] = device

    def get(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            device = self._devices.get(device_id)
            return copy.deepcopy(device.to_dict()) if device else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                copy.deepcopy(device.to_dict())
                for device in sorted(
                    self._devices.values(),
                    key=lambda item: (item.subsystem, item.name, item.device_id),
                )
            ]

    def summary(self) -> dict[str, Any]:
        devices = self.list()
        online = sum(1 for device in devices if device["online"])
        ready = sum(1 for device in devices if device["ready"])
        degraded = sum(1 for device in devices if device["status"] == "degraded")
        offline = sum(1 for device in devices if device["status"] == "offline")
        return {
            "device_count": len(devices),
            "online_count": online,
            "ready_count": ready,
            "degraded_count": degraded,
            "offline_count": offline,
        }
