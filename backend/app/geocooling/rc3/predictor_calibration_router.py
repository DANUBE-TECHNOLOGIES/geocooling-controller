"""
RC3.6 calibration API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.geocooling.rc3.predictor_calibration_live import (
    LivePredictorCalibrationService,
)

router = APIRouter(
    prefix="/geocooling/rc3/calibration",
    tags=["GeoCooling RC3 Calibration"],
)

_service = LivePredictorCalibrationService()


@router.get("/contract")
def get_calibration_contract() -> dict[str, Any]:
    return {
        "schema": "geocooling.rc36.calibration-contract.v1",
        "mode": "SHADOW",
        "automatic_activation": False,
        "requires_review": True,
        "controller_authorized": False,
        "hardware_write": False,
    }


@router.get("/proposal")
def get_calibration_proposal() -> dict[str, Any]:
    return _service.propose()
