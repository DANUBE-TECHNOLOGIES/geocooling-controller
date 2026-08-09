"""
GeoCooling RC3.2 — live shadow API.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.geocooling.rc3.live_shadow import (
    LiveShadowRunner,
)

router = APIRouter(
    prefix="/geocooling/rc3",
    tags=["GeoCooling RC3"],
)

_runner = LiveShadowRunner()


@router.get("/shadow/live")
def get_rc3_live_shadow() -> dict[str, Any]:
    return _runner.run()


@router.get("/shadow/live/health")
def get_rc3_live_shadow_health() -> dict[str, Any]:
    return _runner.health()
