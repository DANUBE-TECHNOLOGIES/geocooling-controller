from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, text

from app.devices.models import ComponentState, DeviceState


class DevicePersistence:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                device_type TEXT NOT NULL,
                subsystem TEXT NOT NULL,
                transport TEXT NOT NULL DEFAULT 'mqtt',
                online BOOLEAN NOT NULL DEFAULT FALSE,
                ready BOOLEAN NOT NULL DEFAULT FALSE,
                health_score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'unknown',
                reason TEXT,
                first_seen_at TIMESTAMPTZ,
                last_seen_at TIMESTAMPTZ,
                last_heartbeat_at TIMESTAMPTZ,
                heartbeat_timeout_seconds INTEGER NOT NULL DEFAULT 90,
                firmware_version TEXT,
                ip_address TEXT,
                mac_address TEXT,
                rssi DOUBLE PRECISION,
                uptime_seconds BIGINT,
                source_topic TEXT,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_devices_subsystem
            ON devices (subsystem, status)
            """,
            """
            CREATE TABLE IF NOT EXISTS device_components (
                device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
                component_id TEXT NOT NULL,
                component_type TEXT NOT NULL,
                name TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'unknown',
                available BOOLEAN NOT NULL DEFAULT FALSE,
                health_score INTEGER NOT NULL DEFAULT 0,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (device_id, component_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS device_events (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                device_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                details JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_device_events_lookup
            ON device_events (device_id, created_at DESC)
            """,
        ]
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def load(self) -> list[DeviceState]:
        with self.engine.connect() as connection:
            device_rows = connection.execute(
                text("SELECT * FROM devices ORDER BY subsystem, name")
            ).mappings().all()
            component_rows = connection.execute(
                text("SELECT * FROM device_components ORDER BY device_id, component_id")
            ).mappings().all()

        components_by_device: dict[str, list[ComponentState]] = {}
        for row in component_rows:
            components_by_device.setdefault(row["device_id"], []).append(
                ComponentState(
                    component_id=row["component_id"],
                    component_type=row["component_type"],
                    name=row["name"],
                    state=row["state"],
                    available=bool(row["available"]),
                    health_score=int(row["health_score"]),
                    metadata=dict(row["metadata"] or {}),
                    updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                )
            )

        result: list[DeviceState] = []
        for row in device_rows:
            result.append(
                DeviceState(
                    device_id=row["device_id"],
                    name=row["name"],
                    device_type=row["device_type"],
                    subsystem=row["subsystem"],
                    transport=row["transport"],
                    online=bool(row["online"]),
                    ready=bool(row["ready"]),
                    health_score=int(row["health_score"]),
                    status=row["status"],
                    reason=row["reason"] or "",
                    first_seen_at=row["first_seen_at"].isoformat() if row["first_seen_at"] else None,
                    last_seen_at=row["last_seen_at"].isoformat() if row["last_seen_at"] else None,
                    last_heartbeat_at=row["last_heartbeat_at"].isoformat() if row["last_heartbeat_at"] else None,
                    heartbeat_timeout_seconds=int(row["heartbeat_timeout_seconds"]),
                    firmware_version=row["firmware_version"],
                    ip_address=row["ip_address"],
                    mac_address=row["mac_address"],
                    rssi=float(row["rssi"]) if row["rssi"] is not None else None,
                    uptime_seconds=int(row["uptime_seconds"]) if row["uptime_seconds"] is not None else None,
                    source_topic=row["source_topic"],
                    payload=dict(row["payload"] or {}),
                    components=components_by_device.get(row["device_id"], []),
                    updated_at=row["updated_at"].isoformat(),
                )
            )
        return result

    def save(self, device: DeviceState) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO devices (
                        device_id, name, device_type, subsystem, transport,
                        online, ready, health_score, status, reason,
                        first_seen_at, last_seen_at, last_heartbeat_at,
                        heartbeat_timeout_seconds, firmware_version,
                        ip_address, mac_address, rssi, uptime_seconds,
                        source_topic, payload, updated_at
                    ) VALUES (
                        :device_id, :name, :device_type, :subsystem, :transport,
                        :online, :ready, :health_score, :status, :reason,
                        CAST(:first_seen_at AS TIMESTAMPTZ), CAST(:last_seen_at AS TIMESTAMPTZ),
                        CAST(:last_heartbeat_at AS TIMESTAMPTZ), :heartbeat_timeout_seconds,
                        :firmware_version, :ip_address, :mac_address, :rssi,
                        :uptime_seconds, :source_topic, CAST(:payload AS JSONB), NOW()
                    )
                    ON CONFLICT (device_id) DO UPDATE SET
                        name=EXCLUDED.name,
                        device_type=EXCLUDED.device_type,
                        subsystem=EXCLUDED.subsystem,
                        transport=EXCLUDED.transport,
                        online=EXCLUDED.online,
                        ready=EXCLUDED.ready,
                        health_score=EXCLUDED.health_score,
                        status=EXCLUDED.status,
                        reason=EXCLUDED.reason,
                        first_seen_at=COALESCE(devices.first_seen_at, EXCLUDED.first_seen_at),
                        last_seen_at=EXCLUDED.last_seen_at,
                        last_heartbeat_at=EXCLUDED.last_heartbeat_at,
                        heartbeat_timeout_seconds=EXCLUDED.heartbeat_timeout_seconds,
                        firmware_version=EXCLUDED.firmware_version,
                        ip_address=EXCLUDED.ip_address,
                        mac_address=EXCLUDED.mac_address,
                        rssi=EXCLUDED.rssi,
                        uptime_seconds=EXCLUDED.uptime_seconds,
                        source_topic=EXCLUDED.source_topic,
                        payload=EXCLUDED.payload,
                        updated_at=NOW()
                    """
                ),
                {
                    **device.to_dict(),
                    "payload": json.dumps(device.payload),
                },
            )
            connection.execute(
                text("DELETE FROM device_components WHERE device_id = :device_id"),
                {"device_id": device.device_id},
            )
            for component in device.components:
                connection.execute(
                    text(
                        """
                        INSERT INTO device_components (
                            device_id, component_id, component_type, name,
                            state, available, health_score, metadata, updated_at
                        ) VALUES (
                            :device_id, :component_id, :component_type, :name,
                            :state, :available, :health_score,
                            CAST(:metadata AS JSONB), NOW()
                        )
                        """
                    ),
                    {
                        "device_id": device.device_id,
                        "component_id": component.component_id,
                        "component_type": component.component_type,
                        "name": component.name,
                        "state": component.state,
                        "available": component.available,
                        "health_score": component.health_score,
                        "metadata": json.dumps(component.metadata),
                    },
                )

    def add_event(self, device_id: str, event_type: str, severity: str, details: dict[str, Any]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO device_events (device_id, event_type, severity, details)
                    VALUES (:device_id, :event_type, :severity, CAST(:details AS JSONB))
                    """
                ),
                {
                    "device_id": device_id,
                    "event_type": event_type,
                    "severity": severity,
                    "details": json.dumps(details),
                },
            )

    def events(self, device_id: str | None, limit: int) -> list[dict[str, Any]]:
        query = """
            SELECT id, created_at, device_id, event_type, severity, details
            FROM device_events
        """
        params: dict[str, Any] = {"limit": limit}
        if device_id:
            query += " WHERE device_id = :device_id"
            params["device_id"] = device_id
        query += " ORDER BY created_at DESC LIMIT :limit"
        with self.engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"].isoformat(),
                "device_id": row["device_id"],
                "event_type": row["event_type"],
                "severity": row["severity"],
                "details": dict(row["details"] or {}),
            }
            for row in rows
        ]
