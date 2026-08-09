from __future__ import annotations
from typing import Any

from app.geocooling.rc3.validation_calibration_bridge import (
    ValidationCalibrationBridge,
)


class LiveValidationCalibrationBridgeService:
    def __init__(
        self,
        bridge: ValidationCalibrationBridge | None = None,
    ) -> None:
        self.bridge = bridge or ValidationCalibrationBridge()

    def report(self) -> dict[str, Any]:
        return self.bridge.build()
