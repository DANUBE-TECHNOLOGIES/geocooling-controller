"""
RC2.1 passive Scenario Engine API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.geocooling.scenario_engine_v1 import (
    ScenarioEngine,
    ScenarioWeights,
)

router = APIRouter(
    prefix="/geocooling/scenario-engine",
    tags=["GeoCooling Scenario Engine"],
)

_engine = ScenarioEngine()


@router.get("/contract")
def get_scenario_engine_contract() -> dict[str, Any]:
    return {
        "schema": "geocooling.rc21.scenario-engine-contract.v1",
        "mode": "passive",
        "scenarios": [
            "WAIT",
            "PRECOOL_30",
            "PRECOOL_60",
            "COOL_NOW",
            "SOFT_COOLING",
        ],
        "weights": {
            "comfort": 0.40,
            "safety": 0.25,
            "energy": 0.20,
            "stability": 0.10,
            "learning": 0.05,
        },
        "safety": {
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
            "outbound_http": False,
        },
    }


@router.post("/evaluate")
def evaluate_scenarios(
    payload: dict[str, Any],
) -> dict[str, Any]:
    weights_payload = payload.get("weights")

    if isinstance(weights_payload, dict):
        weights = ScenarioWeights(
            comfort=float(weights_payload.get("comfort", 0.40)),
            safety=float(weights_payload.get("safety", 0.25)),
            energy=float(weights_payload.get("energy", 0.20)),
            stability=float(weights_payload.get("stability", 0.10)),
            learning=float(weights_payload.get("learning", 0.05)),
        )
        engine = ScenarioEngine(weights=weights)
    else:
        engine = _engine

    context = payload.get("context", payload)

    return engine.evaluate(context).as_dict()
