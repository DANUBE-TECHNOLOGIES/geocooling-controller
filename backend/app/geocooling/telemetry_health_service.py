"""Read-only database adapter for GeoCooling telemetry health."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, text

from app.geocooling.telemetry_health import build_telemetry_health


LATEST_MEASUREMENTS_SQL = text(
    """
    SELECT DISTINCT ON (sensor_name, metric)
        sensor_name,
        metric,
        value,
        unit,
        measured_at,
        mqtt_topic
    FROM sensor_measurements
    ORDER BY sensor_name, metric, measured_at DESC
    """
)


class TelemetryHealthService:
    """Build telemetry-role health from the existing measurement store.

    This service is intentionally read-only: it performs one SELECT and delegates
    all classification to ``build_telemetry_health``. It never publishes MQTT,
    never writes the database and never commands GeoCooling hardware.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ["DATABASE_URL"]
        self.engine = create_engine(self.database_url, pool_pre_ping=True)

    def latest_rows(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(LATEST_MEASUREMENTS_SQL).mappings().all()
        return [dict(row) for row in rows]

    def health(self) -> dict[str, Any]:
        report = build_telemetry_health(self.latest_rows())
        return {
            **report,
            "read_only": True,
            "hardware_touched": False,
            "mqtt_publish": False,
            "database_write": False,
        }
