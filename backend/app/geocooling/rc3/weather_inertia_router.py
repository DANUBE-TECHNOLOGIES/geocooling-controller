"""
RC3.5 Weather/Inertia predictor API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.geocooling.rc3.precooling_advisor import PreCoolingAdvisor
from app.geocooling.rc3.weather_inertia_live import (
    LiveWeatherInertiaPredictionService,
)

router = APIRouter(
    prefix="/geocooling/rc3/weather-inertia",
    tags=["GeoCooling RC3 Predictor"],
)

_service = LiveWeatherInertiaPredictionService()
_precooling_advisor = PreCoolingAdvisor()


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
        "precooling_advisory_route": (
            "/geocooling/rc3/weather-inertia/precooling-advisory"
        ),
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


@router.get("/precooling-advisory")
def get_precooling_advisory() -> dict[str, Any]:
    """Return a passive pre-cooling timing recommendation.

    The endpoint reuses the live RC3.5 forecast and never forwards the
    recommendation to the controller or any hardware path.
    """
    try:
        prediction = _service.predict()
        result = _precooling_advisor.advise(prediction)
        result["sources"] = prediction.get("sources", {})
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
