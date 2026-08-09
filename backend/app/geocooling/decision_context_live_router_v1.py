"""
RC1.7C routes for live, passive DecisionContext observation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.geocooling.decision_context_live_v1 import (
    LiveDecisionContextService,
)

router = APIRouter(
    prefix="/geocooling/decision-context",
    tags=["GeoCooling Decision Context"],
)

_service = LiveDecisionContextService()


@router.get("/live")
def get_live_decision_context() -> dict[str, Any]:
    return _service.build_live_context()


@router.get("/live/sources")
def get_live_decision_context_sources() -> dict[str, Any]:
    return _service.source_status()
