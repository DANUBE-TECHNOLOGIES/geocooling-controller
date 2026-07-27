from typing import Any

from fastapi import APIRouter, HTTPException

from app.building.service import BuildingStateService

router = APIRouter(prefix="/building", tags=["Building Digital Twin"])
_service: BuildingStateService | None = None


def configure_building_router(service: BuildingStateService) -> None:
    global _service
    _service = service


def service() -> BuildingStateService:
    if _service is None:
        raise HTTPException(
            status_code=503,
            detail="BuildingStateService non initialisé",
        )
    return _service


@router.get("/state")
def building_state() -> dict[str, Any]:
    return service().state()


@router.get("/inside")
def building_inside() -> dict[str, Any]:
    return service().inside()


@router.get("/weather")
def building_weather() -> dict[str, Any]:
    return service().weather()


@router.get("/sensors")
def building_sensors() -> dict[str, Any]:
    return service().sensors()


@router.get("/diagnostics")
def building_diagnostics() -> dict[str, Any]:
    return service().diagnostics()


@router.post("/refresh")
def building_refresh() -> dict[str, Any]:
    return service().refresh()
