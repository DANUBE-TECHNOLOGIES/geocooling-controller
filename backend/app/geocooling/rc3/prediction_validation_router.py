"""
RC3.7 prediction validation API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.geocooling.rc3.prediction_validation_live import (
    LivePredictionValidationService,
)

router = APIRouter(
    prefix="/geocooling/rc3/prediction-validation",
    tags=["GeoCooling RC3 Prediction Validation"],
)

_service = LivePredictionValidationService()


@router.get("/contract")
def get_prediction_validation_contract() -> dict[str, Any]:
    return {
        "schema": (
            "geocooling.rc37.prediction-validation-contract.v1"
        ),
        "mode": "SHADOW",
        "journal_interval_seconds": 300,
        "automatic_activation": False,
        "controller_authorized": False,
        "hardware_write": False,
    }


@router.get("/report")
def get_prediction_validation_report() -> dict[str, Any]:
    return _service.report()
