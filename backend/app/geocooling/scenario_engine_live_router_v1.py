"""
RC2.1B live passive Scenario Engine API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.geocooling.scenario_engine_live_v1 import (
    LiveScenarioEngineService,
)
from app.geocooling.scenario_engine_v1 import (
    ScenarioWeights,
)

router = APIRouter(
    prefix="/geocooling/scenario-engine",
    tags=["GeoCooling Scenario Engine"],
)

_service = LiveScenarioEngineService()


@router.get("/live")
def get_live_scenario_evaluation(
    comfort_weight: float = Query(0.40, ge=0.0),
    safety_weight: float = Query(0.25, ge=0.0),
    energy_weight: float = Query(0.20, ge=0.0),
    stability_weight: float = Query(0.10, ge=0.0),
    learning_weight: float = Query(0.05, ge=0.0),
) -> dict[str, Any]:
    weights = ScenarioWeights(
        comfort=comfort_weight,
        safety=safety_weight,
        energy=energy_weight,
        stability=stability_weight,
        learning=learning_weight,
    )

    return _service.evaluate_live(
        weights=weights,
    )


@router.get("/live/health")
def get_live_scenario_health() -> dict[str, Any]:
    return _service.health()
