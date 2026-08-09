"""
RC3.5 Weather/Inertia predictor API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.geocooling.rc3.weather_inertia_live import (
    LiveWeatherInertiaPredictionService,
)

router = APIRouter(
    prefix="/geocooling/rc3/weather-inertia",
    tags=["GeoCooling RC3 Predictor"],
)

_service = LiveWeatherInertiaPredictionService()


@router.get("/contract")
def get_weather_inertia_contract() -> dict[str, Any]:
    return {
        "schema": "geocooling.rc35.weather-inertia-contract.v1",
        "mode": "SHADOW",
        "horizons_minutes": [
            30,
            60,
            120,
            240,
            360,
            720,
            1440,
            2880,
        ],
        "scenarios": [
            "BASELINE",
            "SOFT_COOLING",
            "FULL_COOLING",
        ],
        "controller_authorized": False,
        "hardware_write": False,
    }


@router.get("/live")
def get_live_weather_inertia_prediction() -> dict[str, Any]:
    try:
        return _service.predict()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
