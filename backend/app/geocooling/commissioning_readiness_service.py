"""Read-only adapter for the GeoCooling commissioning readiness gate."""

from __future__ import annotations

import os
from typing import Any

from app.geocooling.commissioning_readiness import build_commissioning_readiness
from app.geocooling.telemetry_health_service import TelemetryHealthService


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class CommissioningReadinessService:
    """Combine telemetry health with explicit human commissioning gates."""

    def __init__(self, telemetry_service: TelemetryHealthService | None = None) -> None:
        self.telemetry_service = telemetry_service

    def status(self) -> dict[str, Any]:
        telemetry = (
            self.telemetry_service.health()
            if self.telemetry_service is not None
            else TelemetryHealthService().health()
        )
        report = build_commissioning_readiness(
            telemetry,
            physical_identification_confirmed=_env_bool(
                "GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED",
                False,
            ),
            field_certification_confirmed=_env_bool(
                "GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED",
                False,
            ),
        )
        return {
            **report,
            "telemetry_health": telemetry,
            "confirmation_sources": {
                "physical_identification": "GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED",
                "field_certification": "GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED",
            },
            "database_write": False,
            "mqtt_publish": False,
        }
