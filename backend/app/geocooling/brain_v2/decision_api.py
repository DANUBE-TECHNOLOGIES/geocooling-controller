from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.geocooling.brain_v2.decision.advisory_decision_engine import (
    AdvisoryDecisionEngine,
)


router = APIRouter(
    prefix="/decision",
    tags=["geocooling-brain-v2-decision"],
)

engine = AdvisoryDecisionEngine()


@router.get("/status")
def get_decision_status() -> dict:
    return engine.status()


@router.get("/latest")
def get_latest_decision() -> dict:
    return engine.latest()


@router.get("/evaluate")
def evaluate_decision(
    target_temperature_c: float | None = Query(
        default=None,
        ge=15.0,
        le=35.0,
    ),
    horizon_minutes: int | None = Query(
        default=None,
        ge=15,
        le=1440,
    ),
    persist: bool = Query(
        default=True
    ),
) -> dict:
    try:
        return engine.evaluate(
            target_temperature_c=(
                target_temperature_c
            ),
            horizon_minutes=(
                horizon_minutes
            ),
            persist=persist,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Advisory decision failed: {exc}"
            ),
        ) from exc


@router.get("/history")
def get_decision_history(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
) -> dict:
    entries = engine.history(
        limit=limit
    )

    return {
        "version": engine.VERSION,
        "count": len(entries),
        "entries": entries,
        "safety": {
            "advisory_only": True,
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
            "relay_command": False,
        },
    }
