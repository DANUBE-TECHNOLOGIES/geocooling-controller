from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.geocooling.brain_v2.brain_v2 import (
    GeoCoolingBrainV2,
)
from app.geocooling.brain_v2.models.observation import (
    ObservationValidationError,
)

from app.geocooling.brain_v2.learning_api import router as learning_router

from app.geocooling.brain_v2.collector_api import router as collector_router

from app.geocooling.brain_v2.prediction_api import router as prediction_router

from app.geocooling.brain_v2.decision_api import router as decision_router

from app.geocooling.brain_v2.advisor_api import router as advisor_router

from app.geocooling.brain_v2.home_assistant_api import router as home_assistant_router

router = APIRouter(
    prefix="/brain-v2",
    tags=["GeoCooling Brain V2"],
)

brain_v2 = GeoCoolingBrainV2()

router.include_router(learning_router)

router.include_router(collector_router)

router.include_router(prediction_router)

router.include_router(decision_router)

router.include_router(advisor_router)

router.include_router(home_assistant_router)


@router.get("/status")
def get_brain_v2_status() -> dict[str, Any]:
    return brain_v2.status()


@router.get("/snapshot")
def get_brain_v2_snapshot() -> dict[str, Any]:
    return brain_v2.snapshot()


@router.get("/knowledge")
def get_brain_v2_knowledge() -> dict[str, Any]:
    return {
        "version": brain_v2.VERSION,
        "read_only": True,
        "hardware_touched": False,
        "knowledge": brain_v2.knowledge.snapshot(),
    }


@router.get("/observations")
def get_brain_v2_observations(
    limit: int = Query(default=100, ge=1, le=5000),
) -> dict[str, Any]:
    observations = brain_v2.recent_observations(limit)

    return {
        "version": brain_v2.VERSION,
        "read_only": True,
        "hardware_touched": False,
        "limit": limit,
        "count": len(observations),
        "observations": observations,
    }


@router.post("/observe")
def post_brain_v2_observation(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    try:
        result = brain_v2.observe(
            payload,
            source="brain_v2_api",
        )
    except ObservationValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return {
        "version": brain_v2.VERSION,
        "hardware_touched": False,
        "decision_authority": False,
        **result,
    }
