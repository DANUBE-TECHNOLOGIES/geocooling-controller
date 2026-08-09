from __future__ import annotations
from typing import Any
from fastapi import APIRouter

from app.geocooling.rc3.validation_calibration_bridge_live import (
    LiveValidationCalibrationBridgeService,
)

router = APIRouter(
    prefix="/geocooling/rc3/learning",
    tags=["GeoCooling RC3 Learning"],
)

_service = LiveValidationCalibrationBridgeService()


@router.get("/contract")
def get_learning_contract() -> dict[str, Any]:
    return {
        "schema": "geocooling.rc38.learning-contract.v1",
        "mode": "SHADOW",
        "pipeline": [
            "prediction",
            "measurement",
            "validation",
            "calibration_proposal",
        ],
        "automatic_activation": False,
        "requires_review": True,
        "controller_authorized": False,
        "hardware_write": False,
    }


@router.get("/report")
def get_learning_report() -> dict[str, Any]:
    return _service.report()
