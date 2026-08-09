"""
GeoCooling RC3.1 — shadow comparison API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.geocooling.rc3.shadow import (
    ShadowDecisionService,
)

router = APIRouter(
    prefix="/geocooling/rc3",
    tags=["GeoCooling RC3"],
)

_service = ShadowDecisionService()


@router.get("/contract")
def get_rc3_contract() -> dict[str, Any]:
    return {
        "schema": "geocooling.rc3.contract.v1",
        "mode": "SHADOW",
        "controller_authorized": False,
        "hardware_write": False,
        "mqtt_publish": False,
        "database_write": False,
    }


@router.post("/shadow/compare")
def compare_rc3_shadow(
    payload: dict[str, Any],
) -> dict[str, Any]:
    context = payload.get("context")
    scenario = payload.get("scenario")

    if not isinstance(context, dict):
        context = {}

    if not isinstance(scenario, dict):
        scenario = {}

    return _service.compare(
        context_payload=context,
        scenario_payload=scenario,
    ).as_dict()
