from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

from app.geocooling.controller import GeoCoolingController

router = APIRouter(
    prefix="/geocooling",
    tags=["GeoCooling"],
)

controller = GeoCoolingController()


class ThermalSnapshotRequest(BaseModel):
    indoor_temperature_c: float | None = Field(default=None, ge=-20, le=60)
    indoor_humidity_percent: float | None = Field(default=None, gt=0, le=100)
    surface_temperature_c: float | None = Field(default=None, ge=-20, le=60)
    floor_supply_temperature_c: float | None = Field(default=None, ge=-20, le=60)
    floor_return_temperature_c: float | None = Field(default=None, ge=-20, le=60)
    source_inlet_temperature_c: float | None = Field(default=None, ge=-20, le=60)
    source_outlet_temperature_c: float | None = Field(default=None, ge=-20, le=60)
    outdoor_temperature_c: float | None = Field(default=None, ge=-40, le=70)


@router.get("/status")
def get_status() -> dict:
    return controller.status()


@router.get("/device")
def get_device_status() -> dict:
    return controller.device_manager.status()


@router.post("/start")
def start_geocooling() -> JSONResponse:
    result = controller.request_start()

    return JSONResponse(
        status_code=202 if result["accepted"] else 409,
        content=result,
    )


@router.post("/stop")
def stop_geocooling() -> JSONResponse:
    result = controller.request_stop()

    return JSONResponse(
        status_code=202 if result["accepted"] else 409,
        content=result,
    )


@router.post("/emergency-stop")
def emergency_stop() -> JSONResponse:
    result = controller.emergency_stop()

    return JSONResponse(
        status_code=200,
        content=result,
    )


@router.post("/reset")
def reset_controller() -> JSONResponse:
    result = controller.reset()

    return JSONResponse(
        status_code=200 if result["accepted"] else 409,
        content=result,
    )


@router.get("/history")
def get_history(
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    return {
        "count": limit,
        "items": controller.history(limit),
    }


@router.get("/diagnostics")
def get_diagnostics() -> dict:
    return controller.diagnostics()


@router.get("/safety")
def get_safety() -> dict:
    return controller.safety_status()


@router.get("/thermal")
def get_thermal() -> dict:
    return controller.thermal_status()


@router.put("/thermal-snapshot")
def update_thermal_snapshot(payload: ThermalSnapshotRequest) -> dict:
    return controller.update_thermal_snapshot(**payload.model_dump())
