from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.geocooling.controller import GeoCoolingController

router = APIRouter(
    prefix="/geocooling",
    tags=["GeoCooling"],
)

controller = GeoCoolingController()


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
