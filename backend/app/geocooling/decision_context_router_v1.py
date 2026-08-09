"""
RC1.7B passive DecisionContext API.

POST is used only as a pure transformation endpoint: supplied payloads are
normalized and returned. No hardware command, persistence or publication is
performed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.geocooling.decision_context_builder_v1 import (
    PassiveDecisionContextBuilder,
)

router = APIRouter(
    prefix="/geocooling/decision-context",
    tags=["GeoCooling Decision Context"],
)

_builder = PassiveDecisionContextBuilder()


@router.get("/contract")
def get_decision_context_contract() -> dict[str, Any]:
    return {
        "schema": "geocooling.decision-context-builder.v1",
        "mode": "passive",
        "side_effect_free": True,
        "hardware_write": False,
        "mqtt_publish": False,
        "database_write": False,
        "accepted_sources": [
            "thermal",
            "weather",
            "prediction",
            "learning",
            "historian",
            "hardware",
            "runtime",
            "configuration",
        ],
    }


@router.post("/build")
def build_decision_context(payload: dict[str, Any]) -> dict[str, Any]:
    context = _builder.build(
        thermal=payload.get("thermal"),
        weather=payload.get("weather"),
        prediction=payload.get("prediction"),
        learning=payload.get("learning"),
        historian=payload.get("historian"),
        hardware=payload.get("hardware"),
        runtime=payload.get("runtime"),
        configuration=payload.get("configuration"),
        timestamp=payload.get("timestamp"),
    )

    return context.as_dict()
