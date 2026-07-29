from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.geocooling.brain_v2.integration.home_assistant_bridge import (
    HomeAssistantBridge,
)


router = APIRouter(
    prefix="/integration/home-assistant",
    tags=["geocooling-brain-v2-home-assistant"],
)

bridge = HomeAssistantBridge()


@router.get("/status")
def get_home_assistant_bridge_status() -> dict:
    return bridge.status()


@router.get("/state")
def get_home_assistant_state() -> dict:
    return bridge.state()


@router.get(
    "/package.yaml",
    response_class=PlainTextResponse,
)
def get_home_assistant_package(
    base_url: str = Query(
        default="http://192.168.10.110:8000",
        min_length=8,
        max_length=256,
    ),
) -> str:
    return bridge.package_yaml(
        base_url=base_url
    )


@router.get(
    "/dashboard.yaml",
    response_class=PlainTextResponse,
)
def get_home_assistant_dashboard() -> str:
    return bridge.dashboard_yaml()
