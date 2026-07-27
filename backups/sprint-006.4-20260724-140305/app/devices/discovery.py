from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, text


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_payload(payload_json: Any, payload_text: str | None) -> dict[str, Any]:
    if isinstance(payload_json, dict):
        return dict(payload_json)
    if payload_text:
        try:
            decoded = json.loads(payload_text)
            if isinstance(decoded, dict):
                return decoded
        except json.JSONDecodeError:
            pass
    return {}


def stable_device_id(topic: str, payload: dict[str, Any]) -> str:
    explicit = (
        payload.get("device_id")
        or payload.get("id")
        or payload.get("name")
        or payload.get("hostname")
    )
    if explicit:
        return str(explicit).strip().lower().replace(" ", "-")
    base = topic.split("/status/")[0].strip("/") or topic
    digest = hashlib.sha1(base.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"mqtt-{digest}"


class DeviceDiscovery:
    """Découverte à partir de l'historien MQTT déjà alimenté par le collecteur."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def latest_geocooling_messages(self) -> dict[str, dict[str, Any]]:
        topics = (
            "geocooling/status/device",
            "geocooling/status/heartbeat",
            "geocooling/status/availability",
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (topic)
                        topic, payload_text, payload_json, received_at
                    FROM telemetry_raw
                    WHERE topic = ANY(:topics)
                    ORDER BY topic, received_at DESC
                    """
                ),
                {"topics": list(topics)},
            ).mappings().all()
        return {
            row["topic"]: {
                "payload": parse_payload(row["payload_json"], row["payload_text"]),
                "payload_text": row["payload_text"],
                "received_at": row["received_at"],
            }
            for row in rows
        }

    def discover_generic_status_devices(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (topic)
                        topic, payload_text, payload_json, received_at
                    FROM telemetry_raw
                    WHERE topic LIKE '%/status/device'
                       OR topic LIKE '%/device/status'
                    ORDER BY topic, received_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
        result = []
        for row in rows:
            payload = parse_payload(row["payload_json"], row["payload_text"])
            result.append(
                {
                    "device_id": stable_device_id(row["topic"], payload),
                    "topic": row["topic"],
                    "payload": payload,
                    "received_at": row["received_at"],
                }
            )
        return result
