from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.geocooling.brain_v2.prediction.thermal_prediction_engine import (
    ThermalPredictionEngine,
)


router = APIRouter(
    prefix="/prediction",
    tags=["geocooling-brain-v2-prediction"],
)

engine = ThermalPredictionEngine()


@router.get("/status")
def get_prediction_status() -> dict:
    return engine.status()


@router.get("/forecast")
def get_thermal_forecast(
    scenario: Literal[
        "auto",
        "passive",
        "cooling",
    ] = Query(
        default="auto"
    ),
    target_temperature_c: float = Query(
        default=24.0,
        ge=15.0,
        le=35.0,
    ),
    horizon_minutes: int = Query(
        default=360,
        ge=15,
        le=1440,
    ),
    step_minutes: int = Query(
        default=15,
        ge=5,
        le=120,
    ),
) -> dict:
    try:
        return engine.forecast(
            scenario=scenario,
            target_temperature_c=(
                target_temperature_c
            ),
            horizon_minutes=(
                horizon_minutes
            ),
            step_minutes=(
                step_minutes
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Thermal prediction failed: {exc}"
            ),
        ) from exc


@router.get("/compare")
def compare_thermal_scenarios(
    target_temperature_c: float = Query(
        default=24.0,
        ge=15.0,
        le=35.0,
    ),
    horizon_minutes: int = Query(
        default=360,
        ge=15,
        le=1440,
    ),
    step_minutes: int = Query(
        default=15,
        ge=5,
        le=120,
    ),
) -> dict:
    try:
        return engine.compare(
            target_temperature_c=(
                target_temperature_c
            ),
            horizon_minutes=(
                horizon_minutes
            ),
            step_minutes=(
                step_minutes
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Thermal comparison failed: {exc}"
            ),
        ) from exc
