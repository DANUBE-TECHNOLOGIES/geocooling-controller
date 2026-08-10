from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.geocooling.brain_v2.integration.safe_home_assistant_bridge import (
    SafeHomeAssistantBridge,
)
from app.geocooling.commissioning_readiness_service import (
    CommissioningReadinessService,
)
from app.geocooling.hardware_activation_policy import (
    build_hardware_activation_policy,
)
from app.geocooling.telemetry_health_service import TelemetryHealthService


router = APIRouter(
    prefix="/integration/home-assistant",
    tags=["geocooling-brain-v2-home-assistant"],
)

bridge = SafeHomeAssistantBridge()


@router.get("/status")
def get_home_assistant_bridge_status() -> dict:
    return bridge.status()


@router.get("/state")
def get_home_assistant_state() -> dict:
    return bridge.state()


@router.get("/telemetry-health")
def get_home_assistant_telemetry_health() -> dict:
    return TelemetryHealthService().health()


@router.get("/commissioning-readiness")
def get_commissioning_readiness() -> dict:
    return CommissioningReadinessService().status()


@router.get("/hardware-activation-policy")
def get_hardware_activation_policy() -> dict:
    readiness = CommissioningReadinessService().status()
    return {
        **build_hardware_activation_policy(readiness),
        "readiness": readiness,
    }


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
