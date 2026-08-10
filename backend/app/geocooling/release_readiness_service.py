"""Read-only service exposing consolidated GeoCooling release readiness."""

from __future__ import annotations

import os
from typing import Any

from app.geocooling.commissioning_readiness_service import (
    CommissioningReadinessService,
)
from app.geocooling.hardware_activation_policy import (
    build_hardware_activation_policy,
)
from app.geocooling.release_readiness import build_release_readiness


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ReleaseReadinessService:
    def __init__(self, commissioning_service: Any = None) -> None:
        self.commissioning_service = commissioning_service

    def status(self) -> dict[str, Any]:
        service = self.commissioning_service or CommissioningReadinessService()
        commissioning = service.status()
        policy = build_hardware_activation_policy(commissioning)

        runtime_flags = {
            "hardware_armed": _env_bool("GEOCOOLING_HARDWARE_ARMED", False),
            "hardware_sequence_enabled": _env_bool(
                "GEOCOOLING_HARDWARE_SEQUENCE_ENABLED",
                False,
            ),
            "autopilot_enabled": _env_bool("GEOCOOLING_AUTOPILOT_ENABLED", False),
            "autopilot_allow_real_driver": _env_bool(
                "GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER",
                False,
            ),
            "commissioning_tests_enabled": _env_bool(
                "GEOCOOLING_COMMISSIONING_TESTS_ENABLED",
                False,
            ),
        }

        result = build_release_readiness(
            commissioning,
            policy,
            runtime_flags,
        )

        return {
            **result,
            "commissioning": commissioning,
            "runtime_flags": runtime_flags,
            "safety_note": (
                "Release readiness never arms hardware. Positive hardware paths "
                "remain governed by the commissioning and activation-policy gates."
            ),
        }
