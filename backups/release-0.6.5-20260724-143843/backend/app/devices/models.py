from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ComponentState:
    component_id: str
    component_type: str
    name: str
    state: str = "unknown"
    available: bool = False
    health_score: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DeviceState:
    device_id: str
    name: str
    device_type: str
    subsystem: str
    transport: str = "mqtt"
    online: bool = False
    ready: bool = False
    health_score: int = 0
    status: str = "unknown"
    reason: str = "Aucune donnée reçue"
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    last_heartbeat_at: str | None = None
    heartbeat_age_seconds: int | None = None
    heartbeat_timeout_seconds: int = 90
    firmware_version: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    rssi: float | None = None
    uptime_seconds: int | None = None
    source_topic: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    components: list[ComponentState] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: utc_now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
